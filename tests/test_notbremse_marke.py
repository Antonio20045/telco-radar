"""Notbremse an der Bündelzeile: die Zeile sagt selbst, dass ihr Preis nicht zählt.

Eine Schätzung (Bündel mit ``herleitung``: 1&1 aus dem Tarifraster, o2 aus
Tarifsumme minus Geräterate) trägt an ihrer Zeile die Marke „nicht direkt genannt“
oder, mit Rechnung, den Satz, wie der Preis berechnet ist (Antonio 07.10.2026), ein Satz
mit abgelaufener eingerechneter Aktion (congstar) die Marke „Aktion abgelaufen“.
Gemessene Zeilen tragen keine. Gerendert wird der Bestand vom 2026-10-03 mit
``render_site``; die Karten zum Abgleich kommen über den öffentlichen Eingang
``geraete_view.aufbereiten`` mit demselben Bezugstag wie der Render (Datum der
jüngsten Ausgabe). Die Zeilen stehen auf ``geraete.html`` (Startmodell) und im
Fragment ``data/geraete-buendel.html`` (alle übrigen Modelle), je Modell in der
Folge Bandliste, dann „Ohne Tarifband“.
"""

from __future__ import annotations

import json

import pytest
from bestand_pfad import abbild
from bs4 import BeautifulSoup, SoupStrainer

from telco_radar.config import load_config
from telco_radar.geraete_config import lade_katalog, lade_quellen
from telco_radar.report import geraete_view
from telco_radar.report.html import render_site

SCHAETZUNG = "nicht direkt genannt"
AKTION = "Aktion abgelaufen"


def _marken(an) -> list[str]:
    """Die Marken der Zeile; der Herleitungssatz unter der Rechnung zählt als
    „nicht direkt genannt“."""
    marken = [m.get_text(" ", strip=True) for m in an.select(".gr-kk-marke")]
    kopf = an.find_parent("summary")
    if kopf is not None and kopf.select_one(".gr-bnd-herleitung") is not None:
        marken.append(SCHAETZUNG)
    return marken


def _zeilen(modell: dict) -> list[dict]:
    return [*modell["zeilen_band"], *modell["zeilen_ohne_band"]]


@pytest.fixture(scope="module")
def paare(tmp_path_factory) -> list[tuple[dict, list[str]]]:
    """Jede Karte mit den Marken ihrer gerenderten Zeile, Seite und Fragment."""
    wurzel = tmp_path_factory.mktemp("notbremse-marke")
    berichte = abbild(wurzel)
    site = wurzel / "site"
    render_site(site, berichte, load_config(wurzel))
    juengste = sorted(berichte.glob("*.json"))[-1]
    heute = json.loads(juengste.read_text(encoding="utf-8"))["date"]
    geraete = geraete_view.aufbereiten(
        wurzel / "data" / "state",
        lade_quellen(wurzel),
        lade_katalog(wurzel),
        heute=heute,
    )
    tco = geraete["tco"]
    karten_seite: list[dict] = []
    karten_fragment = [k for m in tco["modelle"] for k in _zeilen(m)]

    seite = BeautifulSoup(
        (site / "geraete.html").read_text(encoding="utf-8"),
        "html.parser",
        parse_only=SoupStrainer(id="gr-bnd-gruppe"),
    )
    an_seite = seite.select("details.gr-bnd > summary .gr-bnd-an")
    fragment = BeautifulSoup(
        (site / "data" / "geraete-buendel.html").read_text(encoding="utf-8"),
        "html.parser",
        parse_only=SoupStrainer("summary"),
    )
    an_fragment = fragment.select("summary .gr-bnd-an")

    assert len(an_seite) == len(karten_seite), "Seite: Zeilen und Karten zählen anders"
    assert len(an_fragment) == len(karten_fragment), (
        "Fragment: Zeilen und Karten zählen anders"
    )
    zugeordnet = list(
        zip(karten_seite + karten_fragment, an_seite + an_fragment, strict=True)
    )
    vertauscht = [
        (k["anbieter"], an.select_one(".gr-bnd-name").get_text(strip=True))
        for k, an in zugeordnet
        if an.select_one(".gr-bnd-name").get_text(strip=True) != k["anbieter"]
    ]
    assert not vertauscht, f"Zeile und Karte passen nicht zusammen: {vertauscht[:3]}"
    return [(k, _marken(an)) for k, an in zugeordnet]


def _beschreibung(karte: dict) -> str:
    return f"{karte['anbieter']} {karte['tarif']} {karte.get('raten_laufzeit')}"


def test_schaetzung_traegt_marke_an_der_zeile(paare):
    geschaetzt = [(k, m) for k, m in paare if k.get("schaetzung")]
    assert {k["anbieter"] for k, _ in geschaetzt} >= {"o2", "1&1"}, (
        "Bestand ohne Schätzungen von o2 und 1&1 – der Test prüft nichts"
    )
    ohne = [_beschreibung(k) for k, m in geschaetzt if SCHAETZUNG not in m]
    assert not ohne, (
        f"Schätzung: erwartet Marke an der Zeile – {len(ohne)} von "
        f"{len(geschaetzt)} Zeilen ohne Marke (z. B. {ohne[:3]})"
    )


def test_abgelaufene_aktion_traegt_marke_an_der_zeile(paare):
    veraltet = [(k, m) for k, m in paare if k.get("veraltet_aktion")]
    assert {k["anbieter"] for k, _ in veraltet} == {"congstar"}, (
        "Bestand ohne abgelaufene congstar-Aktion – der Test prüft nichts"
    )
    ohne = [_beschreibung(k) for k, m in veraltet if AKTION not in m]
    assert not ohne, (
        f"Aktion abgelaufen: erwartet Marke an der Zeile – {len(ohne)} von "
        f"{len(veraltet)} Zeilen ohne Marke (z. B. {ohne[:3]})"
    )


def test_gemessene_zeilen_tragen_keine_marke(paare):
    """Gegenprobe: eine Zeile, die zählt, trägt keine der beiden Marken, und keine
    Zeile trägt eine Marke, deren Zustand ihre Karte nicht hat."""
    gemessen = {k["anbieter"] for k, _ in paare if k.get("zaehlt", True)}
    assert "Vodafone" in gemessen, "Bestand ohne gemessene Vodafone-Zeile"
    falsch = [
        f"{_beschreibung(k)}: {m}"
        for k, m in paare
        if (SCHAETZUNG in m and not k.get("schaetzung"))
        or (AKTION in m and not k.get("veraltet_aktion"))
    ]
    assert not falsch, f"Zeile mit Marke ohne Grund: {len(falsch)} (z. B. {falsch[:3]})"
