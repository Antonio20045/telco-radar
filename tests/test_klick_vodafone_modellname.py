"""Vodafone-Produktseiten: der Kanarienwert trägt den Namen, den Vodafone zeigt.

Klick-Lauf 12.10.2026: Galaxy S26 Plus, Z Flip7, Z Fold7, Redmi 17, Redmi Note 17 und
Note 17 Pro brachen ab mit „Kanarienwert fehlt: … ohne ‚Galaxy S26 Plus‘“; Vodafone
nennt die Geräte wie in der Geräteliste vom 11.10.2026 (``titel_roh``), etwa „Samsung
Galaxy S26+“ und „Xiaomi REDMI 17 5G“. Drei solche Seiten zuerst hielten vodafone-2
und vodafone-3 mit je 11 Seiten an.
"""

from __future__ import annotations

import pytest
from bestand_pfad import lese_wurzel

from telco_radar.collect.geraete.klickziele import TAGESDATEI, lade_ziele

TITEL = {
    "samsung-galaxy-s26-plus": "Samsung Galaxy S26+ 256 GB Cobalt Violet",
    "samsung-galaxy-z-flip-7": "Samsung Galaxy Z Flip7 256 GB Jetblack",
    "samsung-galaxy-z-fold-7": "Samsung Galaxy Z Fold7 256 GB Jetblack",
    "xiaomi-redmi-17": "Xiaomi REDMI 17 5G 128 GB Deep Blue",
    "xiaomi-redmi-note-17": "Xiaomi REDMI Note 17 5G 128 GB Black",
    "xiaomi-redmi-note-17-pro": "Xiaomi REDMI Note 17 Pro 5G 256 GB Black",
}


@pytest.fixture(scope="module")
def seiten():
    alle = lade_ziele(lese_wurzel(), TAGESDATEI, hoechste=None)
    vodafone = [z for z in alle if z.name == "Vodafone"]
    return {s.geraet: s for z in vodafone for s in z.seiten}


@pytest.mark.parametrize("geraet", sorted(TITEL))
def test_kanarienname_steht_im_vodafone_titel(seiten, geraet):
    assert seiten[geraet].modell in TITEL[geraet]


def test_gegenprobe_katalogname_fehlt_im_titel():
    assert "Galaxy S26 Plus" not in TITEL["samsung-galaxy-s26-plus"]
    assert "Redmi 17" not in TITEL["xiaomi-redmi-17"]
