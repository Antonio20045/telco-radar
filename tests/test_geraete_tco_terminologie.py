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
    """Ticket TCO24-1 (08.09.2026): die Leitzahl ist auf der ganzen Seite
    IMMER TCO-24 (AUFTRAG_GERAETESEITE.md §3, "Immer 24 Monate") - kein
    Angebot traegt mehr eine variable Bindung als Vergleichshorizont, und
    keine Referenzkarte rechnet mehr ueber ein fremdes Fenster.

    BRIEF_RAHMEN2 (A-R5): die Leitzahl der Karte ist der Geraetepreis, das
    TCO-Etikett steht als Sekundaerzeile ("mit Tarif: ...").
    """
    s = _baue(tmp_path)
    ref = s.select_one('#tafel-tco .gr-kkarte[data-anbieter="Vodafone"]')
    assert ref.select_one(".gr-kk-marke").get_text(strip=True) == "Referenzrechnung"
    assert ref.select_one(".gr-kk-leit b").get_text(strip=True) == "Gerätepreis"
    zweit = " ".join(ref.select_one(".gr-kk-zweit").get_text(" ", strip=True).split())
    assert zweit == "mit Tarif: TCO-24 1.428,70 €"
    assert ref["data-laufzeit"] == "24"
    text = " ".join(ref.get_text(" ", strip=True).split())
    assert "36 Monate" not in text
    assert "TCO-36" not in text
    assert "24 Monate Tarifbindung; das Gerät ist bar gekauft und bindet nicht" in text
    # Das o2-Angebot daneben rechnet die LEITZAHL ebenfalls ueber 24 Monate -
    # seine Geraeteraten laufen zwar 36 Monate, aber die 12 Raten jenseits
    # des Horizonts stehen als eigener, klar bezeichneter Restbetrag daneben
    # und NICHT in der TCO-Zahl (Abnahmekriterium 2).
    o2 = s.select_one('#tafel-tco .gr-kkarte[data-anbieter="o2"][data-zustand="neu"]')
    assert o2.select_one(".gr-kk-leit b").get_text(strip=True) == "Gerätepreis"
    o2_zweit = " ".join(o2.select_one(".gr-kk-zweit").get_text(" ", strip=True).split())
    assert o2_zweit == "mit Tarif: TCO-24 880,75 €"
    o2_text = " ".join(o2.get_text(" ", strip=True).split())
    assert "TCO-36" not in o2_text and "36 Monate Bindung" not in o2_text
    assert "Gerechnet über 24 Monate Bindung" in o2_text
    assert "danach noch offen: 240,00 € (12 Geräteraten)" in o2_text


def test_die_tafel_spricht_katalog_d(tmp_path):
    s = _baue(tmp_path)
    tafel = s.select_one("#tafel-tco")
    band = " ".join(tafel.select_one(".gr-mband").get_text(" ", strip=True).split())
    # Ein einziges vergleichbares Angebot: "TCO-24 880,75 €", nicht "von
    # 880,75 € bis 880,75 €" - und die Referenzrechnung zaehlt nicht in die
    # Spanne der Angebote (F-R2-2). Ticket TCO24-1: das Etikett ist IMMER
    # TCO-24, nie mehr eine variable Bindung.
    assert "TCO-24 " in band and "TCO-36" not in band and "Gesamtkosten" not in band
    assert " bis " not in band.split("TCO-24")[1].split("·")[0]
    assert tafel.select_one("h3.gr-tueber").get_text(strip=True) == "Apple iPhone 15 128 GB"
    option = tafel.select_one('select[data-sortiere] option[value="gesamt"]')
    assert option.get_text(strip=True) == "TCO je Laufzeitgruppe"
    # A-R5: die Geraetespalte steht VOR der TCO-Spalte.
    ths = [th.get_text(strip=True) for th in tafel.select("#gr-tco-tabelle th")]
    assert ths[2] == "Gerätepreis" and ths[3] == "TCO"
    assert "Gesamtkosten" not in tafel.select_one("figure.gr-grafik figcaption").get_text()
    # Ratenzeile: "X € in 36 Raten" - die Summe aus der Kennzahl.
    o2 = tafel.select_one('.gr-kkarte[data-anbieter="o2"][data-zustand="neu"]')
    bau = " ".join(o2.select_one(".gr-kk-bau").get_text(" ", strip=True).split())
    assert "720,00 € in 36 Raten à 20,00 €" in bau
    # Kein "(0 %)" auf einer TCO-Karte: der Zinssatz ist dort nicht gemessen.
    assert "(0 %)" not in tafel.get_text(" ")
