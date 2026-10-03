"""Das Repo-Abbild aus dem Schnappschuss rendert die ganze Seite."""

from __future__ import annotations

import pytest
from bestand_pfad import AUTO_KATALOG, ZUSTAND, abbild, lese_wurzel

from telco_radar.report.html import render_site

pytestmark = pytest.mark.seite


def _seiten(site):
    return {p.name for p in site.glob("*.html")}


def test_das_abbild_rendert_newsletter_und_rechtstexte(tmp_path):
    render_site(tmp_path / "site", abbild(tmp_path))
    seiten = _seiten(tmp_path / "site")
    assert {"newsletter.html", "impressum.html", "datenschutz.html"} <= seiten
    assert {"index.html", "geraete.html", "wettbewerbsradar.html"} <= seiten


def test_das_abbild_ist_eine_kopie_des_schnappschusses(tmp_path):
    """Ein Render darf ins Abbild schreiben, der Schnappschuss bleibt unberührt."""
    berichte = abbild(tmp_path)
    datei = berichte.parent / "state" / "geraete_tco.json"
    assert datei.read_bytes() == (ZUSTAND / "geraete_tco.json").read_bytes()
    assert not datei.is_symlink()
    datei.write_text("{}", encoding="utf-8")
    assert (ZUSTAND / "geraete_tco.json").read_text(encoding="utf-8") != "{}"


def test_die_lese_wurzel_liest_den_auto_katalog_des_schnappschusses():
    datei = lese_wurzel() / "data" / "state" / AUTO_KATALOG
    assert not datei.is_symlink()
    assert datei.read_bytes() == (ZUSTAND / AUTO_KATALOG).read_bytes()
