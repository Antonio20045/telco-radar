"""Notbremse in der Modellzeile: bestes Bündel und Spanne ohne Schätzung.

Die Modellzeile des Gerätekatalogs nennt je Modell das beste Bündel
(„Kosten über 24 Monate ab X bei Y“) und die Spanne der Einzelgerätepreise.
Eine Karte, die nicht zählt (Schätzung oder abgelaufene Aktion, Feld
``zaehlt``), stellt keins von beiden; fehlt danach ein bestes Bündel, nennt
die Zeile die Lücke. Gemessen am Bestand vom 2026-10-03 über den öffentlichen
Eingang ``geraete_view.aufbereiten`` und an der gerenderten Seite.
"""

from __future__ import annotations

import json
import shutil

import pytest
from bestand_pfad import ZUSTAND, abbild, lese_wurzel
from bs4 import BeautifulSoup

from telco_radar.config import load_config
from telco_radar.geraete_config import lade_katalog, lade_quellen
from telco_radar.report import geraete_view
from telco_radar.report.html import render_site

HEUTE = "2026-10-03"
MELDUNG_BESTES = "Bestes Bündel: erwartet ohne Schätzung"
MELDUNG_SPANNE = "Spanne: erwartet ohne Schätzung"


MODELL_NUR_SCHAETZUNG = "xiaomi-redmi-note-15-256"
"""Gemessene Bündel von Vodafone und o2, geschätzte von o2 (Bestand 2026-10-03)."""


def _aufbereiten(zustand):
    wurzel = lese_wurzel()
    return geraete_view.aufbereiten(
        zustand, lade_quellen(wurzel), lade_katalog(wurzel), heute=HEUTE
    )


@pytest.fixture(scope="module")
def daten(tmp_path_factory):
    zustand = tmp_path_factory.mktemp("notbremse-view") / "state"
    shutil.copytree(ZUSTAND, zustand)
    return _aufbereiten(zustand)


@pytest.fixture(scope="module")
def tco_zellen(tmp_path_factory) -> list:
    """(Modell, Wert der Spalte „Kosten über 24 Monate“) je gerenderter Zeile."""
    ziel = tmp_path_factory.mktemp("notbremse-seite")
    render_site(ziel / "site", abbild(ziel), load_config(ziel))
    html = (ziel / "site" / "geraete.html").read_text(encoding="utf-8")
    zeilen = BeautifulSoup(html, "html.parser").select(
        "#gr-katalogtabelle tr.gr-k-zeile"
    )
    return [(tr["data-modell"], tr.get("data-s-tco") or "") for tr in zeilen]


def _karten_je_modell(daten) -> dict:
    return {m["id"]: m["karten"] for m in daten["tco"]["modelle"]}


def _traeger(karten: list, anbieter, gesamt) -> list:
    return [
        k
        for k in karten
        if k.get("gesamt") == gesamt and (anbieter is None or k["anbieter"] == anbieter)
    ]


def test_bestes_buendel_nur_aus_zaehlenden_karten(daten):
    karten = _karten_je_modell(daten)
    falsch = []
    for zeile in daten["katalog_modelle"]:
        if zeile["tco_ab"] is None:
            continue
        traeger = _traeger(
            karten.get(zeile["schluessel"], []), zeile["tco_anbieter"], zeile["tco_ab"]
        )
        if not any(k.get("zaehlt", True) for k in traeger):
            falsch.append(
                f"{zeile['schluessel']}: {zeile['tco_anbieter']} {zeile['tco_ab']}"
            )
    assert not falsch, (
        f"{MELDUNG_BESTES} – {len(falsch)} Modellzeilen nennen eine Karte, "
        f"die nicht zählt (z. B. {falsch[:3]})"
    )


def test_gerenderte_zeile_zeigt_kein_geschaetztes_buendel(daten, tco_zellen):
    karten = _karten_je_modell(daten)
    assert tco_zellen, "Katalogtabelle ohne Modellzeilen"
    assert any(wert for _, wert in tco_zellen), "keine Zeile zeigt ein bestes Bündel"
    falsch = []
    for modell, wert in tco_zellen:
        if not wert:
            continue
        traeger = _traeger(karten.get(modell, []), None, float(wert))
        if traeger and all(k.get("schaetzung") for k in traeger):
            falsch.append(f"{modell}: {wert}")
    assert not falsch, f"{MELDUNG_BESTES} – auf der Seite: {falsch[:3]}"


