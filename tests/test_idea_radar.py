"""Tests für den Ideen-Radar (analyze/idea_radar.py) – offline/deterministisch."""
import json

from telco_radar.analyze.idea_radar import (
    seed_radar, refresh, load_or_seed, save)
from telco_radar.report.differentiation import DIFF_THEMES


def test_seed_has_all_levers():
    s = seed_radar()
    assert len(s) == len(DIFF_THEMES)
    for t in DIFF_THEMES:
        assert s[t["key"]]["vorbild"] and s[t["key"]]["idee"]
        assert s[t["key"]]["color"] == t["color"]


def test_idee_is_shortened():
    # Der Seed-Impuls ist lang; die Idee-Zeile muss knapp sein.
    s = seed_radar()
    assert all(len(v["idee"]) <= 140 for v in s.values())


def test_load_or_seed_without_file(tmp_path):
    r = load_or_seed(tmp_path / "nope.json")
    assert len(r) == len(DIFF_THEMES)


def test_refresh_without_llm_writes_seed(tmp_path):
    p = tmp_path / "idea_radar.json"
    data = refresh(p, "Telekom: irgendwas", model=None, use_llm=False)
    assert p.exists()
    assert data["ki"]["vorbild"]
    # persistiert und wieder ladbar
    back = load_or_seed(p)
    assert back["ki"]["idee"] == data["ki"]["idee"]


def test_load_or_seed_merges_saved_override(tmp_path):
    p = tmp_path / "idea_radar.json"
    save(p, {"ki": {"vorbild": "Testbetreiber X", "idee": "Test-Idee Y"}})
    merged = load_or_seed(p)
    assert merged["ki"]["vorbild"] == "Testbetreiber X"
    assert merged["ki"]["idee"] == "Test-Idee Y"
    # Farbe/Label kommen weiter aus der Definition
    assert merged["ki"]["color"]


def test_corrupt_file_falls_back(tmp_path):
    p = tmp_path / "idea_radar.json"
    p.write_text("{ not json", encoding="utf-8")
    r = load_or_seed(p)
    assert len(r) == len(DIFF_THEMES)
