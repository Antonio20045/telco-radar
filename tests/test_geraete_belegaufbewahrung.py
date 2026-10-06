"""Aufbewahrung der Belegdateien (Datenkonzept Geräteradar, Abschnitt 10), feste Daten.

Stichtag und Zeitpunkte sind fest; kein Test hängt vom heutigen Datum ab.
"""

from __future__ import annotations

from datetime import date

from belegbau import beleg

from telco_radar.collect.geraete.belegablage import LokaleAblage
from telco_radar.collect.geraete.belegarchiv import raeume_auf
from telco_radar.collect.geraete.belegaufbewahrung import (
    ERSTER,
    LOESCHEN,
    TAEGLICH,
    WERTAENDERUNG,
    WOCHENBELEG,
    aufbewahrung,
)

STICHTAG = date(2026, 10, 3)
X = {"rate": 25.0}
Y = {"rate": 24.0}
FOLGE = [
    ("a1", "2026-05-01T05:00:00Z", X, {}),
    ("a2", "2026-05-02T05:00:00Z", X, {}),
    ("b1", "2026-05-02T05:00:00Z", X, {"tarif": "M"}),
    ("a3", "2026-05-05T05:00:00Z", X, {}),
    ("a4", "2026-05-06T05:00:00Z", X, {}),
    ("a5", "2026-05-07T05:00:00Z", Y, {}),
    ("a6", "2026-05-08T05:00:00Z", Y, {}),
    ("a7", "2026-05-12T05:00:00Z", X, {}),
    ("a8", "2026-07-04T05:00:00Z", X, {}),
    ("a9", "2026-07-05T05:00:00Z", X, {}),
    ("a10", "2026-07-06T05:00:00Z", X, {}),
    ("a11", "2026-10-03T04:00:00Z", X, {}),
]
ERWARTET = {
    "a1": ERSTER,
    "a2": LOESCHEN,
    "b1": ERSTER,
    "a3": WOCHENBELEG,
    "a4": LOESCHEN,
    "a5": WERTAENDERUNG,
    "a6": LOESCHEN,
    "a7": WERTAENDERUNG,
    "a8": WOCHENBELEG,
    "a9": LOESCHEN,
    "a10": TAEGLICH,
    "a11": TAEGLICH,
}


def _belege():
    return [beleg(zeit, werte, kennung, **v) for kennung, zeit, werte, v in FOLGE]


def test_aufbewahrung_nach_abschnitt_10():
    entscheidungen = aufbewahrung(_belege(), STICHTAG)

    assert [e.beleg_id for e in entscheidungen] == [k for k, *_ in FOLGE]
    assert {e.beleg_id: e.grund for e in entscheidungen} == ERWARTET
    assert {e.beleg_id for e in entscheidungen if not e.behalten} == {
        "a2",
        "a4",
        "a6",
        "a9",
    }


def test_neunzig_tage_grenze_liegt_zwischen_tag_89_und_90():
    entscheidungen = {e.beleg_id: e for e in aufbewahrung(_belege(), STICHTAG)}

    assert (STICHTAG - date(2026, 7, 6)).days == 89
    assert entscheidungen["a10"].behalten
    assert (STICHTAG - date(2026, 7, 5)).days == 90
    assert not entscheidungen["a9"].behalten


def test_vor_neunzig_tagen_bleibt_alles_gegenprobe():
    entscheidungen = aufbewahrung(_belege(), date(2026, 5, 20))

    assert all(e.behalten for e in entscheidungen)
    assert entscheidungen[1].grund == TAEGLICH


def test_doppelter_beleg_zaehlt_einmal():
    belege = _belege()

    entscheidungen = aufbewahrung([*belege, belege[0]], STICHTAG)

    assert len(entscheidungen) == len(FOLGE)


def test_aufraeumen_loescht_nur_dateien_ohne_aufbewahrung(tmp_path):
    ablage = LokaleAblage(tmp_path)
    belege = _belege()
    for b in belege:
        tag = b.zeitpunkt[:10]
        for datei in (b.bild, b.mitschnitt):
            ablage.lege(f"beispielanbieter/{tag}/{datei.name}", b"x", datei.typ)

    entscheidungen = raeume_auf(belege, STICHTAG, ablage)

    for e in entscheidungen:
        for schluessel in e.dateien:
            assert (ablage.lies(schluessel) is not None) is e.behalten
    assert len([e for e in entscheidungen if not e.behalten]) == 4
