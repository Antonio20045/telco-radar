"""Klick-Karte Format 2: ``antwort.platzhalter`` verbindet Werte derselben Antwort.

Telekom ``/v2/details`` (Klick-Erkundung 07.10.2026) nennt je Laufzeit drei
Anzahlungsstufen; welcher Ratenplan gilt, folgt erst aus Laufzeit und der Anzahlung,
die die Seite zeigt. Ein benannter Pfad liest die Plan-Kennung, die Wertpfade filtern
mit ihr. Die Karte und die Antwort hier sind Beispiele; ``NUTZLAST`` hat zwei
Anzahlungsstufen bei 24 Monaten und eine bei 36, jede mit eigenem Plan.
"""

from __future__ import annotations

import copy

import pytest

from telco_radar.collect.geraete.klickantwort import lies_antwort
from telco_radar.collect.geraete.klickkarte import (
    KlickkartenFehler,
    klickkarte_aus_daten,
)

PLAN = "preise[art=anzahlung][monate={laufzeit}][betrag={anzahlung_seite}].plan"
BASIS = {
    "anbieter": "Beispielanbieter",
    "knoepfe": {
        "speicher": {"selektor": "#speicher button"},
        "tarif": {"selektor": "#tarif button"},
        "laufzeit": {"selektor": "#laufzeit button"},
        "gewaehlt": {"attribut": "aria-checked", "wert": "true"},
    },
    "seite": {"anzahlung_seite": {"selektor": "#laufzeit [aria-checked=true]"}},
    "zusammenfassung": {"selektor": "#preis"},
    "antwort": {
        "url_muster": "/details",
        "laden": True,
        "platzhalter": {"plan": PLAN},
        "pfade": {
            "rate": "preise[art=rate][plan={plan}].betrag",
            "anzahlung": "preise[art=anzahlung][plan={plan}].betrag",
            "anschluss": "anschluss",
        },
        "variante": {"speicher": "speicher"},
    },
    "kanarie": {"selektor": "#kanarie", "enthaelt": "Beispielhandy X"},
}
NUTZLAST = {
    "speicher": "256 GB",
    "anschluss": 39.95,
    "preise": [
        {"art": "anzahlung", "monate": "24", "betrag": 99.0, "plan": "p-24-1"},
        {"art": "anzahlung", "monate": "24", "betrag": 199.0, "plan": "p-24-2"},
        {"art": "anzahlung", "monate": "36", "betrag": 99.0, "plan": "p-36-1"},
        {"art": "rate", "plan": "p-24-1", "betrag": 40.4},
        {"art": "rate", "plan": "p-24-2", "betrag": 36.2},
        {"art": "rate", "plan": "p-36-1", "betrag": 26.9},
    ],
}


def _karte(**antwort):
    daten = copy.deepcopy(BASIS)
    for teil, wert in antwort.items():
        if wert is None:
            del daten["antwort"][teil]
        else:
            daten["antwort"][teil] = wert
    return klickkarte_aus_daten(daten, "Prüfkarte")


def _fehler(**antwort) -> str:
    with pytest.raises(KlickkartenFehler) as fehler:
        _karte(**antwort)
    return fehler.value.feld


def _lies(karte, laufzeit, anzahlung):
    platz = {"speicher": "256 GB", "laufzeit": laufzeit, "anzahlung_seite": anzahlung}
    return lies_antwort(NUTZLAST, karte.antwort, None, platz).werte


def test_karte_traegt_benannte_pfade():
    assert _karte().antwort.platzhalter == {"plan": PLAN}


def test_ohne_benannten_pfad_ist_der_platzhalter_unbekannt():
    """Gegenprobe: ``{plan}`` ist ohne ``platzhalter`` kein Name der Karte."""
    assert _fehler(platzhalter=None) == "antwort.pfade.rate"


@pytest.mark.parametrize(
    ("laufzeit", "anzahlung", "rate", "gezahlt"),
    [("24", "99", 40.4, 99.0), ("24", "199", 36.2, 199.0), ("36", "99", 26.9, 99.0)],
)
def test_plan_folgt_aus_laufzeit_und_anzahlung_der_seite(
    laufzeit, anzahlung, rate, gezahlt
):
    werte = _lies(_karte(), laufzeit, anzahlung)

    assert (werte.rate, werte.anzahlung, werte.anschluss) == (rate, gezahlt, 39.95)


@pytest.mark.parametrize(("laufzeit", "anzahlung"), [("24", None), ("36", "199")])
def test_ohne_eindeutigen_plan_bleiben_seine_felder_leer(laufzeit, anzahlung):
    """Fehlt die Anzahlung der Seite oder gibt es sie nicht, gibt es keinen Plan:
    Rate und Anzahlung ``None``, nie 0 und nie die eines anderen Plans."""
    werte = _lies(_karte(), laufzeit, anzahlung)

    assert (werte.rate, werte.anzahlung, werte.anschluss) == (None, None, 39.95)


def test_ohne_anzahlung_im_filter_ist_der_plan_mehrdeutig():
    """Gegenprobe: die Laufzeit allein trifft bei 24 Monaten zwei Pläne."""
    nur_laufzeit = {"plan": "preise[art=anzahlung][monate={laufzeit}].plan"}

    karte = _karte(platzhalter=nur_laufzeit)

    assert _lies(karte, "24", "199").rate is None
    assert _lies(karte, "36", "99").rate == 26.9


@pytest.mark.parametrize(
    ("platzhalter", "gemeldet"),
    [
        ({"Plan": PLAN}, "antwort.platzhalter.Plan"),
        ({"laufzeit": PLAN}, "antwort.platzhalter.laufzeit"),
        ({"anzahlung_seite": PLAN}, "antwort.platzhalter.anzahlung_seite"),
        ({"plan": "preise[art=x][monate={farbe}].plan"}, "antwort.platzhalter.plan"),
        ({"plan": "preise[art=x"}, "antwort.platzhalter.plan"),
        ({"plan": PLAN, "zweit": "p[id={plan}].x"}, "antwort.platzhalter.zweit"),
        ({}, "antwort.platzhalter"),
        (["plan"], "antwort.platzhalter"),
    ],
)
def test_kaputter_platzhalter_wirft_mit_punktpfad(platzhalter, gemeldet):
    assert _fehler(platzhalter=platzhalter) == gemeldet
