"""Klick-Übersicht: ein erneuertes Gerät bleibt erneuert.

Telekom-Übersicht MagentaMobil M, Klick-Tageslauf 09.10.2026 18:30 UTC: „Apple iPhone
14 (Erneuert Premium) 128 GB“ stand auf der Geräteseite als neues iPhone 14 im
Vergleich. Der Zustand ist eine Preisdimension in der ``sku_id``; verglichen wird nur
``neu``.
"""

from __future__ import annotations

import pytest
from bestand_pfad import lese_wurzel

from telco_radar.collect.geraete.klicklauf import LAUF_GELESEN
from telco_radar.collect.geraete.klickrohsatz import ausbeute
from telco_radar.geraete_config import lade_katalog

ADRESSE = "https://www.telekom.de/shop/geraete/smartphones?tariffId=MF_17791"


@pytest.fixture(scope="module")
def katalog():
    return lade_katalog(lese_wurzel())


def _satz(titel: str) -> dict:
    return {
        "titel": titel,
        "speicher_gb": 128,
        "tarif_name": "MagentaMobil M",
        "tarif_slug": "MF_17791",
        "tarif_monatlich": 49.95,
        "geraet_zuzahlung": 1.0,
        "geraet_monatsrate": 11.6,
        "anschlusspreis": 39.95,
        "laufzeit_monate": 36,
        "url": "https://www.telekom.de/shop/geraet/apple/apple-iphone-14/x-128-gb",
    }


def _daten(*titel: str) -> dict:
    uebersicht = {
        "adresse": ADRESSE,
        "status": LAUF_GELESEN,
        "grund": None,
        "saetze": [_satz(t) for t in titel],
        "beleg": {"seite": ADRESSE, "zeitpunkt": "2026-10-09T18:30:59Z"},
    }
    return {
        "name": "Telekom",
        "datum": "2026-10-09",
        "seiten": [],
        "uebersichten": [uebersicht],
    }


def test_erneuertes_geraet_traegt_seinen_zustand(katalog):
    aus = ausbeute(_daten("Apple iPhone 14 (Erneuert Premium) 128 GB"), katalog)
    [satz] = aus.rohsaetze
    assert satz["device_id"] == "apple-iphone-14"
    assert satz["zustand"] == "refurbished"
    assert satz["sku_id"].endswith("-refurbished")


def test_neues_geraet_bleibt_neu(katalog):
    aus = ausbeute(_daten("Apple iPhone 14 128 GB"), katalog)
    [satz] = aus.rohsaetze
    assert satz["zustand"] == "neu"
    assert not satz["sku_id"].endswith("-refurbished")
