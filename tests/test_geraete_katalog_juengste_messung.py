"""Katalogzeile "ab X bei Y": je Anbieter zählt die JÜNGSTE Messung.

Befund Live-Abnahme 03.11.2026 (iPhone 17 256 GB): Saturn führt je Farbe eine
eigene Listung mit eigenem Abrufdatum. Die Farbe vom Vortag stand noch mit
1.019 EUR im Frischefenster, die Farbe von heute mit 1.089 EUR - der Katalog
nahm das Minimum über beide und zeigte "ab 1.019 bei Saturn", während der
Verlauf (letzter Punkt je Anbieter) 1.089 zeigte. Ein Anbieter hat EINEN
aktuellen Preis: den der jüngsten Messung (Clean Code 1).

Alle Daten sind synthetisch und setzen ihr Datum selbst.
"""

from __future__ import annotations

from bestand_pfad import lese_wurzel

from telco_radar.geraete_config import lade_katalog
from telco_radar.report import geraete_view

HEUTE = "2026-11-03"
GESTERN = "2026-11-02"
DEVICE = "apple-iphone-17"


def _listung(anbieter, farbe, preis, tag):
    sku = f"{DEVICE}-256gb-{farbe}"
    return {
        "id": f"{anbieter.lower()}--{sku}",
        "sku_id": sku,
        "device_id": DEVICE,
        "anbieter": anbieter,
        "speicher_gb": 256,
        "zustand": "neu",
        "status": "aktiv",
        "preis_ohne_vertrag": preis,
        "quelle_url": f"https://{anbieter.lower()}.invalid/{farbe}",
        "abgerufen_am": tag,
    }


def _zeile(listungen):
    katalog = lade_katalog(lese_wurzel())
    zeilen = geraete_view.katalog_modellzeilen(listungen, katalog, heute=HEUTE)
    (zeile,) = [z for z in zeilen if z["device_id"] == DEVICE]
    return zeile


def test_ab_preis_nimmt_die_juengste_messung_je_anbieter():
    zeile = _zeile(
        [
            _listung("Saturn", "gruen", 1019.0, GESTERN),
            _listung("Saturn", "weiss", 1089.0, HEUTE),
            _listung("congstar", "weiss", 1063.0, HEUTE),
        ]
    )
    assert zeile["ab_preis"] == 1063.0
    assert zeile["ab_anbieter"] == "congstar"
    assert zeile["spanne"] in ([], [1063.0, 1089.0])


def test_gleiche_messung_gleicher_tag_nimmt_den_tieferen_preis():
    zeile = _zeile(
        [
            _listung("Saturn", "gruen", 1019.0, HEUTE),
            _listung("Saturn", "weiss", 1089.0, HEUTE),
            _listung("congstar", "weiss", 1063.0, HEUTE),
        ]
    )
    assert zeile["ab_preis"] == 1019.0
    assert zeile["ab_anbieter"] == "Saturn"
