"""Gerätepreise ohne Tarif als Gegenprobe (``analyze.klick_geraetepreis``).

Klick-Seite: die echte Preisantwort ``virtualItem/226`` der Vodafone-Produktseite
iPhone 17 Pro, gelesen mit der eingefrorenen Produktseiten-Karte
(``fixtures/geraete/klickkarten_produktseite``; ``vodafone_virtualitem_iphone_17_pro_
20261007.json.gz``, 256 GB, 36 Raten: 1 € einmal, 33 € im Monat; Tarif ``unbekannt``).
Adapter-Seite: die echte Tarifantwort derselben Erkundung (``vodafone_tarif_hardware_
iphone_17_pro_20261007.json``, Anfrage 337), gelesen von ``vodafone.loese_tarifnamen``:
fünf Tarife, 36 Raten. Herkunft beider in ``tests/fixtures/geraete/_herkunft.json``.
Aus dem Klick wird kein Bündel; sein Gerätepreis ist gleich, abweichend (Rate 34 €)
oder ohne Gegenstück (24 Raten gegen eine Antwort nur mit 36).
"""

from __future__ import annotations

import gzip
import json
import logging
from dataclasses import replace
from pathlib import Path

import pytest
from bestand_pfad import lese_wurzel
from klickergebnisse import erfasst, ergebnisdatei, lauf

from telco_radar.analyze.klick_zusammenfuehrung import fuehre_zusammen
from telco_radar.collect.geraete.klickecho import lies_antwort
from telco_radar.collect.geraete.klickkartenprobe import GELADEN, lade_karte
from telco_radar.collect.geraete.klickziele import Seitenziel
from telco_radar.collect.geraete.vodafone import loese_tarifnamen
from telco_radar.geraete_config import lade_katalog
from telco_radar.report.geraete_tco_karten import geraet_aus_sku

HEUTE = "2026-10-07"
FIX = Path(__file__).parent / "fixtures" / "geraete"
KARTEN = Path(__file__).parent / "fixtures" / "geraete" / "klickkarten_produktseite"
PREISE = FIX / "vodafone_virtualitem_iphone_17_pro_20261007.json.gz"
TARIFE = FIX / "vodafone_tarif_hardware_iphone_17_pro_20261007.json"
URL = (
    "https://api.vodafone.de/glados/v2/hardware/v2/virtualItem/226"
    "?businessTransaction=newContract&salesChannel=Online.Consumer&financingType=rate"
)
SEITE = Seitenziel(
    "apple-iphone-17-pro",
    256,
    "https://www.vodafone.de/privat/handys/iphone-17-pro.html",
    None,
    "iPhone 17 Pro",
)
SKU = "apple-iphone-17-pro-256gb-cosmic-orange"


@pytest.fixture(scope="module")
def katalog():
    return lade_katalog(lese_wurzel())


@pytest.fixture(scope="module")
def karte():
    lage = lade_karte(KARTEN, "vodafone")
    assert (lage.status, lage.grund) == (GELADEN, None)
    return lage.karte


@pytest.fixture(scope="module")
def adapter() -> list[dict]:
    """Die fünf Adaptersätze der Tarifantwort, 36 Raten, zugeordnet wie im Sammler."""
    text = TARIFE.read_text(encoding="utf-8")
    roh = [
        {
            "quelle": "vodafone_buendel",
            "sku": "57562",
            "titel": "iPhone 17 Pro",
            "url": SEITE.adresse,
            "tarif_name": "",
            "tarif_slug": "vorschau",
        }
    ]
    loese_tarifnamen(lambda url, kopfzeilen: (200, text), {}, roh)
    saetze = [
        {**s, "anbieter": "Vodafone", "zustand": "neu", "sku_id": SKU} for s in roh
    ]
    assert {(s["laufzeit_monate"], s["geraet_zuzahlung"]) for s in saetze} == {
        (36, 1.0)
    }
    assert len(saetze) == 5 and {s["geraet_monatsrate"] for s in saetze} == {33.0}
    return saetze


def _datei(karte, speicher: str, laufzeit: str, **werte) -> dict:
    platz = {
        "speicher": speicher,
        "tarif": "unbekannt",
        "laufzeit": laufzeit,
        "farbe": "Cosmic Orange",
    }
    lesung = lies_antwort(
        json.loads(gzip.decompress(PREISE.read_bytes())), karte.antwort, URL, platz
    )
    lesung = replace(lesung, werte=replace(lesung.werte, **werte))
    kombination = erfasst(lesung, speicher, "unbekannt", laufzeit)
    seiten = [(SEITE, lauf(SEITE, [kombination]))]
    return ergebnisdatei("Vodafone", "vodafone", seiten, HEUTE)


def _geraet(katalog):
    return lambda sku: geraet_aus_sku(sku, katalog)


