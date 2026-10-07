"""Notbremse in der Δ-Zelle der eigenen Zeile: „Referenz“ nur, wenn die Karte zählt.

Eine Vodafone-Zeile, deren Preis eine Schätzung ist oder eine abgelaufene Aktion
enthält, stellt keine Referenz (``geraete_tco_karten``: die Referenz nimmt nur
Karten, die zählen). Ihre Δ-Zelle nennt dann den Zustand der Notbremse, nicht
„Referenz“.

Gerendert aus dem Bestand vom 2026-10-03; darin werden die Vodafone-Bündel zweier
Modelle zur Schätzung bzw. zum Satz mit abgelaufener Aktion. Orakel ist diese
Änderung selbst, die übrigen Vodafone-Zeilen bleiben „Referenz“ (Gegenprobe).
Gelesen werden die Zeilen MIT Zahl: eine Zeile ohne vollständigen Preis (seit
Datenkonzept Geräte Schritt 2 etwa Vodafone mit 36 Raten, das Tarifblatt nennt
keinen Preis ab Monat 25) stellt nie eine Referenz und trägt den Strich.
"""

from __future__ import annotations

import json

import pytest
from bestand_pfad import abbild
from bs4 import BeautifulSoup

from telco_radar.config import load_config
from telco_radar.report.html import render_site

ABGELAUFEN = {
    "art": "anschluss_erlassen",
    "bedingung": "Online-Aktion",
    "quelle_url": "https://example.de/vodafone/aktion",
    "eingerechnet": True,
    "gueltig_bis": "2026-09-01",
}
GESPERRT = {
    "apple-iphone-16-128": ("berechnet", {"herleitung": "tarifsumme_minus_rate"}),
    "apple-iphone-17-256": ("Aktion abgelaufen", {"aktionen": [ABGELAUFEN]}),
}
"""Modell → (erwartete Δ-Zelle, Felder an seinen Vodafone-Bündeln)."""


@pytest.fixture(scope="module")
def delta_zellen(tmp_path_factory) -> dict[str, list[str]]:
    """Δ-Zellen der Vodafone-Zeilen je Modell des Bündel-Fragments."""
    wurzel = tmp_path_factory.mktemp("notbremse-referenz")
    berichte = abbild(wurzel)
    datei = wurzel / "data" / "state" / "geraete_tco.json"
    tco = json.loads(datei.read_text(encoding="utf-8"))
    for b in tco["buendel"]:
        for modell, (_, felder) in GESPERRT.items():
            if b["anbieter"] == "Vodafone" and b["sku_id"].startswith(f"{modell}gb-"):
                b.update(felder)
    datei.write_text(json.dumps(tco), encoding="utf-8")
    render_site(wurzel / "site", berichte, load_config(wurzel))
    fragment = wurzel / "site" / "data" / "geraete-buendel.html"
    lager = BeautifulSoup(fragment.read_text(encoding="utf-8"), "html.parser")
    zeilen = {
        modell["data-modell"]: modell.select('details.gr-bnd[data-anbieter="Vodafone"]')
        for modell in lager.select(".gr-bnd-lager[data-modell]")
    }
    ohne_zahl = {
        z.select_one(".gr-bnd-delta").get_text(" ", strip=True)
        for liste in zeilen.values()
        for z in liste
        if not z.get("data-gesamt")
    }
    assert ohne_zahl == {"–"}, ohne_zahl
    return {
        modell: [
            z.select_one(".gr-bnd-delta").get_text(" ", strip=True)
            for z in liste
            if z.get("data-gesamt")
        ]
        for modell, liste in zeilen.items()
    }


@pytest.mark.parametrize("modell", sorted(GESPERRT))
def test_eigene_zeile_die_nicht_zaehlt_ist_keine_referenz(delta_zellen, modell):
    kurz = GESPERRT[modell][0]
    zellen = delta_zellen[modell]
    assert zellen, f"Fall fehlt: keine Vodafone-Zeile bei {modell}"
    assert set(zellen) == {kurz}, (
        f"{modell}: Δ-Zelle der eigenen Zeile {sorted(set(zellen))}, erwartet „{kurz}“"
    )


def test_gegenprobe_eigene_zeile_die_zaehlt_bleibt_referenz(delta_zellen):
    uebrige = [
        zelle
        for modell, zellen in delta_zellen.items()
        if modell not in GESPERRT
        for zelle in zellen
    ]
    assert uebrige, "Gegenprobe: Vodafone-Zeilen anderer Modelle fehlen"
    assert set(uebrige) == {"Referenz"}, sorted(set(uebrige))
