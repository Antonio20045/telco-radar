"""Unbegrenzt gehört in die oberste Stufe XL (eine Regel, 09.11.2026) und
"Preis am Original widersprüchlich" bleibt ohne Stufe (Daten, nicht Code).

Gegen den Stand davor rot: Die Regel hing an der Vodafone-Stufe XL selbst
(nur deren Volumen `inf` nahm "unbegrenzt" auf); `tarif_baender` kannte keine
Ausnahmeliste.
"""

from __future__ import annotations

import pytest
from bestand_pfad import ZUSTAND

from telco_radar import band_regel
from telco_radar.collect.geraete import tarifwelt
from telco_radar.report import geraete_tco_band as band
from telco_radar.report.geraete_stufen import TARIFSTUFEN_REGEL
from telco_radar.tarif_bezug import Tarifbestand

INF = float("inf")
O2_M = "o2:o2-mobile-unlimited-m"


@pytest.fixture(scope="module")
def tarife():
    return Tarifbestand.aus_datei(ZUSTAND / "tarife.jsonl").je_id


def _leiter(xl_gb):
    return (("xs", 15.0), ("s", 30.0), ("m", 60.0), ("l", 120.0), ("xl", xl_gb))


@pytest.mark.parametrize("xl_gb", [INF, None, 250.0])
def test_unbegrenzt_steht_in_xl_egal_was_die_vodafone_stufe_traegt(xl_gb):
    assert band_regel.stufe_fuer(INF, _leiter(xl_gb)) == "xl"


def test_gegenprobe_ohne_xl_auf_der_leiter_kein_rutschen_in_die_groesste():
    assert band_regel.stufe_fuer(INF, _leiter(INF)[:4]) is None


def test_gegenprobe_fehlendes_volumen_bleibt_ohne_stufe():
    """Ein Tarif ohne erhobenes Volumen ist nicht "unbegrenzt": keine Stufe,
    auch nicht über den Namen (1&1 "Unlimited XL" trägt heute `None`)."""
    assert band_regel.stufe_fuer(None, _leiter(INF)) is None
    leiter = band.tarifleiter({})
    satz = {"anbieter": "1&1", "name": "1&1 Unlimited XL", "datenvolumen_gb": None}
    assert band.tarif_baender({"11:1-1-unlimited-xl": satz}, leiter) == {}


def test_endliche_volumen_bleiben_wie_sie_waren():
    assert band_regel.stufe_fuer(150.0, _leiter(INF)) == "l"
    assert band_regel.stufe_fuer(20.0, _leiter(INF)) == "xs"
    assert band_regel.stufe_fuer(22.5, _leiter(INF)) == "s"


def test_sammeln_nimmt_unbegrenzt_auch_bei_xl_ohne_volumen_auf():
    saetze = [{"tarif_id": "u", "datenvolumen_gb": INF, "grundgebuehr": 40.0}]
    assert set(tarifwelt.rangliste_je_band(saetze, _leiter(None))) == {"xl"}


def test_erklaersatz_nennt_die_regel_in_einem_satz():
    assert (
        "unbegrenztem Datenvolumen steht in der obersten Stufe XL" in TARIFSTUFEN_REGEL
    )


def test_o2_unlimited_m_bleibt_ohne_stufe_die_uebrigen_unbegrenzten_in_xl(tarife):
    index = band.tarif_baender(tarife, band.tarifleiter(tarife))
    assert tarife[O2_M]["datenvolumen_gb"] == INF
    assert O2_M not in index
    assert O2_M + "-plus" not in index
    assert index["o2:o2-mobile-unlimited-l"] == "xl"
    assert index["o2:o2-mobile-unlimited-s-special"] == "xl"
    assert index["vodafone:vodafone-mobil-xl"] == "xl"


def test_gegenprobe_ohne_listeneintrag_steht_o2_unlimited_m_in_xl(tarife, monkeypatch):
    monkeypatch.setattr(band_regel, "preis_widerspruch", lambda: {})
    index = band.tarif_baender(tarife, band.tarifleiter(tarife))
    assert index[O2_M] == "xl"
    assert index[O2_M + "-plus"] == "xl"


def test_die_liste_nennt_name_grund_und_beleg():
    liste = band_regel.preis_widerspruch()
    assert set(liste) == {O2_M}
    eintrag = liste[O2_M]
    assert (
        eintrag["name"] and "34,99" in eintrag["grund"] and "24,99" in eintrag["grund"]
    )
    assert "unlimited-0811.md" in eintrag["beleg"]
    bestand = {O2_M + "#live_shop": {}, O2_M + "-plus": {}, "o2:o2-mobile-l": {}}
    assert set(band_regel.ohne_preis_widerspruch(bestand)) == {"o2:o2-mobile-l"}
    flex = {"o2:o2-mobile-unlimited-m-flex": {}}
    assert band_regel.ohne_preis_widerspruch(flex) == flex


def test_kaputte_oder_fehlende_liste_ist_ein_fehler_kein_leerer_bestand(tmp_path):
    with pytest.raises(OSError):
        band_regel.preis_widerspruch(tmp_path / "fehlt.yaml")
    ohne_beleg = tmp_path / "x.yaml"
    ohne_beleg.write_text(
        "tarife:\n  - tarif_id: a\n    name: A\n    grund: g\n", encoding="utf-8"
    )
    with pytest.raises(ValueError, match="Beleg"):
        band_regel.preis_widerspruch(ohne_beleg)
    leer = tmp_path / "y.yaml"
    leer.write_text("", encoding="utf-8")
    with pytest.raises(ValueError):
        band_regel.preis_widerspruch(leer)
