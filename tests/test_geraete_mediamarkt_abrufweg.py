"""MediaMarkt ueber den ECHTEN Abrufweg: `hole_fabrik` -> `collect.http.fetch`
mit Mock-Transport (`http.TRANSPORT`), Anfragen gezaehlt.

Die Tests in `test_geraete_adapter_mediamarkt.py` ersetzen `hole` und sehen
darum nicht, was `fetch` darunter tut: nach einem 403 eine zweite Anfrage mit
Browser-Kennung und Client-Hints, bei 429 drei Versuche mit Wartezeit. Fuer
einen Adapter mit `bricht_bei_schutzantwort_ab` ist beides verboten: genau
EINE Anfrage mit der festen ehrlichen Kennung, danach Abbruch des Anbieters.
"""

from __future__ import annotations

from datetime import UTC, datetime

import httpx
import pytest
from bestand_pfad import lese_wurzel

from telco_radar.collect import http
from telco_radar.collect.geraete import sammle_anbieter
from telco_radar.collect.geraete.robots import RobotsWaechter
from telco_radar.geraete_abruf import hole_fabrik
from telco_radar.geraete_config import lade_farben, lade_katalog, lade_quellen

_WURZEL = lese_wurzel()
_EHRLICHE_UA = "TelcoRadar/1.0 (+https://telco-radar.onrender.com/ueber)"
_ROBOTS = "User-agent: *\nDisallow: /api/v1/msg\nDisallow: /de/verboten\n"
_SEITE = (
    '<script>window.__PRELOADED_STATE__ = {"apolloState": {'
    '"CofrPriceFeature:{\\"id\\":\\"Media:de:999\\"}": '
    '{"id": "Media:de:999", "price": {"amount": 500.0}, "currency": "EUR", '
    '"isProductOfTypeMarketplace": false}, '
    '"GraphqlProduct:Media:de-DE:999": '
    '{"title": "SAMSUNG Galaxy S25 256 GB Schwarz Dual SIM", '
    '"url": "/de/product/x.html"}'
    "}};</script>"
)


@pytest.fixture(scope="module")
def katalog():
    return lade_katalog(lese_wurzel())


@pytest.fixture(scope="module")
def farben():
    return lade_farben(_WURZEL)


@pytest.fixture
def netz(monkeypatch):
    """Mock-Transport, der `antwort(anfrage)` ausliefert und alles mitschreibt."""
    gesehen: list[httpx.Request] = []

    def setze(antwort):
        def handler(anfrage: httpx.Request) -> httpx.Response:
            gesehen.append(anfrage)
            if anfrage.url.path == "/robots.txt":
                return httpx.Response(200, text=_ROBOTS)
            return antwort(anfrage)

        monkeypatch.setattr(http, "TRANSPORT", httpx.MockTransport(handler))
        monkeypatch.setattr(http, "_BACKOFF_WAITS", (0.0, 0.0))
        return gesehen

    return setze


def _anbieter(nur_suche: bool = False):
    anbieter = lade_quellen(_WURZEL).nach_name("MediaMarkt")
    anbieter.rate_limit_sekunden = 0
    if nur_suche:
        anbieter.einstiege = [
            e for e in anbieter.einstiege if "iPhone%2018%20Pro" in e.url
        ]
    return anbieter


def _lauf(anbieter, katalog, farben):
    hole = hole_fabrik({"timeout_seconds": 5})
    return sammle_anbieter(
        anbieter,
        katalog,
        farben,
        hole,
        "2026-11-05",
        RobotsWaechter(hole=hole),
        datetime(2026, 11, 5, 12, tzinfo=UTC),
    )


def _seitenabrufe(gesehen):
    return [a for a in gesehen if a.url.path != "/robots.txt"]


@pytest.mark.parametrize("status", [403, 429])
def test_schutzantwort_kostet_genau_eine_anfrage_mit_ehrlicher_kennung(
    netz, katalog, farben, status
):
    gesehen = netz(lambda anfrage: httpx.Response(status, text="gesperrt"))
    bilanz = _lauf(_anbieter(), katalog, farben)

    seiten = _seitenabrufe(gesehen)
    assert len(seiten) == 1
    assert len(gesehen) == 2
    for anfrage in gesehen:
        assert anfrage.headers["user-agent"] == _EHRLICHE_UA
        assert "sec-ch-ua" not in anfrage.headers
    assert bilanz.listungen == []
    assert "Schutzantwort" in bilanz.grund


def test_andere_anbieter_behalten_den_kennungswechsel(netz):
    gesehen = netz(lambda anfrage: httpx.Response(403, text="gesperrt"))
    with pytest.raises(httpx.HTTPStatusError):
        http.fetch("https://www.example.de/seite", {"user_agent": _EHRLICHE_UA})
    kennungen = [a.headers["user-agent"] for a in gesehen]
    assert len(kennungen) == 2
    assert kennungen[0] == _EHRLICHE_UA
    assert kennungen[1] == http.BROWSER_UA


def test_erlaubte_weiterleitung_wird_nach_pruefung_gefolgt(netz, katalog, farben):
    ziel = "/de/brand/apple/iphone/iphone-18-pro"

    def antwort(anfrage):
        if anfrage.url.path == "/de/search.html":
            return httpx.Response(302, headers={"location": ziel})
        return httpx.Response(200, text=_SEITE)

    gesehen = netz(antwort)
    bilanz = _lauf(_anbieter(nur_suche=True), katalog, farben)

    assert [a.url.path for a in _seitenabrufe(gesehen)] == ["/de/search.html", ziel]
    assert "https://www.mediamarkt.de" + ziel in bilanz.besucht


def test_weiterleitung_auf_gesperrten_pfad_wird_nicht_gefolgt(netz, katalog, farben):
    def antwort(anfrage):
        if anfrage.url.path == "/de/search.html":
            return httpx.Response(302, headers={"location": "/de/verboten/seite"})
        return httpx.Response(200, text=_SEITE)

    gesehen = netz(antwort)
    bilanz = _lauf(_anbieter(nur_suche=True), katalog, farben)

    assert [a.url.path for a in _seitenabrufe(gesehen)] == ["/de/search.html"]
    assert bilanz.listungen == []
    assert "robots" in bilanz.grund


def test_weiterleitung_auf_fremden_host_wird_gegen_dessen_robots_geprueft(
    netz, katalog, farben
):
    def antwort(anfrage):
        if anfrage.url.host == "www.mediamarkt.de":
            return httpx.Response(302, headers={"location": "https://fremd.example/x"})
        return httpx.Response(200, text=_SEITE)

    gesehen = netz(antwort)
    _lauf(_anbieter(nur_suche=True), katalog, farben)

    pfade = [(a.url.host, a.url.path) for a in gesehen]
    assert ("fremd.example", "/robots.txt") in pfade
