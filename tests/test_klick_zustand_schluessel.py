"""Ein erneuertes Gerät ist kein zweiter Wert für das neue.

Telekom, Klick-Tageslauf 10.10.2026: „Apple iPhone 15 128 GB“ und „Apple iPhone 15
Erneuert 128 GB“ standen in jeder Übersicht. Beide trafen denselben Schlüssel (Anbieter,
Gerät, Speicher, Tarif, Ratenzahl) mit verschiedenen Raten, und die Zusammenführung
verwarf beide als ``mehrdeutig``. Der Zustand zählt jetzt im Schlüssel mit; ein
erneuertes Gerät ersetzt nie einen neuen Adaptersatz. Datum fest.
"""

from __future__ import annotations

import pytest
from bestand_pfad import lese_wurzel

from telco_radar.analyze.klick_zusammenfuehrung import fuehre_zusammen
from telco_radar.collect.geraete.klicklauf import LAUF_GELESEN
from telco_radar.geraete_config import lade_katalog

TAG = "2026-10-10"
ADRESSE = "https://www.telekom.de/shop/geraete/smartphones?tariffId=MF_17791"


@pytest.fixture(scope="module")
def katalog():
    return lade_katalog(lese_wurzel())


def _satz(titel: str, rate: float) -> dict:
    return {
        "titel": titel,
        "speicher_gb": 128,
        "tarif_name": "MagentaMobil M",
        "tarif_slug": "MF_17791",
        "tarif_monatlich": 49.95,
        "geraet_zuzahlung": 1.0,
        "geraet_monatsrate": rate,
        "anschlusspreis": 39.95,
        "laufzeit_monate": 36,
        "url": "https://www.telekom.de/shop/geraet/apple/apple-iphone-15/x-128-gb",
    }


def _datei() -> dict:
    saetze = [
        _satz("Apple iPhone 15 128 GB", 16.0),
        _satz("Apple iPhone 15 Erneuert 128 GB", 12.4),
    ]
    uebersicht = {
        "adresse": ADRESSE,
        "status": LAUF_GELESEN,
        "grund": None,
        "saetze": saetze,
        "vollstaendig": True,
        "unvollstaendig": None,
    }
    return {
        "anbieter": "telekom",
        "name": "Telekom",
        "datum": TAG,
        "format": 1,
        "laufstatus": LAUF_GELESEN,
        "grund": None,
        "seiten": [],
        "uebersichten": [uebersicht],
    }


def _adapter(sku: str) -> dict:
    return {
        "sku_id": sku,
        "anbieter": "Telekom",
        "zustand": "neu",
        "speicher_gb": 128,
        "tarif_name": "MagentaMobil M",
        "tarif_slug": "MF_17791",
        "laufzeit_monate": 36,
        "geraet_monatsrate": 16.5,
    }


def _geraet(sku: str) -> tuple[str, int | None]:
    return ("apple-iphone-15", 128) if sku.startswith("apple-iphone-15") else ("", None)


def test_neu_und_erneuert_bleiben_beide(katalog):
    zug = fuehre_zusammen([], [_datei()], katalog, TAG, _geraet)
    raten = {(s["zustand"], s["geraet_monatsrate"]) for s in zug.rohsaetze}
    assert raten == {("neu", 16.0), ("refurbished", 12.4)}
    assert zug.bilanz["mehrdeutig"] == []


def test_erneuert_ersetzt_keinen_neuen_adaptersatz(katalog):
    adapter = [_adapter("apple-iphone-15-128gb-blau")]
    zug = fuehre_zusammen(adapter, [_datei()], katalog, TAG, _geraet)
    neu = [s for s in zug.rohsaetze if s["zustand"] == "neu"]
    erneuert = [s for s in zug.rohsaetze if s["zustand"] == "refurbished"]
    assert [s["geraet_monatsrate"] for s in neu] == [16.0]
    assert [s["geraet_monatsrate"] for s in erneuert] == [12.4]
