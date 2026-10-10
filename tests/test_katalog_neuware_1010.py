"""Neuware vom 09.10.2026 im Katalog: jeder Anbietertitel findet sein Gerät."""

import pytest
from bestand_pfad import lese_wurzel

from telco_radar.geraete_config import lade_katalog
from telco_radar.geraete_model import erkenne_geraet

TITEL = [
    ("HONOR 600", "honor-600"),
    ("HONOR Magic V6", "honor-magic-v6"),
    ("HONOR Magic8 Lite", "honor-magic8-lite"),
    ("Motorola moto g77", "motorola-moto-g77"),
    ("motorola moto g77 256 GB", "motorola-moto-g77"),
    ("Motorola razr 70", "motorola-razr-70"),
    ("Samsung Galaxy S25 Edge", "samsung-galaxy-s25-edge"),
    ("Xiaomi REDMI 17C | 5G", "xiaomi-redmi-17c"),
    ("Samsung Galaxy A26 5G 128 GB", "samsung-galaxy-a26"),
    ("Samsung Galaxy A36 5G 256 GB", "samsung-galaxy-a36"),
    (
        "Samsung Galaxy XCover7 Enterprise Edition 128 GB",
        "samsung-galaxy-xcover-7-ee",
    ),
    ("Samsung Galaxy Xcover 7 EE", "samsung-galaxy-xcover-7-ee"),
    (
        "Samsung Galaxy XCover7 Pro Enterprise Edition 128 GB",
        "samsung-galaxy-xcover7-pro-ee",
    ),
    ("Samsung Galaxy XCover7 Pro EE", "samsung-galaxy-xcover7-pro-ee"),
    ("Telekom T Phone 3 128 GB", "telekom-t-phone-3"),
    ("Telekom T Phone 3 Pro 256 GB", "telekom-t-phone-3-pro"),
    ("Xiaomi 15T 256 GB", "xiaomi-15t"),
    ("Xiaomi Redmi Note 15 Pro+ 5G 256 GB", "xiaomi-redmi-note-15-pro-plus"),
    ("Fairphone (Gen. 6+) 256 GB", "fairphone-6-plus"),
    ("Motorola edge 70 512 GB", "motorola-edge-70"),
    ("motorola edge 70 fusion 256 GB", "motorola-edge-70-fusion"),
    (
        "motorola edge 70 fusion FIFA Edition 256 GB",
        "motorola-edge-70-fusion-fifa-edition",
    ),
    ("motorola edge 60 neo 256 GB", "motorola-edge-60-neo"),
    ("motorola moto g37 128 GB", "motorola-moto-g37"),
    ("motorola razr fold 512 GB", "motorola-razr-fold"),
    ("motorola razr fold FIFA Edition 512 GB", "motorola-razr-fold-fifa-edition"),
    ("motorola signature 512 GB", "motorola-signature"),
]

GEGENPROBE = [
    ("Samsung Galaxy S25 256 GB", "samsung-galaxy-s25"),
    ("Fairphone (Gen. 6) 256 GB", "fairphone-6"),
    ("Xiaomi Redmi Note 15 Pro 5G 256 GB", "xiaomi-redmi-note-15-pro"),
    ("Xiaomi 15 256 GB", "xiaomi-15"),
    ("Xiaomi REDMI 17 5G 128 GB", "xiaomi-redmi-17"),
]


@pytest.fixture(scope="module")
def katalog():
    return lade_katalog(lese_wurzel())


@pytest.mark.parametrize(("titel", "erwartet"), TITEL + GEGENPROBE)
def test_titel_findet_sein_geraet(katalog, titel, erwartet):
    geraet = erkenne_geraet(titel, katalog)
    assert geraet is not None
    assert geraet.device_id == erwartet


def test_erneuerte_ware_bleibt_draussen(katalog):
    assert erkenne_geraet("Apple iPhone 13 (Erneuert Basic) 128 GB", katalog) is None
