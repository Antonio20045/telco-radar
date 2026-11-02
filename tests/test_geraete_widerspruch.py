"""Ein abgeleiteter 1&1-Preis, den die gelesene Zeile widerlegt, zählt nirgends.

Befund 02.11.2026: das Bild der Preispositionierung ließ 1&1 beim Galaxy S26 Ultra
weg, Tabelle und Export führten dieselbe Karte mit 1.531,66 € weiter. Jetzt gibt es
EINE Definition (`analyze.geraete_widerspruch`), die vor allen Lesern wirkt.
"""

from __future__ import annotations

import logging

from telco_radar.analyze.geraete_widerspruch import ohne_widerlegte
from telco_radar.report import geraete_preisposition_preise as preise
from telco_radar.report.geraete_tco_view import aufbereiten
from telco_radar.tco_model import Buendel

HEUTE = "2026-11-02"
SKU = "samsung-galaxy-s26-ultra-256gb"
ABGELEITET = "tarifaufschlag_aus_tarifraster"
EINTRAEGE = [
    {"sku_id": SKU, "device_id": "samsung-galaxy-s26-ultra", "speicher_gb": 256}
]


def _buendel(
    tarif: str,
    zuzahlung: float,
    *,
    gelesen: bool,
    anbieter: str = "1&1",
    sku: str = SKU,
    raten: int = 24,
    herleitung: str = ABGELEITET,
) -> Buendel:
    return Buendel(
        sku_id=sku,
        anbieter=anbieter,
        tarif_name=tarif,
        tarif_monatlich=30.0,
        geraet_zuzahlung=zuzahlung,
        geraet_monatsrate=20.0,
        laufzeit_monate=raten,
        anschlusspreis=0.0,
        quelle_url=f"https://beispiel.test/{tarif}",
        abgerufen_am=HEUTE,
        zustand="neu",
        quelle_art="klick" if gelesen else "",
        herleitung="" if gelesen else herleitung,
    )


def _tarife(buendel: list[Buendel]) -> list[str]:
    return [b.tarif_name for b in buendel]


def test_die_abgeleitete_zuzahlung_gegen_die_gelesene_faellt_weg(caplog):
    liste = [_buendel("S", 360.0, gelesen=True), _buendel("M", 340.0, gelesen=False)]
    with caplog.at_level(logging.WARNING):
        rest = ohne_widerlegte(liste)
    assert _tarife(rest) == ["S"]
    assert "widerspricht der gelesenen Zeile" in caplog.text


def test_gegenprobe_nichts_zu_widerlegen_nichts_faellt_weg():
    gleich = [_buendel("S", 360.0, gelesen=True), _buendel("M", 360.0, gelesen=False)]
    assert _tarife(ohne_widerlegte(gleich)) == ["S", "M"]
    ohne_gegenzeile = [_buendel("M", 340.0, gelesen=False)]
    assert _tarife(ohne_widerlegte(ohne_gegenzeile)) == ["M"]
    anderes_geraet = [
        _buendel("S", 360.0, gelesen=True, sku="anderes"),
        _buendel("M", 340.0, gelesen=False),
    ]
    assert _tarife(ohne_widerlegte(anderes_geraet)) == ["S", "M"]
    andere_raten = [
        _buendel("S", 360.0, gelesen=True, raten=36),
        _buendel("M", 340.0, gelesen=False),
    ]
    assert _tarife(ohne_widerlegte(andere_raten)) == ["S", "M"]
    telekom = [
        _buendel("S", 100.0, gelesen=True, anbieter="Telekom"),
        _buendel("M", 150.0, gelesen=False, anbieter="Telekom", herleitung=""),
    ]
    assert _tarife(ohne_widerlegte(telekom)) == ["S", "M"]


def test_tabelle_export_und_bild_fuehren_dieselben_buendel():
    liste = [_buendel("S", 360.0, gelesen=True), _buendel("M", 340.0, gelesen=False)]
    ergebnis = aufbereiten(liste, [], EINTRAEGE, katalog=None, heute=HEUTE)
    modell = ergebnis["modelle"][0]
    tabelle = [k["tarif"] for k in modell["karten"] if k["tarif"]]
    export = [z["tarif"] for z in ergebnis["export"]["buendel"]]
    assert tabelle == export == ["S"]
    assert all(k["zuzahlung"] != 340.0 for k in modell["karten"])
    assert preise.preise_je_anbieter(modell).get("1&1", {}).get("zuzahlung") != 340.0


def test_gegenprobe_stimmt_die_zuzahlung_stehen_alle_ueberall():
    liste = [_buendel("S", 360.0, gelesen=True), _buendel("M", 360.0, gelesen=False)]
    ergebnis = aufbereiten(liste, [], EINTRAEGE, katalog=None, heute=HEUTE)
    export = [z["tarif"] for z in ergebnis["export"]["buendel"]]
    tabelle = [k["tarif"] for k in ergebnis["modelle"][0]["karten"] if k["tarif"]]
    assert sorted(export) == sorted(tabelle) == ["M", "S"]
