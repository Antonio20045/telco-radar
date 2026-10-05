"""Zusatzstufen und Nachlauf: ein Ausfall je Stufe hält den Lauf nicht an."""

from __future__ import annotations

import json
from datetime import date
from types import SimpleNamespace

import pytest

from telco_radar import (
    geraete_pipeline,
    promo_pipeline,
    veroeffentlichen,
    versand,
    zusatzstufen,
)
from telco_radar.analyze import category_sweep, llm
from telco_radar.analyze.takt import Takt
from telco_radar.report import diff_bilder

HEUTE = date(2026, 10, 5)


def _takt(gefangen: list[str]) -> Takt:
    def abgesichert(aufgabe, bei_fehler):
        try:
            return aufgabe()
        except RuntimeError as exc:
            gefangen.append(str(exc))
            return bei_fehler(exc)

    return Takt(lambda: 10.0, lambda *p: None, abgesichert)


def _wirft(name: str):
    def _stufe(*args, **kwargs):
        raise RuntimeError(name)

    return _stufe


def test_jede_zusatzstufe_faellt_einzeln_aus(tmp_path, monkeypatch):
    monkeypatch.setattr(category_sweep, "run_sweep", _wirft("sweep"))
    monkeypatch.setattr(promo_pipeline, "run_promo_stage", _wirft("promo"))
    monkeypatch.setattr(geraete_pipeline, "run_geraete_stage", _wirft("geraete"))
    monkeypatch.setattr(diff_bilder, "beschaffe", _wirft("diff-bilder"))
    gefangen: list[str] = []
    cfg = SimpleNamespace(settings={"promo_enabled": True})

    zusatz = zusatzstufen.ausfuehren(
        cfg,
        tmp_path,
        HEUTE,
        ("e", "m", "Deutsch"),
        False,
        lambda: 60.0,
        _takt(gefangen),
    )

    assert gefangen == ["sweep", "promo", "geraete", "diff-bilder"]
    assert (zusatz.promo, zusatz.geraete) == ({}, {})
    bericht = tmp_path / "data" / "reports" / "differenzierung" / "2026-10-05.md"
    assert bericht.is_file()


def test_geraete_ohne_restzeit_laufen_nicht(tmp_path, monkeypatch):
    monkeypatch.setattr(category_sweep, "run_sweep", lambda *a: None)
    monkeypatch.setattr(geraete_pipeline, "run_geraete_stage", _wirft("geraete"))
    monkeypatch.setattr(diff_bilder, "beschaffe", lambda *a: {})
    gefangen: list[str] = []
    cfg = SimpleNamespace(settings={"promo_enabled": False, "geraete_enabled": True})

    zusatz = zusatzstufen.ausfuehren(
        cfg,
        tmp_path,
        HEUTE,
        ("e", "m", "Deutsch"),
        False,
        lambda: None,
        _takt(gefangen),
    )

    assert gefangen == []
    assert zusatz.geraete == {}


def test_geraete_bekommen_die_restzeit_als_frist(tmp_path, monkeypatch):
    monkeypatch.setattr(category_sweep, "run_sweep", lambda *a: None)
    monkeypatch.setattr(diff_bilder, "beschaffe", lambda *a: {})
    fristen: list[float] = []

    def _geraete(root, http, heute, frist_sekunden):
        fristen.append(frist_sekunden)
        return {"neu": 2}

    monkeypatch.setattr(geraete_pipeline, "run_geraete_stage", _geraete)
    cfg = SimpleNamespace(settings={"promo_enabled": False})

    zusatz = zusatzstufen.ausfuehren(
        cfg, tmp_path, HEUTE, ("e", "m", "Deutsch"), False, lambda: 75.0, _takt([])
    )

    assert fristen == [75.0]
    assert zusatz.geraete == {"neu": 2}


@pytest.fixture
def _bericht(tmp_path) -> veroeffentlichen.Bericht:
    pfad = tmp_path / "bericht.json"
    return veroeffentlichen.Bericht(tmp_path / "bericht.md", pfad, {"run": {}})


def test_versandausfall_behaelt_seite_und_kosten(tmp_path, monkeypatch, _bericht):
    ausfall = object()
    monkeypatch.setattr(veroeffentlichen, "render_site", lambda *a: [ausfall])
    monkeypatch.setattr(versand, "versende", _wirft("versand"))
    monkeypatch.setattr(llm, "llm_available", lambda: False)
    gefangen: list[str] = []
    cfg = SimpleNamespace(settings={"uebersetzung_enabled": False})

    ausfaelle = veroeffentlichen.nachlauf(
        _bericht, ([], {}), cfg, tmp_path, ("m", HEUTE, 0.0), _takt(gefangen)
    )

    assert ausfaelle == [ausfall]
    assert gefangen == ["versand"]
    geschrieben = json.loads(_bericht.json_path.read_text(encoding="utf-8"))
    assert "kosten" in geschrieben["run"]
    assert "versand" not in geschrieben["run"]
