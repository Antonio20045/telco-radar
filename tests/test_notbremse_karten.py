"""Notbremse der Geräteseite: eine Schätzung geht nie in Sieger oder Δ ein.

Ein Bündel mit ``herleitung`` (1&1 aus dem Tarifraster, o2 aus Tarifsumme
minus Geräterate) stand so nie auf der Anbieterseite. Es bleibt als Zeile
sichtbar, aber keine Karte daraus trägt ein Δ zu Vodafone, und kein Modell
nennt es als günstigsten Tarif. Gemessen am Bestand vom 2026-10-03 über den
öffentlichen Eingang ``geraete_view.aufbereiten``.
"""

from __future__ import annotations

import json
import shutil

import pytest
from bestand_pfad import ZUSTAND, lese_wurzel

from telco_radar.geraete_config import lade_katalog, lade_quellen
from telco_radar.report import geraete_view

HEUTE = "2026-10-03"
MELDUNG = "Schätzung: erwartet kein Δ und kein Sieger"


def _schluessel(sku, anbieter, tarif, laufzeit) -> tuple:
    texte = tuple((t or "").strip() for t in (sku, anbieter, tarif))
    return (*texte, laufzeit)


@pytest.fixture(scope="module")
def bestand(tmp_path_factory):
    zustand = tmp_path_factory.mktemp("notbremse") / "state"
    shutil.copytree(ZUSTAND, zustand)
    saetze = json.loads((ZUSTAND / "geraete_tco.json").read_text(encoding="utf-8"))
    geschaetzt = {
        _schluessel(s["sku_id"], s["anbieter"], s["tarif_name"], s["laufzeit_monate"])
        for s in saetze["buendel"]
        if (s.get("herleitung") or "").strip()
    }
    wurzel = lese_wurzel()
    geraete = geraete_view.aufbereiten(
        zustand, lade_quellen(wurzel), lade_katalog(wurzel), heute=HEUTE
    )
    return geraete["tco"]["modelle"], geschaetzt


def _ist_schaetzung(karte: dict, geschaetzt: set) -> bool:
    if karte.get("aus_listung") or not karte.get("sku_id"):
        return False
    sku, anbieter, tarif = karte["sku_id"], karte["anbieter"], karte["tarif"]
    return _schluessel(sku, anbieter, tarif, karte["raten_laufzeit"]) in geschaetzt


def test_bestand_traegt_schaetzungen_auf_der_seite(bestand):
    modelle, geschaetzt = bestand
    assert len(geschaetzt) > 100, "Bestand ohne abgeleitete Bündel"
    alle = [k for m in modelle for k in m["karten"]]
    zeilen = [k for k in alle if _ist_schaetzung(k, geschaetzt)]
    assert {k["anbieter"] for k in zeilen} >= {"1&1", "o2"}, (
        "Schätzungen sollen als Zeile sichtbar bleiben, nicht verschwinden"
    )


def test_schaetzung_ohne_delta_und_nie_sieger(bestand):
    modelle, geschaetzt = bestand
    mit_delta = []
    sieger = []
    for modell in modelle:
        schaetzungen = [k for k in modell["karten"] if _ist_schaetzung(k, geschaetzt)]
        mit_delta += [
            f"{modell['id']} {k['anbieter']} {k['tarif']} {k['raten_laufzeit']}: "
            f"Δ {k['delta']['betrag']}"
            for k in schaetzungen
            if k.get("delta") is not None
        ]
        antwort = modell["antwort"]
        if antwort["tarif_gesamt"] is None:
            continue
        traeger = [
            k
            for k in modell["karten"]
            if k["anbieter"] == antwort["tarif_anbieter"]
            and k["gesamt"] == antwort["tarif_gesamt"]
        ]
        if traeger and all(_ist_schaetzung(k, geschaetzt) for k in traeger):
            wer, wieviel = antwort["tarif_anbieter"], antwort["tarif_gesamt"]
            sieger.append(f"{modell['id']}: {wer} {wieviel}")
    assert not mit_delta and not sieger, (
        f"{MELDUNG} – {len(mit_delta)} Karten mit Δ (z. B. {mit_delta[:3]}), "
        f"{len(sieger)} Modelle mit Schätzung als Sieger (z. B. {sieger[:3]})"
    )


def test_gemessene_karten_behalten_delta_und_sieger(bestand):
    modelle, geschaetzt = bestand
    gemessen_mit_delta = [
        k
        for m in modelle
        for k in m["karten"]
        if k.get("delta") is not None and not _ist_schaetzung(k, geschaetzt)
    ]
    mit_sieger = [m for m in modelle if m["antwort"]["tarif_gesamt"] is not None]
    assert gemessen_mit_delta, "gemessene Karten verlieren ihr Δ"
    assert mit_sieger, "kein Modell nennt mehr einen günstigsten Tarif"


def test_abgelaufene_aktion_macht_den_satz_veraltet(bestand):
    """Eine eingerechnete Aktion, die vor dem Bezugstag endete, steckt noch im
    Preis; der Satz ist veraltet und stellt weder Δ noch Sieger."""
    modelle, _ = bestand
    alle = [k for m in modelle for k in m["karten"] if not k.get("aus_listung")]
    veraltet = [k for k in alle if k.get("veraltet_aktion")]
    assert veraltet, "Aktion abgelaufen: erwartet markierte Karten im Bestand"
    mit_delta = [k for k in veraltet if k.get("delta") is not None]
    assert not mit_delta, f"Aktion abgelaufen: {len(mit_delta)} Karten mit Δ"
    assert all(not k["zaehlt"] for k in veraltet)
    assert {k["anbieter"] for k in veraltet} == {"congstar"}
