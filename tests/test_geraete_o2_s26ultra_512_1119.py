"""o2 führt das Galaxy S26 Ultra nur noch in 256 GB (19.11.)

Der Wächter meldete im Lauf vom 19.11. "samsung-galaxy-s26-ultra ohne
Speicherstufe(n) 512gb ... ohne Beleg" (`Buendelabdeckung pruefen`). Am
Original belegt (`docs/belege/o2-speicher-1119/`): die Produktseite hat nur
einen Speicher-Knopf (256 GB, ausgewählt) und eine Farbe (Black), keine
weitere Stufe. Der eigene o2-Katalog (`/e-shop/rest/catalog/...`) führt
ebenfalls nur die SKU `galaxy-s26-ultra-256gb-black-bw` für dieses Modell -
kein Hinweis auf einen Scraper-Zeitbudget-Abbruch (`o2.vertiefe_buendel`),
sondern eine echte Sortimentslücke. Feste Bezugstage, kein heutiges Datum.
"""

from __future__ import annotations

import dataclasses
from pathlib import Path

import pytest

from telco_radar.analyze.buendel_abdeckung import lade_pflicht
from telco_radar.report import geraete_preisstand, geraete_sortiment, geraete_tco_view
from telco_radar.tco_model import Buendel

WURZEL = Path(__file__).resolve().parents[1]
HEUTE = "2026-11-19"
SKU_512 = "samsung-galaxy-s26-ultra-512gb-black"
SKU_256 = "samsung-galaxy-s26-ultra-256gb-black"
SATZ = "bei o2 nicht mehr im Sortiment"


@pytest.fixture(scope="module")
def belege():
    return lade_pflicht(WURZEL / "config" / "geraete_abdeckung.yaml")["belege"]


def _satz(sku, abgerufen_am):
    b = Buendel(
        sku_id=sku,
        anbieter="o2",
        tarif_name="O2 Mobile S mit 15 GB+ (24 Mon.)",
        tarif_monatlich=14.99,
        geraet_zuzahlung=1.0,
        geraet_monatsrate=16.5,
        laufzeit_monate=24,
        anschlusspreis=0.0,
        quelle_url="https://www.o2online.de/e-shop/samsung/x-details",
        abgerufen_am=abgerufen_am,
        zustand="neu",
        pruefung="gueltig",
    )
    return dataclasses.asdict(b)


def _buendel(satz):
    (b,) = geraete_tco_view._aus_speicher(
        [satz], Buendel, geraete_tco_view._BUENDEL_FELDER
    )
    return b


def test_belegte_stufe_ist_nicht_im_sortiment_statt_altbestand(belege):
    satz = _satz(SKU_512, "2026-11-01")
    (markiert,) = geraete_sortiment.markiere_mit([satz], belege, HEUTE)
    assert markiert is not satz
    assert SATZ in geraete_preisstand.buendel_luecke(_buendel(markiert), HEUTE)


def test_gegenprobe_gefuehrte_stufe_bleibt(belege):
    satz = _satz(SKU_256, "2026-11-19")
    assert geraete_sortiment.markiere_mit([satz], belege, HEUTE) == [satz]


def test_belegbild_liegt_im_repo_und_ist_klein(belege):
    beleg = belege[("o2", "samsung-galaxy-s26-ultra", "512gb")]
    assert beleg["geprueft"].isoformat() == HEUTE
    assert "/docs/belege/o2-speicher-1119/" in beleg["beleg"]
    bild = WURZEL / "docs/belege/o2-speicher-1119" / beleg["beleg"].rsplit("/", 1)[1]
    assert bild.is_file() and bild.stat().st_size < 400_000
