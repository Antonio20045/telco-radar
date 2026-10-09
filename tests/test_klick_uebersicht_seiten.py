"""Telekom-Übersicht über alle Seiten, ohne Warten auf ``load`` (Pitch 4, Schnitt 3).

``klickuebersicht.lies_uebersicht`` folgt dem gelesenen Folgelink der Übersicht
(``<link rel="next">``, sonst „Weitere Geräte anzeigen“), aufgelöst gegen die
Seitenadresse, nur auf demselben Host, nur mit robots.txt-Erlaubnis und höchstens
``HOECHSTE_SEITEN`` Seiten; zusammengesetzt wird keine Adresse. ``vollstaendig`` ist
wahr nur, wenn die letzte gelesene Seite keinen Folgelink trägt. Gelesen wird, sobald
``window.__INITIAL_STATE__`` steht, auch wenn ein langsames Skript ``load`` aufhält.
Seite 1 ist die gespeicherte echte Übersicht
``tests/fixtures/geraete/telekom_kategorie_buendel_magentamobil_s.html.gz``
(MagentaMobil S, 08.09.2026) mit ihrem eigenen Folgelink, ausgeliefert auf 127.0.0.1;
fremde Hosts sperrt robots.txt, es geht nichts ins Netz. Gelesen wird mit der Lesart
des serverseitigen Zustands (``ZUSTAND``); die Telekom liest seit Oktober 2026 die
Datenantwort und blättert in der Seite (``test_klick_uebersicht_liste``).
"""

from __future__ import annotations

import dataclasses
import gzip
from datetime import UTC, datetime

import pytest
from bestand_pfad import lese_wurzel
from klickergebnisse import WURZEL
from klickserver import Antwort, html, klickserver

from telco_radar.collect.geraete.klickkarte import lade_klickkarte
from telco_radar.collect.geraete.klicklauf import LAUF_GELESEN, LAUF_GESTOERT
from telco_radar.collect.geraete.klicktageslauf import GRUND_NACH_STOERUNG, fahre
from telco_radar.collect.geraete.klicktor import Hostschleuse
from telco_radar.collect.geraete.klickuebersicht import (
    GRUND_FREMDER_HOST,
    GRUND_GESPERRT,
    GRUND_OBERGRENZE,
    GRUND_OHNE_LESART,
    HOECHSTE_SEITEN,
    LESARTEN,
    TELEKOM_BEREIT_JS,
    Lesart,
    lies_uebersicht,
    telekom_folgelink,
)
from telco_radar.collect.geraete.klickziele import TAGESDATEI, lade_ziele
from telco_radar.collect.geraete.robots import RobotsWaechter
from telco_radar.collect.geraete.telekom import lies_buendel

FIXTURE = (
    WURZEL / "tests/fixtures/geraete/telekom_kategorie_buendel_magentamobil_s.html.gz"
)
PFAD = "/shop/geraete/smartphones?tariffId=MF_17785"
NAECHSTE = (
    "/shop/geraete/smartphones?currentPage=2&tariffId=MF_17785&itemPerPage=24"
    "&excludedCurrentPage=1&bp=acquisition"
)
IM_HTML = NAECHSTE.replace("&", "&amp;")
DOKUMENTE = "/shop/geraete/"
JETZT = datetime(2026, 10, 9, 5, 0, tzinfo=UTC)
OFFEN = "User-agent: *\nDisallow:\n"
ZU = "User-agent: *\nDisallow: /\n"
TARIFE = ("MF_17791", "MF_17779", "MF_17785", "MF_17797", "MF_17803")
VERZUG_S = 20.0
ZUSTAND = Lesart(lies_buendel, telekom_folgelink, TELEKOM_BEREIT_JS)
"""Telekom bis September 2026: ``window.__INITIAL_STATE__.productList`` im Dokument."""


@pytest.fixture(autouse=True)
def zustand(monkeypatch):
    monkeypatch.setitem(LESARTEN, "Telekom", ZUSTAND)


@pytest.fixture(scope="module")
def roh() -> str:
    return gzip.open(FIXTURE, "rb").read().decode("utf-8", "replace")


@pytest.fixture(scope="module")
def karte():
    return lade_klickkarte(WURZEL / "config" / "klickkarten" / "telekom.yaml")


