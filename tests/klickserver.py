"""Lokaler Beispielserver für die Klick-Crawler-Tests: nur 127.0.0.1, kein Netz.

Eine Antwortfunktion bekommt den Pfad samt Anfrage und liefert eine ``Antwort``; der
Server merkt jeden Abruf mit Pfad und Zeitpunkt (``time.monotonic``). Unter
``localhost`` ist derselbe Server als zweiter Host erreichbar.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
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

    def adresse(self, pfad: str, host: str = "127.0.0.1") -> str:
        return f"http://{host}:{self.port}{pfad}"

    def mit(self, anfang: str) -> list[str]:
        return [a for a in self.abrufe if a.startswith(anfang)]


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
            self.send_response(antwort.status)
            self.send_header("Content-Type", antwort.typ)
            self.send_header("Content-Length", str(len(daten)))
            for name, wert in antwort.kopf.items():
                self.send_header(name, wert)
            self.end_headers()
            self.wfile.write(daten)

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.port = httpd.server_address[1]
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    try:
        yield server
    finally:
        httpd.shutdown()
        httpd.server_close()
