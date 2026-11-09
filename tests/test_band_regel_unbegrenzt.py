"""Unbegrenzt gehört in die oberste Stufe XL (eine Regel, 09.11.2026) und
"Preis am Original widersprüchlich" bleibt ohne Stufe (Daten, nicht Code).

Gegen den Stand davor rot: Die Regel hing an der Vodafone-Stufe XL selbst
(nur deren Volumen `inf` nahm "unbegrenzt" auf); `tarif_baender` kannte keine
Ausnahmeliste.
"""

from __future__ import annotations

import pytest

from telco_radar import band_regel
from telco_radar.collect.geraete import tarifwelt
from telco_radar.report import geraete_stufen
from telco_radar.report import geraete_tco_band as band
from telco_radar.report.geraete_stufen import TARIFSTUFEN_REGEL

INF = float("inf")


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


def _bestand() -> dict:
    """Vodafone-Leiter und zwei unbegrenzte Tarife - von Hand, ohne echte Daten."""

    def satz(anbieter, name, gb, grund, tid):
        return {
            "anbieter": anbieter,
            "name": name,
            "datenvolumen_gb": gb,
            "grundgebuehr": grund,
            "tarif_id": tid,
        }

    saetze = [
        satz("Vodafone", "Vodafone Mobil XS mit Smartphone", 15.0, 29.95, "v:xs"),
        satz("Vodafone", "Vodafone Mobil L mit Smartphone", 120.0, 59.95, "v:l"),
        satz("Vodafone", "Vodafone Mobil XL mit Smartphone", INF, 79.95, "v:xl"),
        satz("Test", "Unlimited A", INF, 29.99, "t:a"),
        satz("Test", "Unlimited B", INF, 39.99, "t:b"),
    ]
    return {s["tarif_id"]: s for s in saetze}


def test_tarif_auf_der_liste_bleibt_ohne_stufe_die_uebrigen_in_xl(monkeypatch):
    monkeypatch.setattr(band_regel, "preis_widerspruch", lambda: {"t:a": {}})
    bestand = _bestand() | {"t:a-plus": dict(_bestand()["t:a"], tarif_id="t:a-plus")}
    index = band.tarif_baender(bestand, band.tarifleiter(bestand))
    assert "t:a" not in index
    assert "t:a-plus" not in index
    assert index["t:b"] == "xl"
    assert index["v:xl"] == "xl"


def test_gegenprobe_leere_liste_alle_unbegrenzten_in_xl(monkeypatch):
    monkeypatch.setattr(band_regel, "preis_widerspruch", lambda: {})
    bestand = _bestand() | {"t:a-plus": dict(_bestand()["t:a"], tarif_id="t:a-plus")}
    index = band.tarif_baender(bestand, band.tarifleiter(bestand))
    assert index["t:a"] == index["t:a-plus"] == index["t:b"] == "xl"


def test_die_echte_liste_laedt_und_jeder_eintrag_hat_name_grund_beleg():
    liste = band_regel.preis_widerspruch()
    assert isinstance(liste, dict)
    assert all(e["name"] and e["grund"] and e["beleg"] for e in liste.values())


def test_ausnahme_trifft_plus_und_variante_aber_nicht_den_flex_tarif(monkeypatch):
    monkeypatch.setattr(band_regel, "preis_widerspruch", lambda: {"t:a": {}})
    bestand = {"t:a#live_shop": {}, "t:a-plus": {}, "t:b": {}, "t:a-flex": {}}
    assert set(band_regel.ohne_preis_widerspruch(bestand)) == {"t:b", "t:a-flex"}


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


def _einsundeins_unlimited_xl() -> dict:
    """Der Tarifsatz so, wie der Sammler ihn aus der echten Seite baut."""
    import gzip
    from pathlib import Path

    from telco_radar.collect import tarif_ldjson
    from telco_radar.collect.tarif_crawler import tarif_id

    pfad = Path(__file__).parent / "fixtures" / "tarife" / "1und1_handytarife.html.gz"
    with gzip.open(pfad, "rt", encoding="utf-8") as fh:
        html = fh.read()
    for tarif, _ in tarif_ldjson.tarife_aus_html(
        html, anbieter="1&1", seiten_url="u", abgerufen_am="2026-11-09"
    ):
        if tarif.name == "1&1 Unlimited XL":
            return {**tarif.als_dict(), "tarif_id": tarif_id("1&1", tarif.name)}
    raise AssertionError("1&1 Unlimited XL fehlt in der Seite")


def test_einsundeins_unlimited_xl_bekommt_stufe_xl_im_bericht():
    satz = _einsundeins_unlimited_xl()
    assert satz["datenvolumen_gb"] == INF
    bestand = _bestand() | {satz["tarif_id"]: satz}
    index = band.tarif_baender(bestand, band.tarifleiter(bestand))
    assert index[satz["tarif_id"]] == "xl"


def test_einsundeins_unlimited_xl_bekommt_stufe_xl_im_sammeln():
    satz = _einsundeins_unlimited_xl()
    assert set(tarifwelt.rangliste_je_band([satz], _leiter(INF))) == {"xl"}


def test_gegenprobe_ohne_erfasstes_volumen_keine_stufe():
    satz = dict(_einsundeins_unlimited_xl(), datenvolumen_gb=None)
    bestand = _bestand() | {satz["tarif_id"]: satz}
    index = band.tarif_baender(bestand, band.tarifleiter(bestand))
    assert satz["tarif_id"] not in index


def test_kopf_der_ausnahmeliste_behauptet_kein_sammeln():
    """Die Liste kennt `tarif_id` des Tarifbestands; das Sammeln (Tarifwelt)
    arbeitet mit anderen IDs und liest sie nicht."""
    kopf = band_regel.PFAD_PREIS_WIDERSPRUCH.read_text(encoding="utf-8")
    kopf = kopf.split("tarife:")[0]
    assert "Sammeln und Bericht" not in kopf
    assert "nur im Bericht" in kopf


def test_sammeln_kennt_die_ausnahmeliste_nicht(monkeypatch):
    def nie():
        raise AssertionError("das Sammeln liest die Ausnahmeliste nicht")

    monkeypatch.setattr(band_regel, "preis_widerspruch", nie)
    saetze = [{"tarif_id": "u", "datenvolumen_gb": INF, "grundgebuehr": 40.0}]
    assert set(tarifwelt.rangliste_je_band(saetze, _leiter(INF))) == {"xl"}


def test_widerspruchsstand_nennt_bei_leerer_liste_derzeit_kein_tarif():
    assert geraete_stufen.widerspruch_stand({}) == "derzeit kein Tarif"


def test_widerspruchsstand_nennt_die_gelisteten_tarife():
    liste = {"t:a": {"name": "Tarif A"}, "t:b": {"name": "Tarif B"}}
    assert geraete_stufen.widerspruch_stand(liste) == "derzeit: Tarif A, Tarif B"


def test_erklaersatz_nennt_tarife_ohne_erfasstes_volumen():
    assert "ohne erfasstes Datenvolumen bleibt ohne Stufe" in TARIFSTUFEN_REGEL
    assert "1&1" not in TARIFSTUFEN_REGEL