def _mit_folgelink(roh: str, href: str | None) -> str:
    """Die Übersicht mit anderem Folgelink (``rel=next`` und Knopf) oder ohne."""
    if href is None:
        ohne = roh.replace(f'<link data-rh="true" rel="next" href="{IM_HTML}"/>', "")
        return ohne.replace(f'href="{IM_HTML}"', "")
    return roh.replace(IM_HTML, href.replace("&", "&amp;"))


def _robots_nur_lokal(url: str) -> tuple[int, str]:
    return 200, OFFEN if "127.0.0.1" in url else ZU


def _lies(chromium, karte, adresse: str, robots=_robots_nur_lokal) -> dict:
    waechter = RobotsWaechter(hole=robots)
    schleuse = Hostschleuse(waechter, lambda: JETZT)
    return lies_uebersicht(
        chromium, adresse, karte, waechter, lambda: JETZT, schleuse=schleuse
    )


def _dokumente(server) -> list[str]:
    return server.mit(DOKUMENTE)


def test_zwei_verkettete_seiten_beide_gelesen_und_vollstaendig(chromium, karte, roh):
    """Seite 2 zeigt dieselben neun Geräte wie Seite 1: sie zählen nicht doppelt."""
    seite2 = _mit_folgelink(roh, None)

    def antworte(pfad: str) -> Antwort:
        return {PFAD: html(roh), NAECHSTE: html(seite2)}.get(pfad, html("", 404))

    with klickserver(antworte) as server:
        ergebnis = _lies(chromium, karte, server.adresse(PFAD))
        erwartet = [server.adresse(PFAD), server.adresse(NAECHSTE)]
    assert ergebnis["status"] == LAUF_GELESEN, ergebnis["grund"]
    assert ergebnis["vollstaendig"] is True
    assert ergebnis["unvollstaendig"] is None
    assert [s["adresse"] for s in ergebnis["seiten"]] == erwartet
    assert [s["status"] for s in ergebnis["seiten"]] == [LAUF_GELESEN] * 2
    assert [s["beleg"]["seite"] for s in ergebnis["seiten"]] == erwartet
    assert len(ergebnis["saetze"]) == 9
    assert [s["saetze_neu"] for s in ergebnis["seiten"]] == [9, 0]
    assert _dokumente(server) == [PFAD, NAECHSTE]


def test_folgelink_auf_fremden_host_wird_nicht_gefolgt(chromium, karte, roh):
    def antworte(pfad: str) -> Antwort:
        return html(seite1) if pfad == PFAD else html("", 404)

    with klickserver(antworte) as server:
        seite1 = _mit_folgelink(roh, server.adresse(NAECHSTE, host="localhost"))
        ergebnis = _lies(chromium, karte, server.adresse(PFAD), lambda u: (200, OFFEN))
    assert ergebnis["status"] == LAUF_GELESEN, ergebnis["grund"]
    assert ergebnis["vollstaendig"] is False
    assert ergebnis["unvollstaendig"].startswith(GRUND_FREMDER_HOST)
    assert len(ergebnis["seiten"]) == 1
    assert len(ergebnis["saetze"]) == 9
    assert _dokumente(server) == [PFAD]


def test_folgelink_von_robots_gesperrt_wird_nicht_gefolgt(chromium, karte, roh):
    seite1 = _mit_folgelink(roh, "/gesperrt/seite2?tariffId=MF_17785")

    def robots(url: str) -> tuple[int, str]:
        regeln = "User-agent: *\nDisallow: /gesperrt\n"
        return 200, regeln if "127.0.0.1" in url else ZU

    def antworte(pfad: str) -> Antwort:
        return html(seite1) if pfad == PFAD else html("", 404)

    with klickserver(antworte) as server:
        ergebnis = _lies(chromium, karte, server.adresse(PFAD), robots)
    assert ergebnis["vollstaendig"] is False
    assert ergebnis["unvollstaendig"].startswith(GRUND_GESPERRT)
    assert not server.mit("/gesperrt")
    assert len(ergebnis["saetze"]) == 9


