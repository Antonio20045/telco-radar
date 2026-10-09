"""Schnitt 5: eine vom Klick-Crawler abgelesene Bündelzeile sagt das neben ihrem Beleg.

Die Entscheidung ist das Kartenfeld ``vom_crawler`` (``quelle_art == "klick"``); die
Vorlage liest nur dieses Feld. Ein Adapter-Bündel und ein Bündel ohne ``quelle_art``
behalten „abgerufen“ mit Datum. Das Datum der Fixture ist fest.
"""

from __future__ import annotations

from bestand_pfad import lese_wurzel

from telco_radar.geraete_config import lade_katalog
from telco_radar.report import geraete_tco_karten as karten
from telco_radar.report import html as seiten
from telco_radar.tarif_model import QUELLE_KLICK
from telco_radar.tco_model import Buendel

TAG = "2026-10-08"
SKU = "apple-iphone-17-pro-256gb-schwarz"
HINWEIS = "vom Crawler abgelesen 8. Oktober 2026"


def _buendel(anbieter, tarif_id, quelle_art):
    return Buendel(
        sku_id=SKU,
        anbieter=anbieter,
        tarif_name=f"Tarif {anbieter}",
        tarif_id=tarif_id,
        tarif_monatlich=19.99,
        geraet_zuzahlung=1.0,
        geraet_monatsrate=30.0,
        laufzeit_monate=24,
        anschlusspreis=0.0,
        quelle_url=f"https://{anbieter.lower()}.invalid/x",
        abgerufen_am=TAG,
        quelle_art=quelle_art,
    )


def _karten():
    ergebnis = karten.modelle(
        [
            _buendel("Telekom", "tk:m", QUELLE_KLICK),
            _buendel("o2", "o2:m", "dokument"),
            _buendel("Vodafone", "vf:m", ""),
        ],
        [],
        [],
        {},
        lade_katalog(lese_wurzel()),
        heute=TAG,
    )
    return {
        k["anbieter"]: k
        for m in ergebnis["modelle"]
        for k in m["karten"]
        if k.get("sku_id")
    }


def test_das_kartenfeld_kennt_nur_den_klicksatz():
    je = _karten()
    assert je["Telekom"]["vom_crawler"] is True
    assert je["Telekom"]["belastbar"] is True
    assert je["o2"]["vom_crawler"] is False
    assert je["Vodafone"]["vom_crawler"] is False


def test_die_zeile_nennt_den_crawler_neben_dem_beleg():
    modul = seiten._env().get_template("_geraete_buendel.html.j2").make_module()
    je = _karten()
    klick = str(modul.buendelzeile(je["Telekom"]))
    assert HINWEIS in klick
    assert "abgerufen 8. Oktober 2026" not in klick
    for anbieter in ("o2", "Vodafone"):
        zeile = str(modul.buendelzeile(je[anbieter]))
        assert "vom Crawler" not in zeile
        assert "abgerufen 8. Oktober 2026" in zeile


def test_der_hinweis_kommt_aus_dem_gespeicherten_buendel():
    from telco_radar.report.geraete_tco_view import aufbereiten

    satz = {
        "id": "buendel--telekom--x",
        "first_seen": TAG,
        **{
            f: getattr(_buendel("Telekom", "tk:m", QUELLE_KLICK), f)
            for f in (
                "sku_id",
                "anbieter",
                "tarif_name",
                "tarif_id",
                "tarif_monatlich",
                "geraet_zuzahlung",
                "geraet_monatsrate",
                "laufzeit_monate",
                "anschlusspreis",
                "quelle_url",
                "abgerufen_am",
                "quelle_art",
            )
        },
    }
    ergebnis = aufbereiten([satz], [], [], lade_katalog(lese_wurzel()), heute=TAG)

    karte = [k for m in ergebnis["modelle"] for k in m["karten"] if k.get("sku_id")]
    assert [k["vom_crawler"] for k in karte] == [True]
