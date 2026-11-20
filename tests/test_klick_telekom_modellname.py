"""Telekom-Produktseiten: der Kanarienwert trägt den Namen, den Telekom zeigt.

Klick-Lauf 10.10.2026 21:12 UTC: Die Produktseite des Galaxy S26 Plus brach ab mit
„Kanarienwert fehlt: … ohne ‚Galaxy S26 Plus‘“; Telekom nennt das Gerät „Samsung Galaxy
S26+“ (Übersichtstitel desselben Laufs). Die Störung hielt die übrigen 40 Seiten an.
Klick-Lauf 11.10.2026 19:31 UTC: das Energielabel nennt „Motorola edge 70“ nicht so
wie der Übersichtstitel; „edge 70“ steht in beiden Schreibweisen.
Seit 20.11.2026 kommen die Seiten aus den Kacheln der Übersichten
(``klickliste_kacheln``); jede nennt einen Namen, der im Kacheltitel steht.
"""

from __future__ import annotations

import json

import pytest
from bestand_pfad import KACHELN, kachel_wurzel

from telco_radar.collect.geraete.klickziele import TAGESDATEI, lade_ziele

TITEL = {
    "samsung-galaxy-s26-plus": ("Samsung Galaxy S26+", "Galaxy S26+"),
    "samsung-galaxy-z-fold-7": ("Samsung Galaxy Z Fold7", "Galaxy Z Fold7"),
    "motorola-edge-70": ("Motorola edge 70", "edge 70"),
    "motorola-moto-g37": ("motorola moto g37", "moto g37"),
    "fairphone-6": ("Fairphone 6", "Fairphone 6"),
}


@pytest.fixture(scope="module")
def seiten():
    alle = lade_ziele(kachel_wurzel(), TAGESDATEI, hoechste=None)
    telekom = [z for z in alle if z.name == "Telekom"]
    return [s for z in telekom for s in z.seiten]


@pytest.mark.parametrize("geraet", sorted(TITEL))
def test_kanarienname_steht_im_telekom_titel(seiten, geraet):
    titel, name = TITEL[geraet]
    modelle = {s.modell for s in seiten if s.geraet == geraet}
    assert modelle == {name}
    assert name in titel


def test_jeder_kanarienname_steht_in_seinem_kacheltitel(seiten):
    daten = json.loads(KACHELN.read_text(encoding="utf-8"))
    titel = {
        satz["url"]: satz["titel"]
        for u in daten["uebersichten"]
        for satz in u["saetze"]
    }
    assert seiten
    for seite in seiten:
        assert seite.modell in titel[seite.adresse], seite.adresse
