"""Antwortsatz der Geräteseite: jeder Anbieter genau EINMAL, ohne toten Verweis.

Befund des Prüfers zu PR 207 (21.11.2026): „steht kein Bündel im Vergleich:
o2 (Plus: 5,00 € günstiger mit Zweitprodukt), o2 (Rabatt nur mit Zweitprodukt),
o2 (nicht direkt genannt).“ - derselbe Anbieter dreimal, weil ``namen`` je
Anbieter UND Grund einen Eintrag bildete und jeder Plus-Betrag ein eigener Grund
war. Darunter verwies der Leersatz der Zeitreihe auf „Bündel-Zeilen darunter“,
die app.js seit dem 10.10.2026 verwirft.

Die Beträge kommen aus dem vorhandenen Feld ``plus_vorteil``; report/ rechnet
nichts, es wählt nur den größten genannten Betrag („bis“).
"""

from __future__ import annotations

import html
import re
import shutil

import pytest
from bestand_pfad import ZUSTAND, lese_wurzel
from test_geraete_zeitreihe_ansicht import baue

from telco_radar.geraete_config import lade_katalog, lade_quellen
from telco_radar.report import geraete_notbremse as notbremse
from telco_radar.report import geraete_view, geraete_zeitreihe

LISTEN = ("steht kein Bündel im Vergleich: ", "Nicht im Vergleich: ")


def _plus(betrag: float | None) -> dict:
    return {
        "anbieter": "o2",
        "bedingter_tarif": True,
        "plus_vorteil": betrag,
        "zaehlt": False,
    }


def _schaetzung(anbieter: str = "o2") -> dict:
    return {"anbieter": anbieter, "schaetzung": True, "zaehlt": False}


@pytest.fixture(scope="module")
def saetze(tmp_path_factory) -> list[str]:
    """Die Antwortsätze aller Paare am festen Bestand (2026-10-03)."""
    zustand = tmp_path_factory.mktemp("antwort-je-anbieter") / "state"
    shutil.copytree(ZUSTAND, zustand)
    wurzel = lese_wurzel()
    geraete = geraete_view.aufbereiten(
        zustand, lade_quellen(wurzel), lade_katalog(wurzel), heute="2026-10-03"
    )
    return [
        html.unescape(re.sub(r"<[^>]+>", "", p["antwort_html"]))
        for p in geraete["zeitreihe"]["paare"]
    ]


def _eintraege(satz: str) -> list[str]:
    """Die Anbieter der Liste „… im Vergleich: a (…), b (…).“ in Reihenfolge."""
    for kopf in LISTEN:
        if kopf in satz:
            liste = re.sub(r"\([^()]*\)", "", satz.split(kopf, 1)[1]).rstrip(". ")
            return [teil.strip() for teil in liste.split(",")]
    return []


def test_antwortsatz_nennt_jeden_anbieter_genau_einmal(saetze):
    mit_liste = [s for s in saetze if _eintraege(s)]
    assert mit_liste, "Fall fehlt: kein Antwortsatz mit gesperrten Anbietern"
    doppelt = [s for s in mit_liste if len(set(_eintraege(s))) < len(_eintraege(s))]
    assert not doppelt, (
        f"{len(doppelt)} Sätze nennen einen Anbieter mehrfach: {doppelt[:2]}"
    )


def test_gegenprobe_bestand_hat_einen_anbieter_mit_zwei_gruenden(saetze):
    """Ohne diesen Fall prüft der Test oben nichts: am Bestand hat o2 im selben
    Paar Schätzung UND Zweitprodukt-Rabatt."""
    assert any(" oder " in s for s in saetze if _eintraege(s))


def test_mehrere_plus_betraege_werden_zu_bis_dem_groessten():
    assert notbremse.namen([_plus(5.0), _plus(10.0)]) == [
        "o2 (Plus: bis 10,00 € günstiger mit Zweitprodukt)"
    ]


def test_zwei_gruende_desselben_anbieters_stehen_in_einer_klammer():
    eintraege = notbremse.namen([_plus(5.0), _schaetzung()])
    assert eintraege == [
        "o2 (Plus: 5,00 € günstiger mit Zweitprodukt oder nicht direkt genannt)"
    ]


def test_plus_ohne_betrag_neben_betrag_nennt_keinen_betrag():
    """Fehlt bei einem Plus-Tarif der Betrag, ist „bis 5,00 €“ nicht belegt:
    dann steht der Grund ohne Zahl (fehlender Wert ist eine Lücke, keine 0)."""
    assert notbremse.namen([_plus(5.0), _plus(None)]) == [
        "o2 (Rabatt nur mit Zweitprodukt)"
    ]


def test_gegenprobe_ein_betrag_und_zwei_anbieter_bleiben_wie_bisher():
    assert notbremse.namen([_plus(5.0), _plus(5.0)]) == [
        "o2 (Plus: 5,00 € günstiger mit Zweitprodukt)"
    ]
    assert notbremse.namen([_schaetzung("1&1"), _plus(5.0)]) == [
        "1&1 (nicht direkt genannt)",
        "o2 (Plus: 5,00 € günstiger mit Zweitprodukt)",
    ]


def test_leersatz_der_zeitreihe_verweist_nicht_auf_buendel_zeilen():
    slot = {"o2": {"2026-11-20": _plus(5.0), "2026-11-21": _schaetzung()}}
    satz = notbremse.leersatz(slot)
    assert satz is not None
    assert "nicht im Vergleich" in satz
    assert "Bündel-Zeilen" not in satz, satz


def test_gegenprobe_leersatz_ohne_messungen_bleibt_none():
    assert notbremse.leersatz({}) is None


def test_satz_ohne_historie_verweist_nicht_auf_buendel_zeilen(tmp_path):
    root, state = baue(tmp_path)
    (state / "geraete_tco_historie.jsonl").write_text("", encoding="utf-8")
    g = geraete_view.aufbereiten(
        state, lade_quellen(root), lade_katalog(root), heute="2026-09-16"
    )
    a = geraete_zeitreihe.aufbereiten(state, g["tco"])
    leer = [p["leer_text"] for p in a["paare"] if p["leer_text"]]
    assert leer, "Fall fehlt: kein Paar ohne Messreihe"
    assert not [t for t in leer if "Bündel-Zeilen" in t], leer[:2]
