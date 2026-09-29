"""Katalog D auf der TCO-Tafel (QA-Befunde S2, S4, S12 vom 04.09.2026).

Dieselbe Fixture wie `test_geraete_tco_zustand._baue` (geraete_db.json,
geraete_tco.json, tarife.jsonl, geraete_preise.jsonl, drei Konfigdateien in
tmp_path). Die Seitentests fielen mit dem Neuentwurf der Geräteseite
(29.09.2026); geblieben sind Titel und G1-Delta der Aufbereitung.
"""
from __future__ import annotations

from telco_radar.report import geraete_tco_grafik as grafik
from telco_radar.report import geraete_tco_karten as karten

from test_geraete_tco_zustand import _modell


def test_der_hersteller_steht_nicht_zweimal_im_titel():
    assert karten.titel("Xiaomi", "Xiaomi 17 512 GB") == "Xiaomi 17 512 GB"
    assert karten.titel("Nothing", "Nothing Phone (3) 256 GB") == "Nothing Phone (3) 256 GB"
    assert karten.titel("Apple", "iPhone 15 128 GB") == "Apple iPhone 15 128 GB"
    assert karten.titel("", "iPhone 15 128 GB") == "iPhone 15 128 GB"
    # Und ein echtes Modell aus dem Katalog traegt den Titel.
    assert _modell()["titel"] == "Apple iPhone 15 128 GB"


def test_das_euro_delta_steht_am_g1_balken():
    """S4 / C.1: dieselbe Zahl wie auf der Karte, in der Grafik."""
    modell = _modell()
    neu = next(k for k in modell["karten"] if k["anbieter"] == "o2"
               and k["zustand"] == "neu")
    svg = grafik.balken(modell)
    assert neu["delta"]["guenstiger"]
    erwartet = f'<tspan class="gr-g1-delta">−{grafik.euro(neu["delta"]["abstand"])}</tspan>'
    assert erwartet in svg
    # Die Referenz selbst und das erneuerte Geraet tragen kein Delta.
    assert svg.count("gr-g1-delta") == 1


    # Ohne die Felder druckt KEINER von beiden - die Alt-Zeile steht exakt
    # in test_die_buendelkarte_nennt_die_wahre_dauer_und_die_richtigen_raten
    # (derselbe _baue-Aufruf ohne die zwei Parameter); die offene
    # Einmalzahlung steht als benannte Luecke im Rechenweg, nicht als 0,00
    # in der Finanzzeile.


