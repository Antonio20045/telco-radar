"""Ladefrist gegen Tor: eine Störung im Tor geht der Zeitüberschreitung vor (Regel 4).

Übernommen aus der Prüfer-Reproduktion zu 66f6c5cf. Playwright (sync) stellt Ereignisse
während jedes synchronen Aufrufs zu, auch während ``page.evaluate``: kommt eine 202 der
eigenen Website (Telekom-Muster, Tageslauf 08.10.2026) erst beim letzten Ladetest oder
bei der Diagnose an, steht sie in ``tor.stoerung``. Dann ist die Seite gestört mit
diesem Grund, ohne ``zeitueberschreitung``, und der Tageslauf ruft keine weitere Seite
ab. Gegenprobe: bleibt die Anfrage nur hängen, ist es eine Zeitüberschreitung, und die
nächste Seite folgt.

Echt sind ``crawler_im_browser`` (Tor, Fristschleuse, Beobachter), ``klicke_durch``,
``Wache``, ``Ladung`` und ``fahre``; nur Browserkontext und Seite sind Attrappen, die
Ereignisse wie Playwright während eines synchronen Aufrufs zustellen. Kein Netz.
"""

from __future__ import annotations

import time
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

import pytest

from telco_radar.collect.geraete import klickcrawler
from telco_radar.collect.geraete.klickergebnis import LAUF_LEER
from telco_radar.collect.geraete.klickkarte import lade_klickkarte
from telco_radar.collect.geraete.klickkontext import Sitzung
from telco_radar.collect.geraete.klicklauf import (
    LAUF_GELESEN,
    LAUF_GESTOERT,
    STOERUNG_ZEIT,
    Klicklauf,
)
from telco_radar.collect.geraete.klicktageslauf import crawler_im_browser, fahre
from telco_radar.collect.geraete.klicktor import SEITEN_FRIST_MS
from telco_radar.collect.geraete.klickziele import Erkundungsziel, Seitenziel

WURZEL = Path(__file__).parent.parent
KARTE = lade_klickkarte(WURZEL / "config" / "klickkarten" / "telekom.yaml")
HOST = "https://www.telekom.de"
ERSTE = f"{HOST}/shop/geraet/apple/apple-iphone-17-pro/tiefblau-256-gb?tariffId=MF_1"
ZWEITE = f"{HOST}/shop/geraet/google/google-pixel-11/frost-256-gb?tariffId=MF_17791"
HAENGT = f"{HOST}/shop/api/eshop/bff-de/session/check"


class _Anfrage:
    def __init__(self, url: str, art: str) -> None:
        self.url, self.resource_type, self.method = url, art, "GET"


class _Antwort:
    def __init__(self, anfrage: _Anfrage, status: int) -> None:
        self.request, self.url, self.status = anfrage, anfrage.url, status
        self.headers: dict[str, str] = {}


class _Seite:
    """Hauptseite HTTP 200, eine Anfrage hängt; mit ``status`` kommt ihre Antwort nach
    ``SEITEN_FRIST_MS`` Warten an, zugestellt im nächsten ``evaluate``."""

    def __init__(self, status: int | None) -> None:
        self.url = "about:blank"
        self.status = status
        self.handler: dict[str, list] = defaultdict(list)
        self.gewartet_ms = 0
        self.haengt: _Anfrage | None = None

    def on(self, name: str, f) -> None:
        self.handler[name].append(f)

    def _sende(self, name: str, objekt) -> None:
        for f in list(self.handler[name]):
            f(objekt)

    def goto(self, url: str, wait_until: str | None = None, timeout=None) -> None:
        self.url = url
        if url == "about:blank":
            return
        haupt = _Anfrage(url, "document")
        self._sende("request", haupt)
        self._sende("response", _Antwort(haupt, 200))
        self._sende("requestfinished", haupt)
        self.haengt = _Anfrage(HAENGT, "xhr")
        self._sende("request", self.haengt)

    def wait_for_timeout(self, ms: float) -> None:
        self.gewartet_ms += ms

    def evaluate(self, js: str, *args):
        if (
            self.haengt is not None
            and self.status is not None
            and self.gewartet_ms >= SEITEN_FRIST_MS
        ):
            haengt, self.haengt = self.haengt, None
            self._sende("response", _Antwort(haengt, self.status))
            self._sende("requestfinished", haengt)
        if "=== 'complete'" in js:
            return False
        if "readyState" in js:
            return "loading"
        return None


class _Kontext:
    def cookies(self) -> list:
        return []

    def close(self) -> None:
        return None


class _Cdp:
    def send(self, *_a, **_k) -> None:
        return None

    def detach(self) -> None:
        return None


def _robots(_url: str) -> tuple[int, str]:
    return 200, "User-agent: *\nAllow: /\n"


@pytest.mark.parametrize(
    ("status", "aufrufe", "laufstatus"),
    [(202, [ERSTE], LAUF_GESTOERT), (None, [ERSTE, ZWEITE], LAUF_LEER)],
)
def test_stoerung_im_tor_geht_der_zeitueberschreitung_vor(
    monkeypatch, status, aufrufe, laufstatus
):
    tore = []

    def oeffne(_browser, tor, _fenster, _kennung=None, *, wiedergabe=()):
        tore.append(tor)
        seite = _Seite(status)
        tor.warte = seite.wait_for_timeout
        return Sitzung(_Kontext(), seite, _Cdp())

    monkeypatch.setattr(klickcrawler, "oeffne_sitzung", oeffne)
    ziel = Erkundungsziel(
        "telekom",
        "Telekom",
        (
            Seitenziel("apple-iphone-17-pro", 256, ERSTE, modell="iPhone 17 Pro"),
            Seitenziel("google-pixel-11", 256, ZWEITE, modell="Pixel 11"),
        ),
        None,
        0.0,
    )
    echt = crawler_im_browser(
        object(), ziel, KARTE, lambda: datetime(2026, 10, 8, 11, tzinfo=UTC), _robots
    )
    gerufen: list[str] = []

    def crawle(seite, ende):
        gerufen.append(seite.adresse)
        if len(gerufen) > 1:
            return Klicklauf("Telekom", seite.adresse, LAUF_GELESEN)
        return echt(seite, ende)

    daten = fahre(
        ziel,
        KARTE,
        "telekom.yaml",
        crawle,
        "2026-10-08",
        time.monotonic() + 3600,
        gelesen={},
    )

    assert gerufen == aufrufe
    erste = daten["seiten"][0]
    assert erste["status"] == LAUF_GESTOERT
    assert erste["ladung"]["geladen"] is False
    if status is None:
        assert tore[0].stoerung is None
        assert erste["stoerung"] == STOERUNG_ZEIT
    else:
        assert "HTTP 202" in tore[0].stoerung
        assert (erste["stoerung"], erste["grund"]) == (None, tore[0].stoerung)
    assert daten["laufstatus"] == laufstatus