def _zusammen(katalog, adapter, datei):
    return fuehre_zusammen(adapter, [datei], katalog, HEUTE, _geraet(katalog))


def test_gleicher_geraetepreis_ohne_tarif(katalog, karte, adapter):
    zug = _zusammen(katalog, adapter, _datei(karte, "256 GB", "36"))

    assert zug.bilanz["gegenprobe_geraet"] == {
        "gleich": 1,
        "abweichend": 0,
        "ohne_gegenstueck": 0,
        "ohne_ratenzahl": 0,
        "beispiele": [],
    }
    assert zug.rohsaetze == adapter
    assert zug.bilanz["dateien"][0]["luecken"] == {"tarif_unbekannt": 1}


def test_abweichende_rate_steht_mit_beispiel_im_protokoll(
    katalog, karte, adapter, caplog
):
    caplog.set_level(logging.WARNING)

    zug = _zusammen(katalog, adapter, _datei(karte, "256 GB", "36", rate=34.0))

    probe = zug.bilanz["gegenprobe_geraet"]
    assert (probe["gleich"], probe["abweichend"]) == (0, 1)
    assert probe["beispiele"] == [
        "Vodafone|apple-iphone-17-pro|256|36: Klick 1.0 / 34.0, Adapter 1.0 / 33.0"
    ]
    assert "Gerätepreis ohne Tarif weicht ab" in caplog.text
    assert zug.rohsaetze == adapter


def test_ungelesene_anzahlung_wird_nicht_verglichen(katalog, karte, adapter):
    zug = _zusammen(katalog, adapter, _datei(karte, "256 GB", "36", anzahlung=None))

    assert zug.bilanz["gegenprobe_geraet"]["gleich"] == 1


def _zahlen(zug) -> tuple[int, int, int]:
    probe = zug.bilanz["gegenprobe_geraet"]
    return probe["gleich"], probe["abweichend"], probe["ohne_gegenstueck"]


def _zeile(caplog):
    (zeile,) = [r for r in caplog.records if "Gerätepreise ohne Tarif" in r.message]
    return zeile


def test_andere_ratenzahl_ist_ohne_gegenstueck_und_steht_im_protokoll(
    katalog, karte, adapter, caplog
):
    caplog.set_level(logging.INFO)

    zug = _zusammen(katalog, adapter, _datei(karte, "256 GB", "24"))

    assert _zahlen(zug) == (0, 0, 1)
    zeile = _zeile(caplog)
    assert zeile.levelno == logging.WARNING and "'ohne_gegenstueck': 1" in zeile.message


def test_gleich_steht_als_info_im_protokoll(katalog, karte, adapter, caplog):
    caplog.set_level(logging.INFO)

    _zusammen(katalog, adapter, _datei(karte, "256 GB", "36"))

    zeile = _zeile(caplog)
    assert zeile.levelno == logging.INFO and "'gleich': 1" in zeile.message


def test_unbekannte_ratenzahl_faellt_aus_dem_vergleich(katalog, karte, adapter):
    """Weder Ratenzahl noch Laufzeit gelesen, im Adapter keine Laufzeit: unbekannt
    gegen unbekannt ist kein Vergleich."""
    ohne = [{**s, "laufzeit_monate": None} for s in adapter]
    datei = _datei(karte, "256 GB", "36")
    (kombination,) = datei["seiten"][0]["kombinationen"]
    kombination["variante"]["laufzeit"] = None
    kombination["werte"]["ratenzahl"] = None

    zug = _zusammen(katalog, ohne, datei)

    probe = zug.bilanz["gegenprobe_geraet"]
    assert (probe["gleich"], probe["ohne_ratenzahl"]) == (0, 1)


@pytest.mark.parametrize(
    ("feld", "erwartet"),
    [("geraet_zuzahlung", (1, 0, 0)), ("geraet_monatsrate", (0, 0, 1))],
    ids=["ohne-anzahlung", "ohne-rate"],
)
def test_luecke_im_adapter_ist_keine_abweichung(
    katalog, karte, adapter, feld, erwartet
):
    """Ohne Anzahlung im Adapter zählt die Rate allein; ohne Rate ist der Satz kein
    Gegenstück. Eine Lücke ist nie eine Abweichung."""
    luecke = [{**s, feld: None} for s in adapter]

    zug = _zusammen(katalog, luecke, _datei(karte, "256 GB", "36"))

    assert _zahlen(zug) == erwartet


def test_ohne_dateien_leer(katalog, adapter):
    zug = fuehre_zusammen(adapter, [], katalog, HEUTE, _geraet(katalog))

    assert zug.bilanz["gegenprobe_geraet"] == {
        "gleich": 0,
        "abweichend": 0,
        "ohne_gegenstueck": 0,
        "ohne_ratenzahl": 0,
        "beispiele": [],
    }
