"""Lader des Weiter-Schritts mit ``klicken`` (Schnitt 8b Teil 1): genau eins von
``kacheln`` und ``klicken``; der geklickte Knopf braucht einen Selektor; kein zweiter
Klick in der Zusammenfassung. BEISPIEL-Karte aus ``test_geraete_klickfolgeklick``."""

from __future__ import annotations

import copy
import re

import pytest
from klickbeispiel import karte
from test_geraete_klickfolgeklick import KARTE

from telco_radar.collect.geraete.klickkarte import KlickkartenFehler, Weiterschritt
from telco_radar.collect.geraete.klickkartentypen import (
    GRUND_KLICKEN_KNOPF,
    GRUND_WEITER_DIMENSION,
    GRUND_WEITER_KLICK,
)


def _mit(**aenderung) -> dict:
    daten = copy.deepcopy(KARTE)
    for pfad, wert in aenderung.items():
        ort = daten
        *weg, letzter = pfad.split("__")
        for teil in weg:
            ort = ort.setdefault(teil, {})
        ort[letzter] = wert
    return daten


def test_klicken_laedt_und_braucht_keine_kacheln():
    geladen = karte(**KARTE)

    assert geladen.weiter == Weiterschritt(
        "#weiter a", "Zur Tarifauswahl", klicken="tarif"
    )
    assert geladen.weiter.dimension == "tarif"
    assert geladen.kacheldimension is None


@pytest.mark.parametrize(
    ("aenderung", "grund"),
    [
        ({"weiter__kacheln": "tarif"}, GRUND_WEITER_DIMENSION),
        ({"knoepfe__tarif": {"fest": "S"}}, GRUND_KLICKEN_KNOPF),
        (
            {"zusammenfassung": {"selektor": "#preis", "oeffnen": "#mehr"}},
            GRUND_WEITER_KLICK,
        ),
    ],
    ids=["beides", "fest", "oeffnen"],
)
def test_gegenprobe_ungueltiges_klicken(aenderung, grund):
    with pytest.raises(KlickkartenFehler, match=re.escape(grund)):
        karte(**_mit(**aenderung))
