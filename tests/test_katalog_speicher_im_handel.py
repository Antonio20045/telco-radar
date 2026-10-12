"""Katalog-Speicher, die keine deutsche Anbieterseite zeigt, fehlen im Katalog.

Klick-Lauf 12.10.2026 (Preisprüfung 11.10.2026, Punkt c): keine Seite von Telekom,
Vodafone, o2, congstar oder 1&1 zeigt iPhone 17e mit 128 GB oder Pixel 11 Pro, Pixel 11
Pro XL und Galaxy Z Fold8 mit 1 TB, auch nicht als gesperrten Knopf. Ein solcher
Katalog-Speicher stünde auf der Geräteseite als Lücke bei allen Anbietern.
"""

from __future__ import annotations

import pytest
from bestand_pfad import lese_wurzel

from telco_radar.geraete_config import lade_katalog

NICHT_IM_HANDEL = {
    "apple-iphone-17e": 128,
    "google-pixel-11-pro": 1024,
    "google-pixel-11-pro-xl": 1024,
    "samsung-galaxy-z-fold8": 1024,
}


@pytest.fixture(scope="module")
def speicher():
    katalog = lade_katalog(lese_wurzel())
    return {g.device_id: set(g.speicher) for g in katalog.geraete}


@pytest.mark.parametrize("geraet", sorted(NICHT_IM_HANDEL))
def test_speicher_ohne_anbieter_steht_nicht_im_katalog(speicher, geraet):
    assert NICHT_IM_HANDEL[geraet] not in speicher[geraet]


def test_gegenprobe_angebotene_speicher_bleiben(speicher):
    assert {256, 512} <= speicher["apple-iphone-17e"]
    assert {256, 512} <= speicher["samsung-galaxy-z-fold8"]
