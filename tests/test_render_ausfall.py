"""render_site nennt jeden Teil, den es nicht neu bauen konnte.

Vorher fing jede Stufe ihren Fehler, schrieb ein Log und lieferte einen
Notzustand - nach aussen sah der Lauf gruen aus. Jetzt kommt eine Liste
benannter Ausfaelle zurueck, die Seite nennt sie, `bauen` und `pipeline`
enden mit einem eigenen Exit-Code.
"""

from __future__ import annotations

import dataclasses
import json
import shutil
from pathlib import Path

import pytest
from test_geraete_zeitreihe_ansicht import HEUTE, _baue

from telco_radar import pipeline
from telco_radar.config import load_config
from telco_radar.report import bauen, geraete_zeitreihe
from telco_radar.report.ausfall import KONFIGURATION_TEIL, NEWSLETTER_TEIL, Ausfall
from telco_radar.report.geraete_view import ZEITREIHE_TEIL
from telco_radar.report.html import render_site

_ECHTE_CONFIG = Path(__file__).resolve().parent.parent / "config"
_MELDUNG = "Testfehler in der Zeitreihe"


def _render(tmp_path, mit_newsletter=True):
    root, _state = _baue(tmp_path)
    if mit_newsletter:
        shutil.copy(_ECHTE_CONFIG / "newsletter.yaml", root / "config")
    reports = root / "data" / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    (reports / f"{HEUTE}.json").write_text(
        json.dumps(
            {
                "date": HEUTE,
                "language": "de",
                "briefing_md": "## Auf einen Blick\n\n- Nichts.\n",
                "stats": {},
                "regions": [],
            }
        ),
        encoding="utf-8",
    )
    (reports / f"{HEUTE}.md").write_text("# B\n", encoding="utf-8")
    site = root / "site"
    ausfaelle = render_site(site, reports)
    return ausfaelle, site


def _wirft(*_a, **_k):
    raise ValueError(_MELDUNG)


def test_kaputte_zeitreihe_ist_ein_benannter_ausfall(tmp_path, monkeypatch):
    monkeypatch.setattr(geraete_zeitreihe, "aufbereiten", _wirft)
    ausfaelle, site = _render(tmp_path)
    assert ausfaelle == [Ausfall(teil=ZEITREIHE_TEIL, grund=f"ValueError: {_MELDUNG}")]
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
    assert gerufen == [
        (tmp_path.resolve() / "site", tmp_path.resolve() / "data" / "reports")
    ]
    return code, ausgabe.read_text(encoding="utf-8")


def test_bauen_meldet_ausfall_mit_exit_1_und_gerendert(tmp_path, monkeypatch, capsys):
    code, ausgabe = _bauen(
        tmp_path, monkeypatch, [Ausfall(ZEITREIHE_TEIL, "ValueError: x")]
    )
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


@pytest.mark.parametrize(
    "ergebnis, erwartet",
    [
        ([Ausfall(ZEITREIHE_TEIL, "ValueError: x")], 3),
        ([], 0),
    ],
)
def test_pipeline_main_endet_mit_3_bei_ausfall(
    tmp_path, monkeypatch, ergebnis, erwartet
):
    monkeypatch.setattr(
        pipeline, "run", lambda *_a, **_k: (tmp_path / "bericht.md", ergebnis)
    )
    assert pipeline.main(["--root", str(tmp_path)]) == erwartet


def test_pipeline_main_bleibt_bei_1_wenn_run_scheitert(tmp_path, monkeypatch):
    monkeypatch.setattr(pipeline, "run", _wirft)
    assert pipeline.main(["--root", str(tmp_path)]) == 1


def _teile(ausfaelle):
    return [a.teil for a in ausfaelle]


def test_fehlende_config_ist_ein_benannter_ausfall(tmp_path):
    reports = tmp_path / "data" / "reports"
    reports.mkdir(parents=True)
    site = tmp_path / "site"
    ausfaelle = render_site(site, reports)
    assert _teile(ausfaelle).count(KONFIGURATION_TEIL) == 1
    assert [a.grund for a in ausfaelle if a.teil == KONFIGURATION_TEIL] == [
        f"config/ fehlt unter {tmp_path}"
    ]
    seite = (site / "index.html").read_text(encoding="utf-8")
    assert "Nicht neu gebaut" in seite
    assert KONFIGURATION_TEIL in seite


def test_vorhandene_config_meldet_keinen_konfigurationsausfall(tmp_path):
    ausfaelle, _site = _render(tmp_path)
    assert KONFIGURATION_TEIL not in _teile(ausfaelle)


def test_fehlende_newsletter_yaml_ist_ein_benannter_ausfall(tmp_path):
    ausfaelle, _site = _render(tmp_path, mit_newsletter=False)
    assert not (tmp_path / "zeitreihe" / "config" / "newsletter.yaml").exists()
    teile = _teile(ausfaelle)
    assert teile.count(NEWSLETTER_TEIL) == 1
    assert KONFIGURATION_TEIL not in teile


def test_konfiguration_kommt_aus_der_wurzel_der_cfg(tmp_path):
    ausfaelle, _site = _render(tmp_path)
    root = tmp_path / "zeitreihe"
    anderswo = tmp_path / "anderswo" / "berichte"
    anderswo.mkdir(parents=True)
    site = tmp_path / "site2"
    cfg = dataclasses.replace(load_config(_ECHTE_CONFIG.parent), root=root)
    ausfaelle = render_site(site, anderswo, cfg)
    assert KONFIGURATION_TEIL not in _teile(ausfaelle)
    ohne_cfg = render_site(tmp_path / "site3", anderswo)
    assert KONFIGURATION_TEIL in _teile(ohne_cfg)
