"""o2 führt A37 256 GB, Redmi Note 15 256 GB, iPhone 17 Pro 512 GB nicht (09.11.)

Am Original belegt (`docs/belege/o2-speicher-0911/`): Speicherwahl des A37 hat nur
128 GB, die Redmi-Note-15-Seite ergibt 404 (die Xiaomi-Liste führt nur das Pro), das
iPhone 17 Pro bietet nur 256 GB. Die Export-Zeilen der drei Stufen sind Altbestand und
tragen heute „Preis veraltet“; mit dem Beleg lesen Seite und Export „nicht im
Sortiment“ (`geraete_sortiment.markiere_mit`, Prüfung `speicher_fehlt` kennt die
Lücke). Gegenprobe: die geführte Stufe (A37 128 GB) und ein anderes Gerät bleiben.
Feste Bezugstage, kein heutiges Datum.
"""

from __future__ import annotations

import dataclasses
from pathlib import Path

import pytest

from telco_radar.analyze.buendel_abdeckung import lade_pflicht
from telco_radar.report import geraete_preisstand, geraete_sortiment, geraete_tco_view
from telco_radar.tco_model import Buendel

WURZEL = Path(__file__).resolve().parents[1]
HEUTE = "2026-11-09"
SKU_A37_256 = "samsung-galaxy-a37-256gb-awesome-charcoal"
SKU_A37_128 = "samsung-galaxy-a37-128gb-awesome-charcoal"
SKU_REDMI_256 = "xiaomi-redmi-note-15-256gb-schwarz-5g"
SKU_REDMI_PRO_256 = "xiaomi-redmi-note-15-pro-256gb-schwarz-5g"
SKU_17PRO_512 = "apple-iphone-17-pro-512gb-silber"
SKU_17PRO_256 = "apple-iphone-17-pro-256gb-cosmic-orange"
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


@pytest.mark.parametrize(
    ("sku", "abgerufen_am"),
    [
        (SKU_A37_256, "2026-10-14"),
        (SKU_REDMI_256, "2026-09-30"),
        (SKU_17PRO_512, "2026-10-13"),
    ],
    ids=["a37_256", "redmi_note_15_256", "iphone_17_pro_512"],
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
        (SKU_A37_128, "2026-11-09"),
        (SKU_REDMI_PRO_256, "2026-11-09"),
        (SKU_17PRO_256, "2026-11-09"),
    ],
    ids=["a37_128_gefuehrt", "redmi_note_15_pro_gefuehrt", "iphone_17_pro_256"],
)
def test_gegenprobe_gefuehrte_stufe_und_anderes_geraet_bleiben(
    belege, sku, abgerufen_am
):
    satz = _satz(sku, abgerufen_am)
    assert geraete_sortiment.markiere_mit([satz], belege, HEUTE) == [satz]


def test_belegbilder_liegen_im_repo_und_sind_klein(belege):
    for modell, stufe in (
        ("samsung-galaxy-a37", "256gb"),
        ("xiaomi-redmi-note-15", "256gb"),
        ("apple-iphone-17-pro", "512gb"),
    ):
        beleg = belege[("o2", modell, stufe)]
        assert beleg["geprueft"].isoformat() == HEUTE
        assert "/docs/belege/o2-speicher-0911/" in beleg["beleg"]
        bild = (
            WURZEL / "docs/belege/o2-speicher-0911" / beleg["beleg"].rsplit("/", 1)[1]
        )
        assert bild.is_file() and bild.stat().st_size < 400_000
