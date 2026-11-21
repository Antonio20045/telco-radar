"""Serverfehler im Klick-Tageslauf: wiederholen statt den Anbieter anzuhalten.

Nachtlauf 21.11.2026 (Klick-Lauf 44840854026, Eintrag ``1und1``): die erste
Tarifdetail-Seite antwortete einmal mit HTTP 502; danach hieß jede weitere Seite
„nicht_besucht, nach Störung keine weitere Anfrage“ (7 Übersichten, 21 Produktseiten).
Ein 5xx ist kein Bot-Schutz (CLAUDE.md Regel 10). Erwartet: dieselbe Seite höchstens
zweimal neu nach wachsender Pause, danach die nächste Seite; 403 beendet den Anbieter
wie bisher sofort, ebenso drei Seiten in Folge mit Serverfehler. Crawler und
Übersichtsleser sind gefälscht und laufen wie im Betrieb durch die Wiederholung
(``klickwiederholung.Wiederholung``, in ``klicktageslauf.leser_im_browser`` gesetzt);
ihre Ergebnisse tragen die Störungsart, die ``klickwache.form`` aus dem Status der
Hauptseite bildet (wie ``klickcrawler``). Einordnung und Verdrahtung prüft ein echter
Browser gegen einen lokalen Server mit 502.
"""

from __future__ import annotations

import time
from dataclasses import replace
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from bestand_pfad import kachel_wurzel
from klickergebnisse import WURZEL, erfasst, o2_lesung
from klickserver import html, klickserver

from telco_radar.collect.geraete.klickergebnis import SEITE_NICHT_BESUCHT
from telco_radar.collect.geraete.klickkarte import lade_klickkarte
from telco_radar.collect.geraete.klicklauf import (
    LAUF_GELESEN,
    LAUF_GESTOERT,
    STOERUNG_SEITE,
    Klicklauf,
    abruf_gestoert,
)
from telco_radar.collect.geraete.klicktageslauf import (
    GRUND_NACH_STOERUNG,
    fahre,
    leser_im_browser,
)
from telco_radar.collect.geraete.klicktor import Hostschleuse
from telco_radar.collect.geraete.klickuebersicht import lies_uebersicht
from telco_radar.collect.geraete.klickwache import form
from telco_radar.collect.geraete.klickwiederholung import Wiederholung
from telco_radar.collect.geraete.klickziele import TAGESDATEI, lade_ziele
from telco_radar.collect.geraete.robots import RobotsWaechter

HEUTE = "2026-11-21"
MINUTE = 60.0
JETZT = datetime(2026, 11, 21, 0, 3, tzinfo=UTC)
SERVERFEHLER = "serverfehler"
"""Der Wert von ``klicklauf.STOERUNG_SERVER`` (wörtlich, damit der Test gegen den
alten Stand fachlich rot ist, nicht am Import scheitert)."""


@pytest.fixture(scope="module")
def ziele():
    return {
        z.schluessel: z for z in lade_ziele(kachel_wurzel(), TAGESDATEI, hoechste=None)
    }


@pytest.fixture(scope="module")
def o2(ziele):
    return replace(ziele["o2"], seiten=ziele["o2"].seiten[:5])


@pytest.fixture(scope="module")
def einsundeins(ziele):
    """Der Eintrag ``1und1`` mit seinen echten Übersichten, ohne Produktseiten."""
    return replace(ziele["1und1"], seiten=())


@pytest.fixture(scope="module")
def karte_o2():
    return lade_klickkarte(WURZEL / "config" / "klickkarten" / "o2.yaml")


@pytest.fixture(scope="module")
def karte_1und1():
    return lade_klickkarte(WURZEL / "config" / "klickkarten" / "1und1.yaml")


@pytest.fixture(scope="module")
def kombination():
    return erfasst(o2_lesung("256 GB", "O2 Mobile Unlimited M Plus", 36))


