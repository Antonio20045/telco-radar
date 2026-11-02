"""Der TCO-Export zeigt für einen veralteten Preis keine Zahl (Befund 02.11.2026).

Die Zeile der Seite macht einen veralteten Preis zur Lücke (``geraete_preisstand``);
der Export liest dieselbe Definition und nennt den Grund in „Lücke“, statt weiter
Betrag und Kosten über 24 Monate zu schreiben. Fester Bezugstag, kein heutiges Datum.
"""

from __future__ import annotations

import csv
import io

import pytest

from telco_radar.report import geraete_tco_view
from telco_radar.report.geraete_export import (
    SPALTE_UEBER_24,
    SPALTE_UEBER_LAUFZEIT,
    tco_csv,
)
from telco_radar.tco_model import Buendel

HEUTE = "2026-11-02"
ALT = "2026-10-20"


def _buendel(sku, abgerufen_am=HEUTE, pruefung=None):
    return Buendel(
        sku_id=sku,
        anbieter="o2",
        tarif_name="o2 Free M",
        tarif_monatlich=23.17,
        geraet_zuzahlung=1.0,
        geraet_monatsrate=30.0,
        laufzeit_monate=24,
        anschlusspreis=39.99,
        quelle_url=f"https://example.org/{sku}",
        abgerufen_am=abgerufen_am,
        zustand="neu",
        pruefung=pruefung,
    )


def _zeilen(*buendel):
    zeilen = geraete_tco_view._export_zeilen(
        list(buendel), [], [], None, {}, None, HEUTE
    )
    text, _ = tco_csv(zeilen)
    kopf, *rest = csv.reader(io.StringIO(text), delimiter=";")
    return {r[kopf.index("SKU-ID")]: dict(zip(kopf, r, strict=True)) for r in rest}


PREISSPALTEN = (
    "Zuzahlung EUR",
    "Tarif/Monat EUR",
    "Geräterate EUR",
    "Bündel/Monat EUR",
    "Anschlusspreis EUR",
    SPALTE_UEBER_24,
    SPALTE_UEBER_LAUFZEIT,
)


@pytest.mark.parametrize(
    "stand",
    [{"abgerufen_am": ALT}, {"pruefung": "veraltet 16"}],
    ids=["zu_alt", "pruefung_veraltet"],
)
def test_veralteter_preis_steht_im_export_ohne_zahl_mit_grund(stand):
    zeile = _zeilen(_buendel("alt", **stand))["alt"]
    for spalte in PREISSPALTEN:
        assert zeile[spalte] == "", f"{spalte} trägt {zeile[spalte]!r}"
    assert zeile["Lücke"].startswith("Preis veraltet")


def test_alte_zeile_nennt_das_abrufdatum_wie_die_seite():
    zeile = _zeilen(_buendel("alt", abgerufen_am=ALT))["alt"]
    assert "kein aktueller Stand seit 20.10.2026" in zeile["Lücke"]


def test_gegenprobe_aktueller_preis_bleibt_im_export():
    zeilen = _zeilen(_buendel("alt", abgerufen_am=ALT), _buendel("neu"))
    neu = zeilen["neu"]
    assert neu["Tarif/Monat EUR"] == "23,17"
    assert neu["Anschlusspreis EUR"] == "39,99"
    assert neu[SPALTE_UEBER_24] != ""
    assert "veraltet" not in neu["Lücke"]
    assert zeilen["alt"][SPALTE_UEBER_24] == ""
