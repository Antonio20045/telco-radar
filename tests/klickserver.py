"""Lokaler Beispielserver für die Klick-Crawler-Tests: nur 127.0.0.1, kein Netz.

Eine Antwortfunktion bekommt den Pfad samt Anfrage und liefert eine ``Antwort``; der
Server merkt jeden Abruf mit Pfad und Zeitpunkt (``time.monotonic``), beim Eingang und
am Ende der Antwort; ``luecken`` misst den Crawl-delay vom Ende der vorigen Antwort.
Schließt der Browser die Verbindung vor dem Ende, steht der Pfad in ``abgebrochen``.
Unter ``localhost`` ist derselbe Server als zweiter Host erreichbar. ``karte`` und
``laufe`` bauen eine Prüfkarte und rufen den Crawler mit eigener Hostschleuse.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


@dataclass(frozen=True)
class Antwort:
    status: int = 200
    typ: str = "text/plain"
    koerper: str = ""
    kopf: dict[str, str] = field(default_factory=dict)
    verzug: float = 0.0


def html(koerper: str, status: int = 200) -> Antwort:
    return Antwort(status, "text/html; charset=utf-8", koerper)


def umleitung(ziel: str) -> Antwort:
    return Antwort(302, "text/html", "", {"Location": ziel})


@dataclass
class Klickserver:
    antworte: Callable[[str], Antwort]
    port: int = 0
    abrufe: list[str] = field(default_factory=list)
    zeiten: list[tuple[float, str]] = field(default_factory=list)
    fertig: list[tuple[float, str]] = field(default_factory=list)
    abgebrochen: list[str] = field(default_factory=list)

    def adresse(self, pfad: str, host: str = "127.0.0.1") -> str:
        return f"http://{host}:{self.port}{pfad}"

    def mit(self, anfang: str) -> list[str]:
        return [a for a in self.abrufe if a.startswith(anfang)]

    def luecken(self, anfang: str | tuple[str, ...]) -> list[float]:
        """Je Abruf ab dem zweiten: Eingang minus Ende der vorigen Antwort."""
        eingang = [t for t, pfad in self.zeiten if pfad.startswith(anfang)]
        ende = [t for t, pfad in self.fertig if pfad.startswith(anfang)]
        return [b - a for a, b in zip(ende, eingang[1:], strict=False)]


@contextmanager
def klickserver(antworte: Callable[[str], Antwort]) -> Iterator[Klickserver]:
    server = Klickserver(antworte)

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args: object) -> None:
            return

        def do_GET(self) -> None:
            server.abrufe.append(self.path)
            server.zeiten.append((time.monotonic(), self.path))
            antwort = server.antworte(self.path)
            if antwort.verzug:
                time.sleep(antwort.verzug)
            daten = antwort.koerper.encode("utf-8")
            try:
                self.send_response(antwort.status)
                self.send_header("Content-Type", antwort.typ)
                self.send_header("Content-Length", str(len(daten)))
                for name, wert in antwort.kopf.items():
                    self.send_header(name, wert)
                self.end_headers()
                self.wfile.write(daten)
                self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError):
                server.abgebrochen.append(self.path)
                return
            server.fertig.append((time.monotonic(), self.path))

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.port = httpd.server_address[1]
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    try:
        yield server
    finally:
        httpd.shutdown()
        httpd.server_close()


JETZT = datetime(2026, 10, 3, 5, 0, tzinfo=UTC)
KNOEPFE = {
    "speicher": {"selektor": "#speicher button", "wert": "data-wert"},
    "tarif": {"selektor": "#tarif button", "wert": "data-wert"},
    "laufzeit": {"selektor": "#laufzeit button", "wert": "data-wert"},
    "gewaehlt": {"attribut": "aria-pressed", "wert": "true"},
}


def karte(antwort: dict):
    from telco_radar.collect.geraete.klickkarte import klickkarte_aus_daten

    daten = {
        "anbieter": "Beispielanbieter",
        "knoepfe": KNOEPFE,
        "zusammenfassung": {"selektor": "#preis"},
        "antwort": antwort,
        "kanarie": {"selektor": "#kanarie", "enthaelt": "Beispielhandy X"},
    }
    return klickkarte_aus_daten(daten, "Prüfkarte")


def laufe(browser, adresse: str, k, robots, **weiter):
    from telco_radar.collect.geraete.klickcrawler import klicke_durch
    from telco_radar.collect.geraete.klicktor import Hostschleuse
    from telco_radar.collect.geraete.robots import RobotsWaechter

    hole = robots if callable(robots) else (lambda url: (200, robots))
    waechter = RobotsWaechter(hole=hole)
    schleuse = Hostschleuse(waechter, lambda: JETZT)
    return klicke_durch(
        browser, adresse, k, waechter, lambda: JETZT, schleuse=schleuse, **weiter
    )