def test_obergrenze_der_seiten_je_uebersicht(chromium, karte, roh):
    def antworte(pfad: str) -> Antwort:
        if not pfad.startswith("/shop/geraete/smartphones?"):
            return html("", 404)
        nummer = int(pfad.rsplit("seite=", 1)[1]) if "seite=" in pfad else 1
        return html(_mit_folgelink(roh, f"{PFAD}&seite={nummer + 1}"))

    with klickserver(antworte) as server:
        ergebnis = _lies(chromium, karte, server.adresse(PFAD))
    assert len(ergebnis["seiten"]) == HOECHSTE_SEITEN
    assert len(_dokumente(server)) == HOECHSTE_SEITEN
    assert ergebnis["vollstaendig"] is False
    assert ergebnis["unvollstaendig"].startswith(GRUND_OBERGRENZE)


def test_langsames_skript_haelt_das_lesen_nicht_auf(chromium, karte, roh):
    """Ein Skript am Ende der Seite hält ``load`` ``VERZUG_S`` auf; gelesen wird
    vorher, denn ``__INITIAL_STATE__`` steht schon im Hauptdokument."""
    langsam = _mit_folgelink(roh, None).replace(
        "</body>", '<script src="/langsam.js"></script></body>'
    )

    def antworte(pfad: str) -> Antwort:
        if pfad == "/langsam.js":
            return Antwort(200, "text/javascript", "", verzug=VERZUG_S)
        return html(langsam) if pfad == PFAD else html("", 404)

    with klickserver(antworte) as server:
        ergebnis = _lies(chromium, karte, server.adresse(PFAD))
        skript_fertig = [p for _, p in server.fertig if p == "/langsam.js"]
    assert ergebnis["status"] == LAUF_GELESEN, ergebnis["grund"]
    assert ergebnis["vollstaendig"] is True
    assert len(ergebnis["saetze"]) == 9
    assert server.mit("/langsam.js")
    assert skript_fertig == []


def test_tagesdatei_nennt_alle_fuenf_tarife_wortlich():
    ziele = lade_ziele(lese_wurzel(), TAGESDATEI, hoechste=None)
    telekom = next(z for z in ziele if z.schluessel == "telekom")
    basis = "https://www.telekom.de/shop/geraete/smartphones?tariffId="
    assert telekom.uebersichten == tuple(basis + t for t in TARIFE)


class _Uhr:
    jetzt = 0.0

    def __call__(self) -> float:
        return self.jetzt


def test_gestoerte_folgeseite_haelt_den_anbieter_an(karte):
    ziele = lade_ziele(lese_wurzel(), TAGESDATEI, hoechste=None)
    telekom = next(z for z in ziele if z.schluessel == "telekom")
    telekom = dataclasses.replace(telekom, uebersichten=telekom.uebersichten[:1])
    adresse = telekom.uebersichten[0]
    gestoert = {
        "adresse": adresse + "&seite=2",
        "status": LAUF_GESTOERT,
        "grund": "Abruf gestört (HTTP 403)",
        "stoerung": None,
    }

    def lies(adresse: str, ende: float) -> dict:
        erste = {"adresse": adresse, "status": LAUF_GELESEN, "grund": None}
        return {
            **erste,
            "stoerung": None,
            "saetze": [{"titel": "iPhone 18 Pro 256 GB"}],
            "seiten": [erste, gestoert],
            "vollstaendig": False,
        }

    def crawle(seite, ende):
        raise AssertionError("nach gestörter Folgeseite keine Produktseite")

    daten = fahre(
        telekom,
        karte,
        "k",
        crawle,
        "2026-10-09",
        10**6,
        gelesen={},
        uhr=_Uhr(),
        schlafe=lambda s: None,
        lies_uebersicht=lies,
    )
    assert daten["laufstatus"] == LAUF_GESTOERT
    assert all(s["grund"].startswith(GRUND_NACH_STOERUNG) for s in daten["seiten"])


def test_anbieter_ohne_lesart_ist_gestoert_ohne_browser(karte):
    fremd = dataclasses.replace(karte, anbieter="Beispielanbieter")
    ergebnis = _lies(None, fremd, "http://127.0.0.1:9/uebersicht")
    assert ergebnis["status"] == LAUF_GESTOERT
    assert ergebnis["grund"].startswith(GRUND_OHNE_LESART)
    assert ergebnis["saetze"] == []
    assert ergebnis["vollstaendig"] is False
    assert "Telekom" in LESARTEN
