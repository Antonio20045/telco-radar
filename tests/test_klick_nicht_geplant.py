"""Klick-Dateien eines Anbieters, der nicht mehr im Tagesplan steht, zählen nicht.

o2 steht seit 21.11.2026 nicht mehr in ``config/klick_tageslauf.yaml``; in
``data/state/klick/`` bleiben aber ``o2*.json`` vom 21.11. liegen, darunter
``o2-tarife-2.json`` mit ``laufstatus`` „gestoert“. Ohne Plan-Abgleich hieße es auf der
Seite bis zur Frischegrenze „o2 nicht erfasst: Lesen gestört (21.11.2026)“, obwohl der
Adapter o2 vollständig liest, und ihre Sätze ersetzten Adaptersätze.
"""

from __future__ import annotations

import json
from pathlib import Path

from bestand_pfad import lese_wurzel

from telco_radar.analyze.klick_zusammenfuehrung import zusammenfuehren
from telco_radar.geraete_config import lade_katalog

WURZEL = Path(__file__).resolve().parents[1]
TAG = "2026-11-21"


def _datei(ordner: Path, schluessel: str, name: str) -> None:
    kopf = {
        "anbieter": schluessel,
        "name": name,
        "datum": TAG,
        "format": 1,
        "laufstatus": "gestoert",
        "grund": "https://example.invalid/x: Abruf gestört (HTTP 503)",
        "seiten": [],
    }
    (ordner / f"{schluessel}.json").write_text(json.dumps(kopf), encoding="utf-8")


def _zug(tmp_path: Path):
    ordner = tmp_path / "klick"
    ordner.mkdir()
    _datei(ordner, "o2-tarife-2", "o2")
    _datei(ordner, "telekom", "Telekom")
    katalog = lade_katalog(lese_wurzel())
    return zusammenfuehren([], ordner, WURZEL, katalog, TAG, lambda s: ("", None))


def test_datei_ohne_plan_ist_kein_erfassungsgrund(tmp_path):
    zug = _zug(tmp_path)
    assert "o2" not in zug.erfassung
    assert [d["anbieter"] for d in zug.bilanz["dateien"]] == ["Telekom"]


def test_gegenprobe_geplanter_anbieter_behaelt_seinen_grund(tmp_path):
    zug = _zug(tmp_path)
    assert zug.erfassung["Telekom"].startswith("Telekom nicht erfasst")
