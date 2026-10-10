"""Telekom-Produktseiten: der Kanarienwert trägt den Namen, den Telekom zeigt.

Klick-Lauf 10.10.2026 21:12 UTC: Die Produktseite des Galaxy S26 Plus brach ab mit
„Kanarienwert fehlt: … ohne ‚Galaxy S26 Plus‘“; Telekom nennt das Gerät „Samsung Galaxy
S26+“ (Übersichtstitel desselben Laufs). Die Störung hielt die übrigen 40 Seiten an.
Jede Telekom-Seite nennt darum einen Namen, der im Telekom-Titel steht.
"""

from __future__ import annotations

import pytest
from bestand_pfad import lese_wurzel

from telco_radar.collect.geraete.klickziele import TAGESDATEI, lade_ziele

TITEL = {
    "samsung-galaxy-s26-plus": "Samsung Galaxy S26+",
    "samsung-galaxy-z-fold-7": "Samsung Galaxy Z Fold7",
    "samsung-galaxy-z-flip-7": "Samsung Galaxy Z Flip7",
    "motorola-moto-g77": "motorola moto g77",
    "xiaomi-redmi-note-15-pro-plus": "Xiaomi Redmi Note 15 Pro+ 5G",
}


@pytest.fixture(scope="module")
def seiten():
    alle = lade_ziele(lese_wurzel(), TAGESDATEI, hoechste=None)
    [telekom] = [z for z in alle if z.schluessel == "telekom"]
    return {s.geraet: s for s in telekom.seiten}


@pytest.mark.parametrize("geraet", sorted(TITEL))
def test_kanarienname_steht_im_telekom_titel(seiten, geraet):
    assert seiten[geraet].modell in TITEL[geraet]
