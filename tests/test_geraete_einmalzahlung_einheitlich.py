"""Die Einmalzahlung nach 24 Monaten ist bei 1&1 ein Gerätewert, kein Tarifwert.

Entscheidung Manager 05.11.2026: bei 1&1 ist die Einmalzahlung bei Kündigung nach
Monat 24 für alle Tarife desselben Geräts (gleicher Speicher) gleich. Ein Tarif, der
abweicht, hat einen unglaubwürdigen 24+12-Preis und wird zur benannten Lücke
("1&1-Wert widersprüchlich, neu messen"). Bei nur einem Tarif je Gerät gibt es nichts
zu prüfen. Das ersetzt die Regel "nur der jüngste Messlauf" (der alte Wert steht in
der Klickdatei vom 05.11. selbst).
Befund: Galaxy S26 256 GB, Tarif S, zeigte 1.051,66 € (220 € Ablöse), alle anderen
Tarife des Geräts rechnen mit 280 €.
"""

from __future__ import annotations

import logging

from telco_radar.analyze.geraete_pruefstatus import HERLEITUNG_EINMALZAHLUNG
from telco_radar.analyze.geraete_widerspruch import (
    abweichende_einmalzahlungen,
    mit_einheitlicher_einmalzahlung,
)
from telco_radar.report import geraete_notbremse as notbremse
from telco_radar.report.geraete_tco_view import aufbereiten
from telco_radar.tco_kosten import POSTEN_EINMALZAHLUNG
from telco_radar.tco_model import Buendel, kosten_ueber

HEUTE = "2026-11-05"
SKU = "samsung-galaxy-s26-256gb-schwarz"
GERAET = {SKU: ("samsung-galaxy-s26", 256)}
EINTRAEGE = [{"sku_id": SKU, "device_id": "samsung-galaxy-s26", "speicher_gb": 256}]


def _eins_und_eins(tarif: str, monatlich: float, zuzahlung: float, sku: str = SKU):
    return Buendel(
        sku_id=sku,
        anbieter="1&1",
        tarif_name=tarif,
        buendel_monatlich=monatlich,
        geraet_zuzahlung=zuzahlung,
        laufzeit_monate=36,
        anschlusspreis=39.9,
        quelle_url=f"https://beispiel.test/{tarif}",
        abgerufen_am=HEUTE,
        zustand="neu",
    )


def _s26():
    return [
        _eins_und_eins("1&1 All-Net-Flat S", 32.99, 220.0),
        _eins_und_eins("1&1 All-Net-Flat M", 37.99, 280.0),
        _eins_und_eins("1&1 All-Net-Flat L", 42.99, 280.0),
    ]


def test_abweichende_einmalzahlung_wird_zur_luecke(caplog):
    with caplog.at_level(logging.WARNING):
        ergebnis = mit_einheitlicher_einmalzahlung(_s26(), GERAET)
    je_tarif = {b.tarif_name: b for b in ergebnis}
    s = je_tarif["1&1 All-Net-Flat S"]
    assert s.geraet_zuzahlung is None and s.herleitung == HERLEITUNG_EINMALZAHLUNG
    assert je_tarif["1&1 All-Net-Flat M"].geraet_zuzahlung == 280.0
    assert je_tarif["1&1 All-Net-Flat L"].geraet_zuzahlung == 280.0
    assert "weicht vom Gerätewert ab" in caplog.text


def test_gegenprobe_gleiche_einmalzahlung_bleibt_der_preis():
    gleich = [_eins_und_eins(t, m, 280.0) for t, m in (("S", 32.99), ("M", 37.99))]
    assert mit_einheitlicher_einmalzahlung(gleich, GERAET) == gleich


def test_gegenprobe_ein_tarif_je_geraet_wird_nicht_geprueft():
    allein = [_eins_und_eins("S", 32.99, 220.0)]
    assert mit_einheitlicher_einmalzahlung(allein, GERAET) == allein


def test_gegenprobe_anderer_speicher_ist_ein_anderes_geraet():
    sku_512 = "samsung-galaxy-s26-512gb-schwarz"
    geraete = {**GERAET, sku_512: ("samsung-galaxy-s26", 512)}
    liste = [
        _eins_und_eins("S", 32.99, 220.0),
        _eins_und_eins("S", 37.99, 350.0, sku=sku_512),
    ]
    assert mit_einheitlicher_einmalzahlung(liste, geraete) == liste


def test_gleichstand_hat_keinen_geraetewert_beide_werden_luecke():
    assert abweichende_einmalzahlungen([220.0, 280.0]) == {220.0, 280.0}
    assert abweichende_einmalzahlungen([280.0, 280.0, 220.0]) == {220.0}
    assert abweichende_einmalzahlungen([280.0]) == set()
    assert abweichende_einmalzahlungen([280.0, 280.0]) == set()


def test_die_tafel_zeigt_fuer_s_die_luecke_statt_1051_66():
    """24 × 32,99 + 220 € + 39,90 = 1.051,66 € - genau der Wert, den die Prüfung
    an PR #45 noch auf der Zeitreihen-Seite fand, obwohl die Tafel ihn für S
    schon als widersprüchlich führt. M rechnet unverändert: 24 × 37,99 + 280 +
    39,90 = 1.231,66 €."""
    ergebnis = aufbereiten(_s26(), [], EINTRAEGE, katalog=None, heute=HEUTE)
    zeilen = {z["tarif"]: z for z in ergebnis["export"]["buendel"]}
    s = zeilen["1&1 All-Net-Flat S"]
    assert s["zuzahlung"] is None and s["tco24"] is None
    assert s["luecke"] == POSTEN_EINMALZAHLUNG
    assert zeilen["1&1 All-Net-Flat M"]["tco24"] == 1231.66
    assert 1051.66 not in {z["tco24"] for z in zeilen.values() if z["tco24"]}


def test_die_notbremse_nennt_den_grund_beim_namen():
    satz = notbremse.HERLEITUNG_SATZ[HERLEITUNG_EINMALZAHLUNG].format(anbieter="1&1")
    assert "1&1-Wert widersprüchlich, neu messen" in satz


def test_kosten_ueber_ohne_widerspruch_rechnet_24_monate_plus_abloese():
    """Gegenprobe der Kernzahl selbst (ohne die Widerspruchsregel): ein
    einzelnes 1&1-Bündel über 36 Monate zählt 24 Beträge plus Ablöse."""
    b = _eins_und_eins("1&1 All-Net-Flat M", 37.99, 280.0)
    k = kosten_ueber(b)
    assert k.gesamt == round(24 * 37.99 + 280.0 + 39.9, 2) == 1231.66
    assert k.monate == 24
