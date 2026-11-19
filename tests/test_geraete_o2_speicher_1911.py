"""o2 führt das Galaxy S26 Ultra nur noch mit 256 GB (19.11.)

Am Original belegt (`docs/belege/o2-speicher-1911/`): der Speicherwähler der
Produktseite hat genau eine Stufe, 256 GB (1), die Adresse der 512-GB-Variante
(…-512gb-cobalt-violet-details) ergibt 404 (2). Gestern (18.11.) war 512 GB noch
da (arbeit/ursache-waechter-2026-11-19.md) - eine echte Sortimentsänderung, keine
Messlücke. Export-Zeilen mit 512 GB bzw. 1024 GB tragen deshalb heute "nicht im
Sortiment" statt "Preis veraltet". Gegenprobe: die geführte Stufe (256 GB) und ein
anderes Gerät bleiben. Feste Bezugstage, kein heutiges Datum.
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
SKU_S26U_512 = "samsung-galaxy-s26-ultra-512gb-cobalt-violet"
SKU_S26U_1024 = "samsung-galaxy-s26-ultra-1024gb-cobalt-violet"
SKU_S26U_256 = "samsung-galaxy-s26-ultra-256gb-black-bw"
SKU_ANDERES_GERAET = "apple-iphone-17-256gb-schwarz"
SATZ = "bei o2 nicht mehr im Sortiment"


@pytest.fixture(scope="module")
def belege():
    return lade_pflicht(WURZEL / "config" / "geraete_abdeckung.yaml")["belege"]


def _satz(sku, abgerufen_am):
    b = Buendel(
        sku_id=sku,
        anbieter="o2",
        tarif_name="O2 Mobile M mit 50 GB+ (24 Mon.)",
        tarif_monatlich=19.99,
        geraet_zuzahlung=1.0,
        geraet_monatsrate=52.0,
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


@pytest.mark.parametrize(
    ("sku", "abgerufen_am"),
    [
        (SKU_S26U_512, "2026-11-18"),
        (SKU_S26U_1024, "2026-11-08"),
    ],
    ids=["s26ultra_512", "s26ultra_1024"],
)
def test_belegte_stufe_ist_nicht_im_sortiment_statt_altbestand(
    belege, sku, abgerufen_am
):
    satz = _satz(sku, abgerufen_am)
    (markiert,) = geraete_sortiment.markiere_mit([satz], belege, HEUTE)
    assert markiert is not satz
    assert SATZ in geraete_preisstand.buendel_luecke(_buendel(markiert), HEUTE)


@pytest.mark.parametrize(
    ("sku", "abgerufen_am"),
    [
        (SKU_S26U_256, "2026-11-19"),
        (SKU_ANDERES_GERAET, "2026-11-19"),
    ],
    ids=["s26ultra_256_gefuehrt", "anderes_geraet"],
)
def test_gegenprobe_gefuehrte_stufe_und_anderes_geraet_bleiben(
    belege, sku, abgerufen_am
):
    satz = _satz(sku, abgerufen_am)
    assert geraete_sortiment.markiere_mit([satz], belege, HEUTE) == [satz]


def test_belegbilder_liegen_im_repo_und_sind_klein(belege):
    for speicher in ("512gb", "1024gb"):
        beleg = belege[("o2", "samsung-galaxy-s26-ultra", speicher)]
        assert beleg["geprueft"].isoformat() == HEUTE
        assert "/docs/belege/o2-speicher-1911/" in beleg["beleg"]
        bild = (
            WURZEL / "docs/belege/o2-speicher-1911" / beleg["beleg"].rsplit("/", 1)[1]
        )
        assert bild.is_file() and bild.stat().st_size < 400_000
