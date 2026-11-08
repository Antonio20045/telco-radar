"""1&1 führt iPhone 16e und iPhone 15 nicht mehr: Lücke statt Preis (08.11.2026).

Am Original belegt: /iphone-16e leitet auf das iPhone 17e um (erst ab 256 GB),
/iphone-15 meldet „nicht mehr verfügbar“. Der Bestand trägt für das 16e noch eine
Zeile vom 05.11.2026 mit Prüfstatus „gueltig“. Die echte Config
(`config/geraete_abdeckung.yaml`) führt beide als belegte Lücke; Seite, Export und
Grafik lesen daraus über `geraete_sortiment.markiere` dieselbe Lücke, nie einen Preis.
Feste Bezugstage, kein heutiges Datum.
"""

from __future__ import annotations

import csv
import dataclasses
import io
from pathlib import Path

import pytest

from telco_radar.analyze.buendel_abdeckung import lade_pflicht
from telco_radar.report import geraete_preisstand, geraete_sortiment, geraete_tco_view
from telco_radar.report.geraete_export import SPALTE_UEBER_24, tco_csv
from telco_radar.tco_model import Buendel

ECHTE_CONFIG = Path(__file__).resolve().parents[1] / "config" / "geraete_abdeckung.yaml"
HEUTE = "2026-11-08"
GEPRUEFT = "2026-11-08"
SKU_16E = "apple-iphone-16e-128gb-ohne-farbe"
SKU_15 = "apple-iphone-15-128gb-blau"
SKU_17E = "apple-iphone-17e-256gb-weiss"
SATZ = "bei 1&1 nicht mehr im Sortiment"


@pytest.fixture(scope="module")
def belege():
    return lade_pflicht(ECHTE_CONFIG)["belege"]


def _satz(sku, anbieter="1&1", abgerufen_am="2026-11-05", pruefung="gueltig"):
    b = Buendel(
        sku_id=sku,
        anbieter=anbieter,
        tarif_name="1&1 All-Net-Flat M",
        tarif_monatlich=None,
        buendel_monatlich=37.99,
        geraet_zuzahlung=220.0,
        laufzeit_monate=36,
        anschlusspreis=39.9,
        quelle_url="https://mobile.1und1.de/iphone-16e?tariffFirst=true",
        abgerufen_am=abgerufen_am,
        zustand="neu",
        pruefung=pruefung,
    )
    return dataclasses.asdict(b)


def _buendel(satz):
    """Wie die Seite: `_aus_speicher` liest auch den Vermerk `pruefung`."""
    (b,) = geraete_tco_view._aus_speicher(
        [satz], Buendel, geraete_tco_view._BUENDEL_FELDER
    )
    return b


def _export(satz):
    zeilen = geraete_tco_view._export_zeilen(
        [_buendel(satz)], [], [], None, {}, None, HEUTE
    )
    text, _ = tco_csv(zeilen)
    kopf, zeile = list(csv.reader(io.StringIO(text), delimiter=";"))
    return dict(zip(kopf, zeile, strict=True))


def test_echte_config_belegt_beide_geraete_bei_1und1(belege):
    for modell in ("apple-iphone-16e", "apple-iphone-15"):
        beleg = belege[("1&1", modell)]
        assert "nicht im Sortiment" in beleg["grund"]
        assert beleg["geprueft"].isoformat() == GEPRUEFT
        assert "/docs/belege/1und1-sortiment-0811/" in beleg["beleg"]
        assert (
            Path(__file__).resolve().parents[1]
            / "docs/belege/1und1-sortiment-0811"
            / beleg["beleg"].rsplit("/", 1)[1]
        ).is_file()


@pytest.mark.parametrize(
    ("sku", "abgerufen_am"),
    [(SKU_16E, "2026-11-05"), (SKU_15, "2026-10-08")],
    ids=["iphone_16e_gueltig_vom_05_11", "iphone_15_veraltet_vom_08_10"],
)
def test_beide_varianten_erscheinen_bei_1und1_als_luecke_ohne_preis(
    belege, sku, abgerufen_am
):
    satz = _satz(sku, abgerufen_am=abgerufen_am)
    if sku == SKU_16E:
        assert geraete_preisstand.buendel_luecke(_buendel(satz), HEUTE) == ""
        assert _export(satz)[SPALTE_UEBER_24] != ""
    (markiert,) = geraete_sortiment.markiere_mit([satz], belege, HEUTE)
    assert markiert is not satz and satz["pruefung"] == "gueltig"
    b = _buendel(markiert)
    assert SATZ in geraete_preisstand.buendel_luecke(b, HEUTE)
    zeile = _export(markiert)
    assert SATZ in zeile["Lücke"]
    assert zeile["Status"] == "nicht im Sortiment"
    for spalte in (
        "Zuzahlung EUR",
        "Bündel/Monat EUR",
        "Anschlusspreis EUR",
        SPALTE_UEBER_24,
        "Kosten über die Bündellaufzeit EUR",
    ):
        assert zeile[spalte] == ""


def test_karte_traegt_den_grund_statt_einer_zahl(belege):
    from telco_radar.report import geraete_notbremse

    (markiert,) = geraete_sortiment.markiere_mit([_satz(SKU_16E)], belege, HEUTE)
    flags = geraete_notbremse.felder_aus_satz(markiert, HEUTE)
    assert flags["nicht_im_sortiment"] and not flags["zaehlt"]
    karte = geraete_preisstand.anzeige(
        {"sku_id": SKU_16E, "anbieter": "1&1", "gesamt": 1171.66, **flags}
    )
    assert karte["gesamt"] is None and karte["belastbar"] is False
    assert karte["luecke_kurz"] == "nicht im Sortiment"
    assert SATZ in karte["leer_grund"]


def test_gegenprobe_andere_geraete_und_anbieter_behalten_ihren_preis(belege):
    unberuehrt = [
        _satz(SKU_17E),
        _satz(SKU_16E, anbieter="Telekom"),
        _satz("apple-iphone-17e-256gb-weiss", anbieter="1&1"),
    ]
    assert geraete_sortiment.markiere_mit(unberuehrt, belege, HEUTE) == unberuehrt


def test_kommt_das_geraet_zurueck_zaehlt_die_zeile_wieder(belege):
    zurueck = _satz(SKU_16E, abgerufen_am="2026-11-12")
    assert geraete_sortiment.markiere_mit([zurueck], belege, "2026-11-12") == [zurueck]


def test_abgelaufener_beleg_markiert_nicht_mehr(belege):
    """Nach `bis` gilt der Beleg nicht mehr; der Wächter ist dann rot (Neuprüfung)."""
    satz = _satz(SKU_16E)
    assert geraete_sortiment.markiere_mit([satz], belege, "2026-11-23") == [satz]
    assert geraete_sortiment.markiere_mit([satz], belege, "") == [satz]


def test_ohne_lesbare_belegliste_bleibt_der_bestand_unveraendert(tmp_path):
    assert geraete_sortiment.belege_aus(tmp_path / "data" / "state") == {}
    satz = _satz(SKU_16E)
    assert geraete_sortiment.markiere_mit([satz], {}, HEUTE) == [satz]


def test_ein_stand_vor_der_pruefung_ist_nicht_widerlegt(belege):
    satz = _satz(SKU_16E, abgerufen_am="2026-10-03")
    assert geraete_sortiment.markiere_mit([satz], belege, "2026-10-03") == [satz]
