"""1&1-Kachel 24 im Bestand: aus dem Klick-Ergebnis ein Bündel mit 24 Raten.

Die Kachel „Weiter mit HW24“ der Folgeseite (Erkundung 07.10.2026, Commit c8ce1f77,
``einsundeins_bestellweg_laufzeit_20261007.json``) nennt 59,99 €/Mon. und keine
Einmalzahlung; seit dem 08.10.2026 bestätigt sie sich selbst (``klickkachel``). Der
Adaptersatz der gespeicherten Produktseite (``einsundeins.lies_buendel``, 08.09.2026)
nennt den Tarif „1&1 All-Net-Flat S“ mit dem Slug ``tariff-anf-s-mvl``, nur für 36
Raten. Erwartet: ein 1&1-Bündel mit 24 Raten mit Gerät, Speicher und Tarif des
Adapters, Bündelbetrag 59,99 € und der Einmalzahlung als Lücke, nie 360 €; daneben das
Bündel mit 36 Raten wie bisher. Gegenproben: ohne Adaptersatz bleibt der Tarif offen;
nennt der Klick den Tarif mit Namen, behält der Satz seine SKU.
"""

from __future__ import annotations

import gzip
from dataclasses import replace

import pytest
from bestand_pfad import ZUSTAND, lese_wurzel
from klickergebnisse import (
    EINSUNDEINS_KARTE,
    EINSUNDEINS_SEITE,
    FIX,
    einsundeins_kachel,
    einsundeins_lesung,
    erfasst,
    ergebnisdatei,
    lauf,
)

from telco_radar.analyze.klick_zusammenfuehrung import fuehre_zusammen
from telco_radar.analyze.tco_buendel import aus_rohsaetzen
from telco_radar.analyze.tco_store import TcoDB
from telco_radar.collect.geraete.einsundeins import lies_buendel
from telco_radar.collect.geraete.klickecho import variante_aus
from telco_radar.collect.geraete.klickkachel import QUELLE_KACHEL, kachel_echo
from telco_radar.collect.geraete.klicklauf import ERFASST, Kombiergebnis
from telco_radar.geraete_config import lade_katalog
from telco_radar.geraete_model import sku_id
from telco_radar.report.geraete_tco_karten import geraet_aus_sku
from telco_radar.tarif_bezug import Tarifbestand

HEUTE = "2026-10-08"
TARIF = "tariff-anf-s-mvl"


@pytest.fixture(scope="module")
def katalog():
    return lade_katalog(lese_wurzel())


@pytest.fixture(scope="module")
def bestand():
    return Tarifbestand.aus_datei(ZUSTAND / "tarife.jsonl")


def _adapter() -> dict:
    html = gzip.decompress(
        (FIX / "einsundeins_produktseite_iphone_17_pro.html.gz").read_bytes()
    ).decode("utf-8")
    (roh,) = [
        r
        for r in lies_buendel(html, EINSUNDEINS_SEITE.adresse)
        if r["speicher_gb"] == 256
    ]
    farbe = sku_id("apple-iphone-17-pro", 256, roh["farbe"])
    return {**roh, "anbieter": "1&1", "zustand": "neu", "sku_id": farbe}


def _kachel_24(tarif: str = TARIF) -> Kombiergebnis:
    """Die Kachel 24 wie der Klick-Crawler sie erfasst: Label und Text der Kachel."""
    label, gezeigt = einsundeins_kachel(0)
    variante = variante_aus("256", tarif, label)
    auswahl = ("laufzeit", label, label)
    echo = kachel_echo(
        variante, variante, auswahl, gezeigt, EINSUNDEINS_KARTE.entfallen
    )
    assert echo.stimmt, echo.befunde
    return Kombiergebnis(
        variante,
        ERFASST,
        buendel=echo.buendel,
        luecken=echo.luecken,
        auswahl=("256", tarif, label),
        echo_quelle=QUELLE_KACHEL,
    )


def _datei(*kombinationen: Kombiergebnis) -> dict:
    seite = (EINSUNDEINS_SEITE, lauf(EINSUNDEINS_SEITE, list(kombinationen)))
    return ergebnisdatei("1&1", "1und1", [seite], HEUTE, vertragsform="ein_vertrag")


def _kachel_36(einmalzahlung: float) -> Kombiergebnis:
    lesung = einsundeins_lesung()
    buendel = replace(lesung.buendel, einmalzahlung=einmalzahlung)
    return erfasst(replace(lesung, buendel=buendel), "256", TARIF, 36)


def test_kachel_24_wird_buendel_mit_24_raten_und_luecke_einmalzahlung(
    katalog, bestand, tmp_path
):
    alt = _adapter()
    datei = _datei(_kachel_24(), _kachel_36(alt["geraet_zuzahlung"]))
    tco = TcoDB(tmp_path / "tco.json")

    zug = fuehre_zusammen(
        [alt], [datei], katalog, HEUTE, lambda s: geraet_aus_sku(s, katalog)
    )
    bilanz = zug.buendel(bestand, HEUTE, tco.nach_id)
    neu, _ = tco.upsert_buendel(bilanz.buendel, HEUTE)
    gebildet = {b.laufzeit_monate: b for b in bilanz.buendel}

    (kombination, _) = datei["seiten"][0]["kombinationen"]
    assert kombination["echo_quelle"] == QUELLE_KACHEL
    assert "einmalzahlung" in kombination["luecken"]
    assert set(gebildet) == {24, 36} and neu == 2
    kurz, lang = gebildet[24], gebildet[36]
    assert (kurz.sku_id, kurz.anbieter, kurz.tarif_name) == (
        alt["sku_id"],
        "1&1",
        "1&1 All-Net-Flat S",
    )
    assert kurz.tarif_id == lang.tarif_id == "11:1-1-all-net-flat-s"
    assert (kurz.buendel_monatlich, kurz.geraet_zuzahlung) == (59.99, None)
    assert (lang.buendel_monatlich, lang.geraet_zuzahlung) == (44.99, 360.0)
    assert {kurz.quelle_art, lang.quelle_art} == {"klick"}
    assert kurz.id != lang.id
    assert zug.bilanz["ohne_gegenstueck"] == 1 and zug.bilanz["ersetzt"] == 1


def test_gegenprobe_ohne_adaptersatz_bleibt_der_tarif_offen(katalog, bestand):
    zug = fuehre_zusammen(
        [], [_datei(_kachel_24())], katalog, HEUTE, lambda s: geraet_aus_sku(s, katalog)
    )
    bilanz = aus_rohsaetzen(zug.rohsaetze, bestand, HEUTE)

    assert bilanz.buendel == []
    assert bilanz.offene_tarife == {TARIF: 1}


def test_gegenprobe_tarif_mit_namen_behaelt_die_eigene_sku(katalog):
    name = _adapter()["tarif_name"]

    zug = fuehre_zusammen(
        [_adapter()],
        [_datei(_kachel_24(tarif=name))],
        katalog,
        HEUTE,
        lambda s: geraet_aus_sku(s, katalog),
    )

    (satz,) = [s for s in zug.rohsaetze if s.get("quelle_art") == "klick"]
    assert satz["sku_id"] == sku_id("apple-iphone-17-pro", 256, None, "neu")
    assert (satz["tarif_name"], satz["laufzeit_monate"]) == (name, 24)
