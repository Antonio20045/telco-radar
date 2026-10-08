"""Jede Seite jedes Anbieters jeden Tag (Pitch 1, Schnitt 5).

Eine Produktseite ist überfällig, sobald sie einen Tag ohne ganze Lesung ist
(``LESEFRIST_TAGE``); nutzbar bleibt ihr Wert bis zur Frischegrenze, damit ein
ausgefallener Tag nichts leert. ``geraete-quellen.html`` nennt je Anbieter mit
Klick-Lauf „Crawler heute: N von M Seiten gelesen (TT.MM.JJJJ)“, N, M und Datum aus
der Ergebnisdatei. Gegenproben: eine an der Zeitgrenze abgeschnittene Seite zählt
nicht als gelesen, ohne Ergebnisdatei steht keine Zeile da. Feste Tage, kein heute.
"""

from __future__ import annotations

import json

from bestand_pfad import abbild

from telco_radar.collect.geraete.klickergebnis import (
    FRISCHEGRENZE_TAGE,
    LESEFRIST_TAGE,
    ORDNER,
)
from telco_radar.collect.geraete.klicktageslauf import ueberfaellig
from telco_radar.collect.geraete.klickziele import Seitenziel
from telco_radar.config import load_config
from telco_radar.report.html import render_site

TAG = "2026-10-08"
GESTERN = "2026-10-07"
A = "https://www.telekom.de/shop/geraet/a"
B = "https://www.telekom.de/shop/geraet/b"


def _seiten() -> tuple[Seitenziel, ...]:
    return (Seitenziel("a", 256, A), Seitenziel("b", 256, B))


def test_gestern_gelesen_ist_heute_ueberfaellig():
    gelesen = {A: GESTERN, B: GESTERN}
    assert ueberfaellig(_seiten(), gelesen, set(), TAG) == [A, B]
    assert ueberfaellig(_seiten(), gelesen, {A}, TAG) == [B]
    assert ueberfaellig(_seiten(), {A: TAG, B: TAG}, set(), TAG) == []


def test_lesefrist_ein_tag_frischegrenze_unveraendert():
    assert LESEFRIST_TAGE == 1
    assert FRISCHEGRENZE_TAGE == 3


def _seite(adresse: str, status: str) -> dict:
    return {"adresse": adresse, "status": status, "grund": None, "kombinationen": []}


def _datei(stati: list[str]) -> dict:
    return {
        "format": 1,
        "anbieter": "telekom",
        "name": "Telekom",
        "datum": TAG,
        "laufstatus": "gestoert",
        "grund": None,
        "seiten": [_seite(f"{A}{i}", s) for i, s in enumerate(stati)],
    }


def _quellenseite(tmp_path, stati: list[str] | None) -> str:
    root = tmp_path / "repo"
    berichte = abbild(root)
    if stati is not None:
        (root / ORDNER).mkdir(parents=True, exist_ok=True)
        text = json.dumps(_datei(stati), ensure_ascii=False)
        (root / ORDNER / "telekom.json").write_text(text, encoding="utf-8")
    site = tmp_path / "site"
    render_site(site, berichte, load_config(root))
    return (site / "geraete-quellen.html").read_text(encoding="utf-8")


def test_quellenseite_nennt_gelesene_seiten_aus_der_datei(tmp_path):
    stati = ["gelesen", "gelesen", "gestoert", "nicht_besucht"]
    html = _quellenseite(tmp_path, stati)
    assert "Crawler heute: 2 von 4 Seiten gelesen (08.10.2026)" in html


def test_gegenprobe_zeitgrenze_zaehlt_nicht(tmp_path):
    stati = ["gelesen", "zeitgrenze", "gestoert", "nicht_besucht", "nicht_besucht"]
    html = _quellenseite(tmp_path, stati)
    assert "Crawler heute: 1 von 5 Seiten gelesen (08.10.2026)" in html


def test_gegenprobe_ohne_klick_lauf_keine_zeile(tmp_path):
    assert "Crawler heute" not in _quellenseite(tmp_path, None)
