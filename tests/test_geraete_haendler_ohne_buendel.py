"""Saturn seit dem 05.09.2026: die TCO-Tafel zeigt fuer Haendler ohne
Tarifbuendel (Amazon, Expert, Saturn - QUELLEN_MAP.md §6) den echten
Geraetepreis, sobald einer erhoben ist - statt weiter "Beschaffung laeuft
seit ..." zu behaupten.

Der Befund, gegen den dieser Test gebaut ist: der erste gerenderte
Live-Stand nach dem Saturn-Adapter zeigte fuer iPhone 17 Pro 256 GB
GLEICHZEITIG eine echte Saturn-Linie im Zeitreihen-Graph UND den Satz
"Saturn — Beschaffung läuft seit 5. September 2026" in derselben
Legende darunter - zwei Antworten auf dieselbe Frage ("hat Saturn Daten zu
diesem Geraet?"), die sich widersprechen.
"""
from __future__ import annotations

import json

import pytest

from telco_radar.geraete_model import Geraet, Katalog
from telco_radar.report import geraete_tco_view as view
from telco_radar.report.geraete_tco_view import (
    HAENDLER_OHNE_BUENDEL, _haendler_ohne_buendel_preise,
)
from telco_radar.tarif_bezug import Tarifbestand

from test_geraete_tco_zustand import HEUTE, SKU_NEU, _buendel, _referenzen, _tarife

# ==========================================================================
# Die reine Funktion
# ==========================================================================

def test_ohne_jede_listung_ist_jeder_haendler_none():
    ergebnis = _haendler_ohne_buendel_preise([])
    assert ergebnis == {h: None for h in HAENDLER_OHNE_BUENDEL}


def test_saturn_mit_preis_wird_gefunden_amazon_und_expert_bleiben_leer():
    listungen = [
        {"anbieter": "Saturn", "preis_ohne_vertrag": 939.99, "zustand": "neu",
         "quelle_url": "https://www.saturn.de/de/product/x.html",
         "abgerufen_am": "2026-09-05"},
    ]
    ergebnis = _haendler_ohne_buendel_preise(listungen)
    assert ergebnis["Amazon"] is None
    assert ergebnis["Expert"] is None
    assert ergebnis["Saturn"] == {
        "preis": 939.99,
        "quelle_url": "https://www.saturn.de/de/product/x.html",
        "abgerufen_am": "2026-09-05",
    }


def test_der_guenstigste_von_zwei_farbvarianten_gewinnt():
    """Zwei Farbvarianten desselben Modells+Speichers sind zwei SKUs mit
    (meist) demselben oder aehnlichem Preis - die Karte zeigt EINE Zahl,
    und das ist die guenstigste, nicht die zuletzt gelesene."""
    listungen = [
        {"anbieter": "Saturn", "preis_ohne_vertrag": 1179.0, "zustand": "neu",
         "quelle_url": "https://www.saturn.de/tiefblau.html",
         "abgerufen_am": "2026-09-05"},
        {"anbieter": "Saturn", "preis_ohne_vertrag": 1099.0, "zustand": "neu",
         "quelle_url": "https://www.saturn.de/silber.html",
         "abgerufen_am": "2026-09-05"},
    ]
    ergebnis = _haendler_ohne_buendel_preise(listungen)
    assert ergebnis["Saturn"]["preis"] == 1099.0
    assert ergebnis["Saturn"]["quelle_url"] == "https://www.saturn.de/silber.html"


def test_refurbished_zaehlt_nicht_als_geraetepreis_dieses_haendlers():
    """`VERGLEICHBARE_ZUSTAENDE` gilt auch hier: ein Gebrauchtpreis ist
    eine andere Preisdimension und beantwortet nicht "was kostet das
    Neugeraet bei diesem Haendler"."""
    listungen = [
        {"anbieter": "Saturn", "preis_ohne_vertrag": 799.0,
         "zustand": "refurbished",
         "quelle_url": "https://www.saturn.de/x.html",
         "abgerufen_am": "2026-09-05"},
    ]
    assert _haendler_ohne_buendel_preise(listungen)["Saturn"] is None


def test_ein_haendler_ausserhalb_der_liste_wird_ignoriert():
    listungen = [
        {"anbieter": "Medimax", "preis_ohne_vertrag": 349.0, "zustand": "neu",
         "quelle_url": "https://example.de/x.html", "abgerufen_am": "2026-09-05"},
    ]
    ergebnis = _haendler_ohne_buendel_preise(listungen)
    assert set(ergebnis) == set(HAENDLER_OHNE_BUENDEL)
    assert all(v is None for v in ergebnis.values())


# ==========================================================================
# Der ganze Weg: `geraete_tco_view.aufbereiten()`
# ==========================================================================

def _katalog():
    return Katalog(geraete=[
        Geraet(hersteller="Apple", modell="iPhone 15",
              speicher=[128, 256], segment="premium"),
    ])


def _tarifbestand(tmp_path):
    pfad = tmp_path / "tarife.jsonl"
    pfad.write_text("\n".join(json.dumps(t) for t in _tarife()) + "\n",
                    encoding="utf-8")
    return Tarifbestand.aus_datei(pfad)


@pytest.fixture
def modell(tmp_path):
    """Ein Modell mit einem echten o2-Buendel (damit es ueberhaupt in
    `modelle["modelle"]` erscheint - siehe `geraete_tco_karten.modelle()`)
    UND einer Saturn-Listung derselben SKU."""
    buendel = [_buendel(SKU_NEU, 20.0)]
    referenzen = _referenzen()
    tarife = _tarifbestand(tmp_path).je_id
    eintraege = [
        {"sku_id": SKU_NEU, "device_id": "apple-iphone-15", "anbieter": "Saturn",
         "anbieter_typ": "handel", "speicher_gb": 128, "zustand": "neu",
         "preis_ohne_vertrag": 939.99,
         "quelle_url": "https://www.saturn.de/de/product/x.html",
         "abgerufen_am": "2026-09-05", "confidence": "hoch"},
    ]
    ergebnis = view.aufbereiten(buendel, referenzen, eintraege, _katalog(),
                               tarife=tarife, historie=None)
    treffer = [m for m in ergebnis["modelle"] if m["id"].startswith("apple-iphone-15")]
    assert len(treffer) == 1, "Das Modell muss ueber sein o2-Buendel erscheinen"
    return treffer[0]


def test_saturn_preis_landet_am_modell(modell):
    assert modell["haendler_ohne_buendel"]["Saturn"]["preis"] == 939.99
    assert modell["haendler_ohne_buendel"]["Amazon"] is None
    assert modell["haendler_ohne_buendel"]["Expert"] is None


def test_saturn_faellt_aus_der_liste_ohne_erfasste_zeitreihe(modell):
    assert "Saturn" not in modell["haendler_offen"]
    assert "Amazon" in modell["haendler_offen"]
    assert "Expert" in modell["haendler_offen"]


def test_ohne_saturn_listung_bleiben_alle_drei_offen(tmp_path):
    buendel = [_buendel(SKU_NEU, 20.0)]
    tarife = _tarifbestand(tmp_path).je_id
    ergebnis = view.aufbereiten(buendel, _referenzen(), [], _katalog(),
                               tarife=tarife, historie=None)
    treffer = [m for m in ergebnis["modelle"] if m["id"].startswith("apple-iphone-15")][0]
    assert treffer["haendler_offen"] == list(HAENDLER_OHNE_BUENDEL)
    assert all(v is None for v in treffer["haendler_ohne_buendel"].values())
