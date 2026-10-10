"""Notbremse: die Preisspanne eines Modells nimmt nur Karten, die zählen.

Datenkonzept Geräteradar, Abschnitt 4 Regel 1: eine Schätzung oder ein Satz mit
abgelaufener Aktion geht nie in Sieger oder Kernzahl ein. Günstigster Tarif und
Spanne teilen dieselbe Definition, also ist das untere Ende der Spanne der
günstigste Tarif. Gemessen am Bestand vom 2026-10-03 über den öffentlichen
Eingang ``geraete_view.aufbereiten``.
"""

from __future__ import annotations

import shutil

import pytest
from bestand_pfad import ZUSTAND, lese_wurzel

from telco_radar.geraete_config import lade_katalog, lade_quellen
from telco_radar.report import geraete_view

HEUTE = "2026-10-03"


@pytest.fixture(scope="module")
def modelle(tmp_path_factory):
    zustand = tmp_path_factory.mktemp("notbremse-spanne") / "state"
    shutil.copytree(ZUSTAND, zustand)
    wurzel = lese_wurzel()
    geraete = geraete_view.aufbereiten(
        zustand, lade_quellen(wurzel), lade_katalog(wurzel), heute=HEUTE
    )
    return geraete["tco"]["modelle"]


def _im_vergleich(karte: dict) -> bool:
    """Ein gemessenes, frisches Angebot mit Zahl - mit oder ohne Notbremse."""
    return bool(
        karte.get("belastbar")
        and not karte.get("naeherung")
        and karte.get("vergleichbar")
        and karte.get("frisch")
        and karte.get("gesamt") is not None
    )


def test_spanne_nimmt_nur_karten_die_zaehlen(modelle):
    falsch = []
    for modell in modelle:
        if not modell["spanne"]:
            continue
        unten, oben = modell["spanne"]
        zaehlen = {k["gesamt"] for k in modell["karten"] if k.get("zaehlt", True)}
        if (
            unten != modell["antwort"]["tarif_gesamt"]
            or unten not in zaehlen
            or oben not in zaehlen
        ):
            falsch.append(
                f"{modell['id']} {modell['spanne']} "
                f"(günstigster Tarif {modell['antwort']['tarif_gesamt']})"
            )
    assert not falsch, (
        f"Spanne: erwartet ohne Schätzung, {len(falsch)} Modelle reichen über "
        f"Karten, die nicht zählen (z. B. {falsch[:3]})"
    )


def test_schaetzungen_bleiben_zeilen_ausserhalb_der_spanne(modelle):
    """Gegenprobe: die Notbremse greift am Bestand, und sie leert die Spanne
    nicht - die Schätzung bleibt Zeile, sie zählt nur nicht mit. Beim iPhone 17
    Pro liegt sie seit 10.10.2026 innerhalb: 1&1 steht mit 24 Monaten plus
    Ablöse in der Spanne und weitet sie."""
    mit_spanne = [m for m in modelle if m["spanne"]]
    ausserhalb = [
        m["id"]
        for m in mit_spanne
        if any(
            _im_vergleich(k)
            and not k["zaehlt"]
            and not m["spanne"][0] <= k["gesamt"] <= m["spanne"][1]
            for k in m["karten"]
        )
    ]
    assert len(mit_spanne) >= 90, f"nur {len(mit_spanne)} Modelle mit Spanne"
    assert ausserhalb, "keine Schätzung außerhalb einer Spanne - Fall fehlt"
    assert "samsung-galaxy-s25-fe-128" in ausserhalb, ausserhalb
