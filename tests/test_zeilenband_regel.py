"""Die Regeln hinter der Stufe je Bündelzeile: Herkunft, Verlauf, Lesart.

Die Zusammenschau gegen echte Exportdaten steht in
``test_einsundeins_unlimited_rechenart``; hier die einzelnen Regeln.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from telco_radar.analyze.geraete_pruefstatus import (
    HERLEITUNG_SCHLUSSZAHLUNG,
    HERLEITUNG_TARIFRASTER,
    ist_gemessen,
)
from telco_radar.analyze.geraete_schwankung import (
    rueckspruenge,
    schwankende_buendel,
)
from telco_radar.band_regel import Tarifbaender, band_fuer, unbegrenzt_ohne_beleg

ID = "buendel--1-1--sku-a--1-1-unlimited-xl--36m"


@pytest.mark.parametrize(
    ("herleitung", "quelle_art", "gemessen"),
    [
        ("", "", True),
        ("", "klick", True),
        (HERLEITUNG_TARIFRASTER, "", False),
        (HERLEITUNG_TARIFRASTER, "klick", False),
        (HERLEITUNG_SCHLUSSZAHLUNG, "klick", True),
        (HERLEITUNG_SCHLUSSZAHLUNG, "", False),
        ("tarifsumme_minus_geraeterate", "", True),
    ],
)
def test_gemessen_ist_was_nicht_aus_dem_raster_stammt(herleitung, quelle_art, gemessen):
    assert ist_gemessen(herleitung, quelle_art) is gemessen


@pytest.mark.parametrize(
    ("gb", "belegt", "ohne"),
    [
        (float("inf"), False, True),
        (float("inf"), True, False),
        (150.0, False, False),
        (None, False, False),
    ],
)
def test_nur_unbegrenzt_braucht_einen_beleg(gb, belegt, ohne):
    assert unbegrenzt_ohne_beleg(gb, belegt) is ohne


def test_die_zeile_auf_der_liste_hat_keine_stufe_ihr_tarif_behaelt_sie():
    baender = Tarifbaender({"t": "xl"}, ohne_stufe={"b1"})
    assert band_fuer(baender, "t", "b1") is None
    assert band_fuer(baender, "t", "b2") == "xl"
    assert band_fuer(baender, "t", None) == "xl"
    assert band_fuer(baender, None, "b2") is None
    assert band_fuer({"t": "xl"}, "t", "b1") == "xl"


@pytest.mark.parametrize(
    ("folge", "zahl"),
    [
        ([1, 1, 2, 2], 0),
        ([1, 2, 3], 0),
        ([1, 2, 1], 1),
        ([1, 1, 2, 1, 2], 2),
        ([], 0),
    ],
)
def test_rueckspruenge_zaehlt_die_rueckkehr_zu_einem_verlassenen_stand(folge, zahl):
    assert rueckspruenge(folge) == zahl


def _historie(tmp_path: Path, folge: list[float]) -> Path:
    """Eine Zeile je Messtag (ab 01.11.) mit dem Bündelpreis aus ``folge``."""
    ordner = tmp_path / "geraete_tco_historie"
    ordner.mkdir()
    for tag, preis in enumerate(folge, start=1):
        satz = {
            "id": ID,
            "datum": f"2026-11-{tag:02d}",
            "laufzeit_monate": 36,
            "buendel_monatlich": preis,
            "geraet_zuzahlung": 100.0,
        }
        (ordner / f"{satz['datum']}.jsonl").write_text(
            json.dumps(satz) + "\n", encoding="utf-8"
        )
    return tmp_path / "geraete_tco_historie.jsonl"


def test_ohne_historie_ist_der_verlauf_unbekannt_nicht_ruhig(tmp_path):
    assert schwankende_buendel(tmp_path / "geraete_tco_historie.jsonl") is None


def test_hin_und_zurueck_im_fenster_ist_ein_widerspruch(tmp_path):
    alt = _historie(tmp_path, [50.0, 50.0, 50.0, 53.0, 50.0, 53.0, 53.0])
    assert schwankende_buendel(alt) == {ID}


def test_ein_preiswechsel_ist_kein_widerspruch(tmp_path):
    alt = _historie(tmp_path, [50.0, 50.0, 50.0, 53.0, 53.0, 53.0, 53.0])
    assert schwankende_buendel(alt) == frozenset()


def test_der_wechsel_vor_dem_fenster_zaehlt_nicht_mehr(tmp_path):
    alt = _historie(tmp_path, [50.0, 53.0, 50.0, 50.0, 50.0, 50.0, 50.0, 50.0, 50.0])
    assert schwankende_buendel(alt) == frozenset()
