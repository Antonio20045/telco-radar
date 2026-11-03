"""Punkt 3: die Δ-Zelle der Tabelle „Alle Geräte“ sagt in Worten, ob günstiger.

„−193,79 € · −9,9 %“ verlangte vom Leser, das Vorzeichen zu deuten. Die Zelle
nennt jetzt „193,79 € günstiger · 9,9 %“ (oder „teurer“). Das Wort entsteht an
einer Stelle (`geraete_delta_wort.delta_wort`), Seite und Feld
`tco_delta_wort` lesen dasselbe.
"""

from __future__ import annotations

import json

from bs4 import BeautifulSoup
from test_laufzeit_vergleich import HEUTE, baue

from telco_radar.report import geraete_delta_wort
from telco_radar.report.html import render_site


def baue_site(tmp_path):
    root, _ = baue(tmp_path)
    reports = root / "data" / "reports"
    reports.mkdir(parents=True)
    bericht = {
        "date": HEUTE,
        "language": "de",
        "briefing_md": "## Auf einen Blick\n\n- Nichts.\n",
        "stats": {},
        "regions": [],
    }
    (reports / f"{HEUTE}.json").write_text(json.dumps(bericht), encoding="utf-8")
    (reports / f"{HEUTE}.md").write_text("# Bericht\n", encoding="utf-8")
    site = root / "site"
    render_site(site, reports)
    return site


def test_delta_wort_nennt_guenstiger_und_teurer_mit_dem_betrag():
    wort = geraete_delta_wort.delta_wort
    assert wort(-193.79, 9.9) == "193,79 € günstiger · 9,9 %"
    assert wort(100.0, 9.1) == "100,00 € teurer · 9,1 %"
    assert wort(-1234.5, None) == "1.234,50 € günstiger"
    assert wort(0.0, None) == "gleich teuer"
    assert wort(None, 9.9) is None


def test_delta_wort_einer_naeherung_bleibt_ungefaehr():
    wort = geraete_delta_wort.delta_wort
    assert wort(7.74, None, ungefaehr=True) == "rund 7,74 € teurer"
    assert wort(-7.74, None, ungefaehr=True) == "rund 7,74 € günstiger"


def test_die_modellzeile_traegt_das_wort_zum_abstand():
    """congstar 1.000 gegen Vodafone 1.100: 100,00 € günstiger (Feld und Zahl)."""
    felder = {
        "tco_delta": -100.0,
        "tco_delta_prozent": 9.1,
        "tco_delta_kurz": "−100,00 € · −9,1 %",
    }
    zeile = geraete_delta_wort.ergaenze(felder, None)
    assert zeile["tco_delta"] == -100.0
    assert zeile["tco_delta_wort"] == "100,00 € günstiger · 9,1 %"
    naeherung = {
        **felder,
        "tco_delta": 7.74,
        "tco_delta_prozent": None,
        "tco_delta_kurz": "≈ +7,74 €",
    }
    assert (
        geraete_delta_wort.ergaenze(naeherung, None)["tco_delta_wort"]
        == "rund 7,74 € teurer"
    )


def test_gegenprobe_ohne_abstand_kein_wort():
    felder = {"tco_delta": None, "tco_delta_prozent": None, "tco_delta_kurz": None}
    zeile = geraete_delta_wort.ergaenze(felder, None)
    assert zeile["tco_delta_wort"] is None
    assert zeile["tco_vodafone_teurer"] is None


def test_die_seite_schreibt_das_wort_in_die_delta_zelle(tmp_path):
    """Jede Δ-Zelle mit Abstand trägt das Wort passend zum Vorzeichen der
    Sortierzahl (`data-s-delta`) und nie das nackte Minus."""
    site = baue_site(tmp_path)
    suppe = BeautifulSoup(
        (site / "geraete.html").read_text(encoding="utf-8"), "html.parser"
    )
    gesehen = 0
    for z in suppe.select("#gr-katalogtabelle .gr-k-zeile"):
        wert = z.get("data-s-delta")
        zelle = z.select("td.gr-sp--tco")[2]
        if not wert or zelle.select_one(".wr-prozent") is None:
            continue
        gesehen += 1
        text = zelle.get_text(" ", strip=True)
        richtig, falsch = (
            ("günstiger", "teurer") if float(wert) < 0 else ("teurer", "günstiger")
        )
        assert richtig in text and falsch not in text, text
        assert (
            f"{abs(float(wert)):,.2f}".replace(",", "#")
            .replace(".", ",")
            .replace("#", ".")
            in text
        ), text
        assert "−" not in text and "+" not in text, text
    assert gesehen, "die Fixture hat keine Δ-Zelle mit Abstand"


def test_die_katalogzahl_traegt_ihr_wort_und_die_kostenzelle_ihren_tarif(tmp_path):
    """Die nackte Zahl neben „Alle Geräte“ heißt „Modelle“ und ist die Zahl der
    Tabellenzeilen; der „ab“-Betrag nennt den Tarif, aus dem er stammt."""
    site = baue_site(tmp_path)
    suppe = BeautifulSoup(
        (site / "geraete.html").read_text(encoding="utf-8"), "html.parser"
    )
    zeilen = suppe.select("#gr-katalogtabelle tr.gr-k-zeile")
    kopf = suppe.select_one(".gr-katalog h2")
    assert kopf.get_text(" ", strip=True).endswith(f"{len(zeilen)} Modelle")
    mit_kosten = [z for z in zeilen if z.select_one(".gr-k-ab")]
    assert mit_kosten
    for z in mit_kosten:
        kosten = z.select("td.gr-sp--tco")[0].get_text(" ", strip=True)
        band = z.select("td.gr-sp--tco")[3].get_text(strip=True)
        assert f"Tarif {band}" in kosten, kosten
