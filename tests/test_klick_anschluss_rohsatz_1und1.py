"""1&1-Anschlusspreis im Klick-Rohsatz: gelesene Tarifdetail-Seite je Tarif-Slug.

Klick-Satz: Lesung der gespeicherten Produktseite (``tests/klickergebnisse.py``),
Anschluss aus ``einsundeins_tarifdetails_anf_s.html.gz`` über die Lesart der Übersicht.
Adaptersatz: ``einsundeins.lies_buendel`` samt ``ergaenze_bereitstellungsgebuehr``.
"""

from __future__ import annotations

import gzip
from dataclasses import replace

import pytest
from bestand_pfad import ZUSTAND, lese_wurzel
from klickergebnisse import (
    EINSUNDEINS_SEITE,
    FIX,
    einsundeins_lesung,
    erfasst,
    ergebnisdatei,
    lauf,
)
from test_klick_anschluss_1und1 import DETAILS_M, DETAILS_S, HEUTE

from telco_radar.analyze.klick_zusammenfuehrung import zusammenfuehren
from telco_radar.analyze.tco_buendel import aus_rohsaetzen
from telco_radar.collect.geraete.einsundeins import (
    ergaenze_bereitstellungsgebuehr,
    lies_buendel,
)
from telco_radar.collect.geraete.klickergebnis import schreibe
from telco_radar.collect.geraete.klicklauf import LAUF_GELESEN, LAUF_GESTOERT
from telco_radar.collect.geraete.klickrohsatz import ausbeute
from telco_radar.collect.geraete.klickuebersicht import LESARTEN
from telco_radar.geraete_config import lade_katalog
from telco_radar.geraete_model import sku_id
from telco_radar.report.geraete_tco_karten import geraet_aus_sku
from telco_radar.tarif_bezug import Tarifbestand


def _text(name: str) -> str:
    return gzip.decompress((FIX / name).read_bytes()).decode("utf-8")


@pytest.fixture(scope="module")
def katalog():
    return lade_katalog(lese_wurzel())


@pytest.fixture(scope="module")
def details() -> str:
    return _text("einsundeins_tarifdetails_anf_s.html.gz")


def _uebersicht(adresse: str, text: str, status: str = LAUF_GELESEN) -> dict:
    saetze = LESARTEN["1&1"].saetze(text, adresse) if status == LAUF_GELESEN else []
    return {"adresse": adresse, "status": status, "saetze": saetze}


def _klickdatei(*uebersichten: dict) -> dict:
    lesung = einsundeins_lesung()
    lesung = replace(lesung, buendel=replace(lesung.buendel, einmalzahlung=360.0))
    kombination = erfasst(lesung, "256", "tariff-anf-s-mvl", 36)
    seite = (EINSUNDEINS_SEITE, lauf(EINSUNDEINS_SEITE, [kombination]))
    daten = ergebnisdatei("1&1", "1und1", [seite], HEUTE, vertragsform="ein_vertrag")
    return {**daten, "uebersichten": list(uebersichten)}


def test_rohsatz_bekommt_anschluss_mit_gleichem_slug(katalog, details):
    aus = ausbeute(_klickdatei(_uebersicht(DETAILS_S, details)), katalog)

    (satz,) = aus.rohsaetze
    assert satz["anschlusspreis"] == 39.9
    assert satz["buendel_monatlich"] == 44.99
    assert dict(aus.luecken) == {}


@pytest.mark.parametrize(
    ("adresse", "status"),
    [(DETAILS_M, LAUF_GELESEN), (DETAILS_S, LAUF_GESTOERT)],
    ids=["anderer-slug", "nicht-gelesen"],
)
def test_ohne_gelesene_detailseite_bleibt_anschluss_offen(
    katalog, details, adresse, status
):
    aus = ausbeute(_klickdatei(_uebersicht(adresse, details, status)), katalog)

    (satz,) = aus.rohsaetze
    assert satz["anschlusspreis"] is None


def _adaptersatz(details: str) -> dict:
    html = _text("einsundeins_produktseite_iphone_17_pro.html.gz")
    (roh,) = [
        r
        for r in lies_buendel(html, EINSUNDEINS_SEITE.adresse)
        if r["speicher_gb"] == 256
    ]
    gesetzt = ergaenze_bereitstellungsgebuehr(
        lambda url, kopfzeilen=None: (200, details), {}, [roh]
    )
    assert gesetzt == 1 and roh["anschlusspreis"] == 39.9
    farbe = sku_id("apple-iphone-17-pro", 256, roh["farbe"])
    return {**roh, "anbieter": "1&1", "zustand": "neu", "sku_id": farbe}


@pytest.mark.parametrize("gelesen", [True, False], ids=["mit-details", "ohne"])
def test_36_monats_klicksatz_ersetzt_adaptersatz(katalog, details, tmp_path, gelesen):
    alt = _adaptersatz(details)
    uebersichten = [_uebersicht(DETAILS_S, details)] if gelesen else []
    schreibe(tmp_path / "1und1.json", _klickdatei(*uebersichten))

    zug = zusammenfuehren(
        [alt],
        tmp_path,
        lese_wurzel(),
        katalog,
        HEUTE,
        lambda sku: geraet_aus_sku(sku, katalog),
    )

    if not gelesen:
        assert zug.rohsaetze == [alt]
        assert zug.bilanz["unvollstaendig"]["felder"] == {"anschlusspreis": 1}
        return
    (satz,) = zug.rohsaetze
    assert satz["quelle_art"] == "klick" and satz["sku_id"] == alt["sku_id"]
    assert (satz["buendel_monatlich"], satz["geraet_zuzahlung"]) == (44.99, 360.0)
    assert satz["anschlusspreis"] == 39.9
    assert zug.bilanz["ersetzt"] == 1 and zug.bilanz["gegenprobe"]["gleich"] == 1
    bestand = Tarifbestand.aus_datei(ZUSTAND / "tarife.jsonl")
    (buendel,) = aus_rohsaetzen(zug.rohsaetze, bestand, HEUTE).buendel
    assert buendel.anschlusspreis == 39.9 and buendel.quelle_art == "klick"