def test_ohne_bestes_buendel_benannte_luecke(daten):
    zeilen = daten["katalog_modelle"]
    stumm = [
        z["schluessel"] for z in zeilen if z["tco_ab"] is None and not z["tco_leer"]
    ]
    null = [z["schluessel"] for z in zeilen if z["tco_ab"] == 0]
    assert not stumm, f"Bestes Bündel fehlt ohne benannte Lücke: {stumm[:3]}"
    assert not null, f"Bestes Bündel als 0 statt Lücke: {null[:3]}"


def test_nur_geschaetzte_buendel_heissen_schaetzung(tmp_path):
    """Bleiben einem Modell nur Schätzungen, nennt die Zeile die Lücke beim
    Namen der Karte, statt eine Schätzung als bestes Bündel zu zeigen."""
    zustand = tmp_path / "state"
    shutil.copytree(ZUSTAND, zustand)
    datei = zustand / "geraete_tco.json"
    roh = json.loads(datei.read_text(encoding="utf-8"))
    praefix = f"{MODELL_NUR_SCHAETZUNG}gb-"
    vorher = len(roh["buendel"])
    roh["buendel"] = [
        b
        for b in roh["buendel"]
        if not b["sku_id"].startswith(praefix) or (b.get("herleitung") or "").strip()
    ]
    assert len(roh["buendel"]) < vorher, "Modell ohne gemessene Bündel im Bestand"
    datei.write_text(json.dumps(roh, ensure_ascii=False), encoding="utf-8")
    zeile = next(
        z
        for z in _aufbereiten(zustand)["katalog_modelle"]
        if z["schluessel"] == MODELL_NUR_SCHAETZUNG
    )
    assert zeile["hat_buendel"], "Modell verliert mit den Messungen die Zeile"
    assert (zeile["tco_ab"], zeile["tco_leer"]) == (None, "nicht direkt genannt"), (
        f"{MELDUNG_BESTES} – {MODELL_NUR_SCHAETZUNG}: "
        f"{zeile['tco_anbieter']} {zeile['tco_ab']}, Lücke {zeile['tco_leer']!r}"
    )


def test_gemessene_karten_liefern_weiter_ein_bestes_buendel(daten):
    karten = _karten_je_modell(daten)
    gemessen = [
        z
        for z in daten["katalog_modelle"]
        if z["tco_ab"] is not None
        and any(
            k["zaehlt"]
            for k in _traeger(
                karten.get(z["schluessel"], []), z["tco_anbieter"], z["tco_ab"]
            )
        )
    ]
    assert len(gemessen) >= 50, (
        f"nur {len(gemessen)} Modellzeilen mit gemessenem bestem Bündel"
    )


def test_spanne_nur_aus_einzelgeraetepreisen(daten):
    """Die Spanne der Modellzeile reicht vom günstigsten zum teuersten
    Einzelgerätepreis der Händler; keine Bündelkarte, also keine Schätzung,
    stellt eine ihrer Grenzen."""
    mit_spanne = [z for z in daten["katalog_modelle"] if z["spanne"]]
    assert mit_spanne, "keine Modellzeile trägt eine Spanne"
    karten = _karten_je_modell(daten)
    falsch = []
    for zeile in mit_spanne:
        preise = {
            round(z["preis"], 2) for z in zeile["zeilen"] if z["preis"] is not None
        }
        nicht_zaehlend = {
            k["gesamt"]
            for k in karten.get(zeile["schluessel"], [])
            if not k.get("zaehlt", True)
        }
        for grenze in zeile["spanne"]:
            if grenze not in preise or grenze in nicht_zaehlend:
                falsch.append(f"{zeile['schluessel']}: {grenze}")
    assert not falsch, (
        f"{MELDUNG_SPANNE} – Grenzen ohne Einzelgerätepreis: {falsch[:3]}"
    )