class Uhr:
    def __init__(self) -> None:
        self.jetzt = 0.0

    def __call__(self) -> float:
        return self.jetzt


def _lauf(adresse: str, status: int, kombination) -> Klicklauf:
    """Ein Lauf, wie ``klickcrawler`` ihn nach der Antwort ``status`` der Hauptseite
    schreibt: gelesen bei 200, sonst gestört mit Grund und ``form`` des Tors."""
    if status == 200:
        return Klicklauf("o2", adresse, ergebnisse=[kombination])
    tor = SimpleNamespace(haupt_status=status)
    lauf = Klicklauf("o2", adresse, LAUF_GESTOERT, abruf_gestoert(status), status)
    return replace(lauf, stoerung=form(tor))


class Crawler:
    """Je Adresse eine Folge von HTTP-Status der Hauptseite, sonst 200."""

    def __init__(self, uhr, kombination, folgen) -> None:
        self.uhr, self.kombination, self.folgen = uhr, kombination, folgen
        self.aufrufe: list[str] = []

    def __call__(self, seite, ende):
        self.aufrufe.append(seite.adresse)
        self.uhr.jetzt += MINUTE
        folge = self.folgen.get(seite.adresse, [])
        status = folge.pop(0) if folge else 200
        return _lauf(seite.adresse, status, self.kombination)


class Schlaf:
    def __init__(self, uhr) -> None:
        self.uhr, self.pausen = uhr, []

    def __call__(self, sekunden: float) -> None:
        self.pausen.append(sekunden)
        self.uhr.jetzt += sekunden


def _fahre(ziel, karte, crawler, uhr, schlaf, lies=None, ende=10**6):
    crawle, liest = Wiederholung(uhr, schlaf).um(crawler, lies or _ohne_uebersicht)
    return fahre(
        ziel,
        karte,
        "karte.yaml",
        crawle,
        HEUTE,
        ende,
        gelesen={},
        uhr=uhr,
        schlafe=schlaf,
        lies_uebersicht=liest if lies else None,
    )


def _ohne_uebersicht(adresse, ende):
    raise AssertionError("keine Übersicht erwartet")


def test_ein_502_wird_wiederholt_und_die_seite_gelesen(o2, karte_o2, kombination):
    zweite = o2.seiten[1].adresse
    uhr = Uhr()
    crawler = Crawler(uhr, kombination, {zweite: [502]})
    schlaf = Schlaf(uhr)

    daten = _fahre(o2, karte_o2, crawler, uhr, schlaf)

    assert crawler.aufrufe.count(zweite) == 2
    assert len(crawler.aufrufe) == len(o2.seiten) + 1
    seite = daten["seiten"][1]
    assert (seite["status"], seite["ladung"]["versuche"]) == (LAUF_GELESEN, 2)
    assert len(schlaf.pausen) == 1 and schlaf.pausen[0] > 0
    assert daten["laufstatus"] == LAUF_GELESEN


def test_bleibender_5xx_hoechstens_zwei_wiederholungen_dann_die_naechste_seite(
    o2, karte_o2, kombination
):
    zweite = o2.seiten[1].adresse
    uhr = Uhr()
    crawler = Crawler(uhr, kombination, {zweite: [502, 503, 500, 502]})
    schlaf = Schlaf(uhr)

    daten = _fahre(o2, karte_o2, crawler, uhr, schlaf)

    assert crawler.aufrufe.count(zweite) == 3
    assert len(schlaf.pausen) == 2 and schlaf.pausen[0] < schlaf.pausen[1]
    seite = daten["seiten"][1]
    assert (seite["status"], seite["stoerung"], seite["ladung"]["versuche"]) == (
        LAUF_GESTOERT,
        SERVERFEHLER,
        3,
    )
    assert seite["grund"] == "Abruf gestört (HTTP 500)"
    rest = daten["seiten"][2:]
    assert {s["status"] for s in rest} == {LAUF_GELESEN}
    assert daten["laufstatus"] == LAUF_GELESEN
    assert daten["ueberfaellig"] == [zweite]


