"""render_site nennt jeden Teil, den es nicht neu bauen konnte.

Vorher fing jede Stufe ihren Fehler, schrieb ein Log und lieferte einen
Notzustand - nach aussen sah der Lauf gruen aus. Jetzt kommt eine Liste
benannter Ausfaelle zurueck, die Seite nennt sie, `bauen` und `pipeline`
enden mit einem eigenen Exit-Code.
"""
from __future__ import annotations

import json

import pytest

from telco_radar import pipeline
from telco_radar.report import bauen, geraete_zeitreihe
from telco_radar.report.ausfall import Ausfall
from telco_radar.report.geraete_view import ZEITREIHE_TEIL
from telco_radar.report.html import render_site

from test_geraete_zeitreihe_ansicht import HEUTE, _baue

_MELDUNG = "Testfehler in der Zeitreihe"


def _render(tmp_path):
    root, _state = _baue(tmp_path)
    reports = root / "data" / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    (reports / f"{HEUTE}.json").write_text(json.dumps({
        "date": HEUTE, "language": "de",
        "briefing_md": "## Auf einen Blick\n\n- Nichts.\n",
        "stats": {}, "regions": []}), encoding="utf-8")
    (reports / f"{HEUTE}.md").write_text("# B\n", encoding="utf-8")
    site = root / "site"
    ausfaelle = render_site(site, reports)
    return ausfaelle, site


def _wirft(*_a, **_k):
    raise ValueError(_MELDUNG)


def test_kaputte_zeitreihe_ist_ein_benannter_ausfall(tmp_path, monkeypatch):
    monkeypatch.setattr(geraete_zeitreihe, "aufbereiten", _wirft)
    ausfaelle, site = _render(tmp_path)
    assert ausfaelle == [Ausfall(teil=ZEITREIHE_TEIL,
                                 grund=f"ValueError: {_MELDUNG}")]
    geraete = (site / "geraete.html").read_text(encoding="utf-8")
    assert "Nicht neu gebaut" in geraete
    assert ZEITREIHE_TEIL in geraete
    assert _MELDUNG in geraete


def test_ohne_fehler_keine_ausfaelle_und_kein_hinweis(tmp_path, monkeypatch):
    echt = geraete_zeitreihe.aufbereiten
    gerufen = []

    def _zaehlt(*a, **k):
        gerufen.append(1)
        return echt(*a, **k)

    monkeypatch.setattr(geraete_zeitreihe, "aufbereiten", _zaehlt)
    ausfaelle, site = _render(tmp_path)
    assert gerufen == [1]
    assert ausfaelle == []
    geraete = (site / "geraete.html").read_text(encoding="utf-8")
    assert "Nicht neu gebaut" not in geraete


def _bauen(tmp_path, monkeypatch, ergebnis):
    ausgabe = tmp_path / "github_output"
    ausgabe.write_text("", encoding="utf-8")
    monkeypatch.setenv("GITHUB_OUTPUT", str(ausgabe))
    gerufen = []

    def _render_site(site_dir, reports_dir, cfg):
        gerufen.append((site_dir, reports_dir))
        return ergebnis

    monkeypatch.setattr(bauen, "render_site", _render_site)
    monkeypatch.setattr(bauen, "load_config", lambda root: None)
    code = bauen.main(["--root", str(tmp_path)])
    assert gerufen == [(tmp_path.resolve() / "site",
                        tmp_path.resolve() / "data" / "reports")]
    return code, ausgabe.read_text(encoding="utf-8")


def test_bauen_meldet_ausfall_mit_exit_1_und_gerendert(tmp_path, monkeypatch,
                                                      capsys):
    code, ausgabe = _bauen(tmp_path, monkeypatch,
                           [Ausfall(ZEITREIHE_TEIL, "ValueError: x")])
    assert code == 1
    assert ausgabe.splitlines() == ["gerendert=true"]
    assert f"AUSFALL {ZEITREIHE_TEIL}: ValueError: x" in capsys.readouterr().err


def test_bauen_ohne_ausfall_endet_mit_0(tmp_path, monkeypatch, capsys):
    code, ausgabe = _bauen(tmp_path, monkeypatch, [])
    assert code == 0
    assert ausgabe.splitlines() == ["gerendert=true"]
    assert "AUSFALL" not in capsys.readouterr().err


def test_bauen_ohne_gerendert_wenn_render_site_wirft(tmp_path, monkeypatch):
    ausgabe = tmp_path / "github_output"
    ausgabe.write_text("", encoding="utf-8")
    monkeypatch.setenv("GITHUB_OUTPUT", str(ausgabe))
    monkeypatch.setattr(bauen, "render_site", _wirft)
    monkeypatch.setattr(bauen, "load_config", lambda root: None)
    with pytest.raises(ValueError):
        bauen.main(["--root", str(tmp_path)])
    assert ausgabe.read_text(encoding="utf-8") == ""


@pytest.mark.parametrize("ergebnis, erwartet", [
    ([Ausfall(ZEITREIHE_TEIL, "ValueError: x")], 3),
    ([], 0),
])
def test_pipeline_main_endet_mit_3_bei_ausfall(tmp_path, monkeypatch,
                                               ergebnis, erwartet):
    monkeypatch.setattr(pipeline, "run",
                        lambda *_a, **_k: (tmp_path / "bericht.md", ergebnis))
    assert pipeline.main(["--root", str(tmp_path)]) == erwartet


def test_pipeline_main_bleibt_bei_1_wenn_run_scheitert(tmp_path, monkeypatch):
    monkeypatch.setattr(pipeline, "run", _wirft)
    assert pipeline.main(["--root", str(tmp_path)]) == 1
