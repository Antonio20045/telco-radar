"""Katalog D auf der TCO-Tafel (QA-Befunde S2, S4, S12 vom 04.09.2026).

Dieselbe Fixture wie `test_geraete_tco_zustand._baue` (geraete_db.json,
geraete_tco.json, tarife.jsonl, geraete_preise.jsonl, drei Konfigdateien in
tmp_path). Gemessen wird am gerenderten HTML, weil die Woerter dort stehen.
"""
from __future__ import annotations

from telco_radar.geraete_config import lade_katalog
from telco_radar.report import geraete_tco_grafik as grafik
from telco_radar.report import geraete_tco_karten as karten

from test_geraete_tco_zustand import WURZEL, _baue, _modell


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


def test_die_referenzkarte_behauptet_keine_36_monate(tmp_path):
    """F-R2-2 auf der Seite: Etikett, Rechenweg und Gruppenkopf nennen die
    Bindung der Referenz (24 Tarifmonate, Barkauf bindet nicht)."""
    s = _baue(tmp_path)
    ref = s.select_one('#tafel-tco .gr-kkarte[data-anbieter="Vodafone"]')
    assert ref.select_one(".gr-kk-marke").get_text(strip=True) == "Referenzrechnung"
    assert ref.select_one(".gr-kk-leit b").get_text(strip=True) == "TCO-24"
    assert ref["data-laufzeit"] == "24"
    text = " ".join(ref.get_text(" ", strip=True).split())
    assert "36 Monate Bindung" not in text
    assert "24 Monate Tarifbindung; das Gerät ist bar gekauft und bindet nicht" in text
    assert "binden 36 Monate" in text
    # Das o2-Angebot daneben rechnet weiterhin ueber seine 36 Monate.
    o2 = s.select_one('#tafel-tco .gr-kkarte[data-anbieter="o2"][data-zustand="neu"]')
    assert o2.select_one(".gr-kk-leit b").get_text(strip=True) == "TCO-36"
    assert "Gerechnet über 36 Monate Bindung" in " ".join(o2.get_text(" ", strip=True).split())


def test_die_tafel_spricht_katalog_d(tmp_path):
    s = _baue(tmp_path)
    tafel = s.select_one("#tafel-tco")
    band = " ".join(tafel.select_one(".gr-mband").get_text(" ", strip=True).split())
    assert "TCO-36 von" in band and "Gesamtkosten" not in band
    assert tafel.select_one("h3.gr-tueber").get_text(strip=True) == "Apple iPhone 15 128 GB"
    option = tafel.select_one('select[data-sortiere] option[value="gesamt"]')
    assert option.get_text(strip=True) == "TCO je Laufzeitgruppe"
    assert [th.get_text(strip=True) for th in tafel.select("#gr-tco-tabelle th")][2] == "TCO"
    assert "Gesamtkosten" not in tafel.select_one("figure.gr-grafik figcaption").get_text()
    # Ratenzeile: "X € in 36 Raten" - die Summe aus der Kennzahl.
    o2 = tafel.select_one('.gr-kkarte[data-anbieter="o2"][data-zustand="neu"]')
    bau = " ".join(o2.select_one(".gr-kk-bau").get_text(" ", strip=True).split())
    assert "720,00 € in 36 Raten à 20,00 €" in bau
    # Kein "(0 %)" auf einer TCO-Karte: der Zinssatz ist dort nicht gemessen.
    assert "(0 %)" not in tafel.get_text(" ")