def test_gegenprobe_403_beendet_den_anbieter_sofort_ohne_wiederholung(
    o2, karte_o2, kombination
):
    zweite = o2.seiten[1].adresse
    uhr = Uhr()
    crawler = Crawler(uhr, kombination, {zweite: [403]})
    schlaf = Schlaf(uhr)

    daten = _fahre(o2, karte_o2, crawler, uhr, schlaf)

    assert crawler.aufrufe == [o2.seiten[0].adresse, zweite]
    assert schlaf.pausen == []
    assert daten["laufstatus"] == LAUF_GESTOERT
    assert {s["grund"] for s in daten["seiten"][2:]} == {
        f"{GRUND_NACH_STOERUNG}: Abruf gestört (HTTP 403)"
    }


def test_drei_seiten_in_folge_mit_serverfehler_beenden_den_anbieter(
    o2, karte_o2, kombination
):
    adressen = [s.adresse for s in o2.seiten]
    uhr = Uhr()
    folgen = {a: [502, 502, 502] for a in adressen[:3]}
    crawler = Crawler(uhr, kombination, folgen)

    daten = _fahre(o2, karte_o2, crawler, uhr, Schlaf(uhr))

    assert len(crawler.aufrufe) == 9
    rest = daten["seiten"][3:]
    assert {s["status"] for s in rest} == {SEITE_NICHT_BESUCHT}
    assert {s["grund"] for s in rest} == {
        f"{GRUND_NACH_STOERUNG}: 3 Seiten in Folge mit Serverfehler: "
        "Abruf gestört (HTTP 502)"
    }
    assert daten["laufstatus"] == LAUF_GESTOERT


def test_gelesene_seite_dazwischen_setzt_die_folge_zurueck(o2, karte_o2, kombination):
    adressen = [s.adresse for s in o2.seiten]
    uhr = Uhr()
    folgen = {a: [502, 502, 502] for a in (adressen[0], adressen[1], adressen[3])}
    crawler = Crawler(uhr, kombination, folgen)

    daten = _fahre(o2, karte_o2, crawler, uhr, Schlaf(uhr))

    assert [s["status"] for s in daten["seiten"]] == [
        LAUF_GESTOERT,
        LAUF_GESTOERT,
        LAUF_GELESEN,
        LAUF_GESTOERT,
        LAUF_GELESEN,
    ]


def test_ohne_restzeit_fuer_die_pause_keine_wiederholung(o2, karte_o2, kombination):
    """Das Zeitbudget (CLAUDE.md Regel 8) geht vor: reicht die Restzeit nach der Pause
    nicht für eine Seite, bleibt es beim einen Versuch."""
    erste = o2.seiten[0].adresse
    uhr = Uhr()
    crawler = Crawler(uhr, kombination, {erste: [502]})
    schlaf = Schlaf(uhr)

    daten = _fahre(o2, karte_o2, crawler, uhr, schlaf, ende=4 * MINUTE)

    assert crawler.aufrufe.count(erste) == 1
    assert schlaf.pausen == []
    assert daten["seiten"][0]["ladung"] is None


def _uebersicht(adresse: str, status: int) -> dict:
    if status == 200:
        satz = {"art": "anschluss", "tarif_slug": "s", "anschlusspreis": 39.9}
        return {
            "adresse": adresse,
            "status": LAUF_GELESEN,
            "grund": None,
            "stoerung": None,
            "saetze": [satz],
            "vollstaendig": True,
        }
    stoerung = form(SimpleNamespace(haupt_status=status))
    return {
        "adresse": adresse,
        "status": LAUF_GESTOERT,
        "grund": abruf_gestoert(status),
        "stoerung": stoerung,
        "saetze": [],
        "vollstaendig": False,
    }


