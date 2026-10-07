"""Klick-Karte Format 2, Stufe 4 im Lader: ``weiter`` und Kacheln, ohne Browser.

1&1 zeigt die Laufzeit erst nach „Weiter zur Tarifauswahl“ als Kacheln (Erkundung
07.10.2026, Commit c8ce1f77, Seiten 3/4); „24+12“ zählt als 36 Monate. Die Karten
hier sind Beispiele. Gegenproben: jede Form, die der Weiter-Schritt nicht lesen kann,
lehnt der Lader mit Feld und Grund ab, auch einen zweiten Klick auf der Folgeseite
(``oeffnen``, ``schliessen``) und Textmuster mit eigenem Selektor, die sonst für jede
Kachel den ersten Treffer läsen (Prüferbefunde zu 6b9c3dd0).
"""

from __future__ import annotations

import copy

import pytest

from telco_radar.collect.geraete.klickantwort import monate
from telco_radar.collect.geraete.klickkarte import (
    KlickkartenFehler,
    Weiterschritt,
    klickkarte_aus_daten,
)
from telco_radar.collect.geraete.klickkartentypen import (
    GRUND_DIMENSION,
    GRUND_KACHEL_BEREICH,
    GRUND_KACHEL_KNOPF,
    GRUND_KACHEL_MARKE,
    GRUND_KACHEL_MUSTER,
    GRUND_WEITER_ADRESSEN,
    GRUND_WEITER_KLICK,
)

KACHEL = "#kacheln > div.kachel"
MARKE = {"passt": ".aktiv"}
EIGENES_MUSTER = {"selektor": "#rate", "muster": r"(\d+,\d{2})"}
BASIS = {
    "anbieter": "Beispielanbieter",
    "knoepfe": {
        "speicher": {
            "selektor": "#speicher button",
            "gewaehlt": {"attribut": "aria-pressed", "wert": "true"},
        },
        "tarif": {"fest": "S"},
        "laufzeit": {"selektor": KACHEL, "wert_in": "button", "wert": "data-linkid"},
    },
    "weiter": {"selektor": "#weiter button", "text": "Weiter", "kacheln": "laufzeit"},
    "zusammenfassung": {"selektor": KACHEL},
    "antwort": {
        "global": "preise",
        "pfade": {"rate": "preise.rate"},
        "variante": {"laufzeit": "preise.dauer"},
    },
    "kanarie": {"selektor": "#kanarie", "enthaelt": "Beispielhandy X"},
}


def _lade(**teile):
    daten = copy.deepcopy(BASIS)
    for pfad, wert in teile.items():
        ort = daten
        *weg, letzter = pfad.split("__")
        for schluessel in weg:
            ort = ort[schluessel]
        if wert is None:
            del ort[letzter]
        else:
            ort[letzter] = copy.deepcopy(wert)
    return klickkarte_aus_daten(daten, "Prüfkarte")


def _fehler(**teile) -> tuple[str, str]:
    with pytest.raises(KlickkartenFehler) as fehler:
        _lade(**teile)
    return fehler.value.feld, fehler.value.grund


def test_weiter_mit_kacheln_ohne_marke():
    karte = _lade()

    assert karte.weiter == Weiterschritt("#weiter button", "Weiter", "laufzeit")
    assert karte.kacheldimension == "laufzeit"
    assert karte.knoepfe["laufzeit"].marke is None


def test_gegenprobe_ohne_weiter_braucht_die_laufzeit_eine_marke():
    karte = _lade(
        weiter=None,
        knoepfe__speicher__gewaehlt=None,
        knoepfe__gewaehlt={"attribut": "aria-pressed", "wert": "true"},
    )

    assert karte.weiter is None
    assert karte.kacheldimension is None
    feld, _ = _fehler(weiter=None)
    assert feld == "knoepfe.gewaehlt"


@pytest.mark.parametrize(
    ("teile", "feld", "grund"),
    [
        (
            {"weiter__kacheln": "farbe", "knoepfe__laufzeit__gewaehlt": MARKE},
            "weiter.kacheln",
            f"{GRUND_DIMENSION} farbe",
        ),
        (
            {"knoepfe__laufzeit": {"fest": 24}},
            "knoepfe.laufzeit",
            GRUND_KACHEL_KNOPF,
        ),
        (
            {"knoepfe__laufzeit__gewaehlt": MARKE},
            "knoepfe.laufzeit.gewaehlt",
            GRUND_KACHEL_MARKE,
        ),
        (
            {"zusammenfassung": {"selektor": "#preis"}},
            "zusammenfassung.selektor",
            GRUND_KACHEL_BEREICH,
        ),
        (
            {"zusammenfassung__selektor": [KACHEL, "#preis"]},
            "zusammenfassung.selektor",
            GRUND_KACHEL_BEREICH,
        ),
        (
            {"knoepfe__tarif": {"adressen": {"selektor": "a", "parameter": "t"}}},
            "weiter",
            GRUND_WEITER_ADRESSEN,
        ),
        (
            {"zusammenfassung__oeffnen": "#mehr"},
            "zusammenfassung.oeffnen",
            GRUND_WEITER_KLICK,
        ),
        (
            {"zusammenfassung__schliessen": "#zu"},
            "zusammenfassung.schliessen",
            GRUND_WEITER_KLICK,
        ),
        (
            {"zusammenfassung__muster": {"rate": EIGENES_MUSTER}},
            "zusammenfassung.muster.rate",
            GRUND_KACHEL_MUSTER,
        ),
    ],
    ids=[
        "dimension",
        "fest",
        "marke",
        "bereich",
        "zweiter-bereich",
        "adressen",
        "oeffnen",
        "schliessen",
        "muster-selektor",
    ],
)
def test_gegenprobe_ungueltiger_weiter_schritt(teile, feld, grund):
    assert _fehler(**teile) == (feld, grund)


def test_gegenprobe_unbekanntes_feld_im_weiter_schritt():
    feld, grund = _fehler(weiter__klicke={"zweimal": True})

    assert feld.startswith("weiter")
    assert "klicke" in f"{feld} {grund}"


def test_gegenprobe_weiter_ohne_text():
    assert _fehler(weiter__text=None)[0] == "weiter.text"


@pytest.mark.parametrize(
    ("roh", "erwartet"),
    [("24+12", 36), (" 24 + 12 ", 36), ("24", 24), (36, 36), ("24+x", None)],
)
def test_monate_mit_summe(roh, erwartet):
    assert monate(roh) == erwartet


def test_textmuster_ohne_eigenen_selektor_liest_in_der_kachel():
    karte = _lade(zusammenfassung__muster={"rate": EIGENES_MUSTER["muster"]})

    assert karte.textlesung.muster["rate"].selektor is None
    assert karte.textlesung.selektoren == (KACHEL,)
