"""Goldener Lauf: ``pipeline.run`` ganz aus der Aufnahme, Seiten byte-gleich.

Die Aufnahme unter ``tests/fixtures/golden/<tag>/`` stammt aus
``scripts/golden_aufnehmen.py`` (``make golden-aufnehmen``, nur Antonio). Fehlt
eine Antwort, weil ein Prompt oder eine Quelle sich geändert hat, scheitert der
Lauf mit „… fehlt, neu aufnehmen mit make golden-aufnehmen“. Hat das LLM bei der
Aufnahme jede Anfrage abgelehnt (``llm`` in ``_herkunft.json``), ist der Weg ohne
LLM golden: ungelesene Meldungen kommen im zweiten Lauf wieder, sonst nichts.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from telco_radar import golden
from telco_radar.analyze import editor
from telco_radar.dedupe import SeenStore

pytestmark = pytest.mark.golden

WURZEL = Path(__file__).resolve().parents[2]
AUFNAHME = max(
    p for p in (WURZEL / "tests" / "fixtures" / "golden").iterdir() if p.is_dir()
)
STOERUNG = "Störung des Analyse-Dienstes"


def _wurzel(tmp_path: Path) -> Path:
    bestand = WURZEL / golden.herkunft(AUFNAHME)["bestand"]
    return golden.wurzel_bauen(tmp_path / "wurzel", AUFNAHME, bestand)


def _bericht(wurzel: Path) -> dict:
    tag = golden.herkunft(AUFNAHME)["zeit"][:10]
    pfad = wurzel / "data" / "reports" / f"{tag}.json"
    return json.loads(pfad.read_text(encoding="utf-8"))


def _gesehen(wurzel: Path) -> int:
    return len(SeenStore(wurzel / "data" / "state" / "seen.jsonl"))


def _index(wurzel: Path) -> str:
    return (wurzel / "site" / "index.html").read_text(encoding="utf-8")


def test_seiten_wie_aufgenommen_und_zweiter_lauf_ohne_neues(tmp_path):
    wurzel = _wurzel(tmp_path)
    vorher = _gesehen(wurzel)

    band = golden.lauf(AUFNAHME, wurzel)

    assert not band.fehlend, "\n".join(band.fehlend[:10])
    erwartet = json.loads((AUFNAHME / "erwartet.json").read_text(encoding="utf-8"))
    seiten = golden.seiten(wurzel)
    abweichend = sorted(
        p for p in erwartet.keys() | seiten.keys() if erwartet.get(p) != seiten.get(p)
    )
    assert not abweichend, f"Seiten weichen von der Aufnahme ab: {abweichend[:20]}"
    neu = _bericht(wurzel)["stats"]["new"]
    ungelesen = neu - (_gesehen(wurzel) - vorher)
    assert neu > 0
    assert (ungelesen == 0) == (golden.herkunft(AUFNAHME)["llm"] == "beantwortet")

    band = golden.lauf(AUFNAHME, wurzel)

    assert not band.fehlend, "\n".join(band.fehlend[:10])
    assert _bericht(wurzel)["stats"]["new"] == ungelesen


def test_geaenderter_prompt_nennt_die_fehlende_stufe(tmp_path, monkeypatch):
    for name in ("EDITOR_SYSTEM", "BEREICH_SYSTEM", "CHEF_SYSTEM"):
        monkeypatch.setattr(editor, name, getattr(editor, name) + "\nGeändert.")

    band = golden.lauf(AUFNAHME, _wurzel(tmp_path))

    assert (
        "LLM-Antwort für Stufe editor fehlt, neu aufnehmen mit make golden-aufnehmen"
        in band.fehlend
    )


def test_leeres_guthaben_rendert_den_ausfall(tmp_path):
    wurzel = _wurzel(tmp_path)

    band = golden.lauf(AUFNAHME, wurzel, guthaben_leer=True)

    assert not band.fehlend, "\n".join(band.fehlend[:10])
    bericht = _bericht(wurzel)
    assert bericht["run"]["editor_used"] is False
    assert bericht["run"]["models"]["unavailable"]
    assert STOERUNG in _index(wurzel)