def test_uebersicht_mit_einem_502_wird_wiederholt_die_uebrigen_folgen(
    einsundeins, karte_1und1, kombination
):
    """Der Fall der Nacht: erste Tarifdetail-Seite 502, beim zweiten Versuch gelesen;
    die sechs übrigen Tarifdetail-Seiten und die Geräteübersicht folgen."""
    adressen = list(einsundeins.uebersichten)
    uhr = Uhr()
    folgen = {adressen[0]: [502]}
    aufrufe: list[str] = []

    def lies(adresse: str, ende: float) -> dict:
        aufrufe.append(adresse)
        uhr.jetzt += 5
        folge = folgen.get(adresse, [])
        return _uebersicht(adresse, folge.pop(0) if folge else 200)

    crawler = Crawler(uhr, kombination, {})
    daten = _fahre(einsundeins, karte_1und1, crawler, uhr, Schlaf(uhr), lies)

    assert aufrufe == [adressen[0], *adressen]
    assert [u["status"] for u in daten["uebersichten"]] == [LAUF_GELESEN] * len(
        adressen
    )
    assert daten["uebersichten"][0]["versuche"] == 2


@pytest.mark.parametrize(
    ("status", "art"),
    [
        (500, SERVERFEHLER),
        (502, SERVERFEHLER),
        (503, SERVERFEHLER),
        (599, SERVERFEHLER),
        (404, STOERUNG_SEITE),
        (403, None),
        (429, None),
        (202, None),
    ],
)
def test_art_der_stoerung_nach_dem_status_der_hauptseite(status, art):
    assert form(SimpleNamespace(haupt_status=status)) == art


def _robots(url: str) -> tuple[int, str]:
    return 200, "User-agent: *\nDisallow:\n" if "127.0.0.1" in url else "Disallow: /\n"


def test_uebersicht_im_browser_502_ist_ein_serverfehler(chromium, karte_1und1):
    """Echte Lesung (Tor, Wache, Lesart 1&1) gegen einen lokalen Server mit 502."""
    with klickserver(lambda pfad: html("Bad Gateway", 502)) as server:
        waechter = RobotsWaechter(hole=_robots)
        schleuse = Hostschleuse(waechter, lambda: JETZT)
        adresse = server.adresse("/details-all-net-flat-preisliste?chosenTariff=s")
        ergebnis = lies_uebersicht(
            chromium, adresse, karte_1und1, waechter, lambda: JETZT, schleuse=schleuse
        )

    assert (ergebnis["status"], ergebnis["http_status"]) == (LAUF_GESTOERT, 502)
    assert ergebnis["stoerung"] == SERVERFEHLER
    assert ergebnis["saetze"] == []


def test_leser_im_browser_wiederholt_einen_502_hoechstens_zweimal(
    chromium, einsundeins, karte_1und1, monkeypatch
):
    """Verdrahtung im Betrieb: der echte Übersichtsleser von ``leser_im_browser``
    fragt nach einem bleibenden 502 genau dreimal (Pausen im Test 0 s)."""
    from telco_radar.collect.geraete import klickwiederholung

    monkeypatch.setattr(klickwiederholung, "PAUSEN_SERVERFEHLER_S", (0.0, 0.0))
    monkeypatch.setattr(klickwiederholung, "MINDESTZEIT_NACH_PAUSE_S", 0)
    pfad = "/details-all-net-flat-preisliste?chosenTariff=s"
    with klickserver(lambda _pfad: html("Bad Gateway", 502)) as server:
        _, lies = leser_im_browser(
            chromium, einsundeins, karte_1und1, lambda: JETZT, _robots
        )
        ergebnis = lies(server.adresse(pfad), time.monotonic() + 120)

    assert server.mit(pfad) == [pfad] * 3
    assert (ergebnis["stoerung"], ergebnis["versuche"]) == (SERVERFEHLER, 3)
