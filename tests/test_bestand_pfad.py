"""Das Repo-Abbild aus dem Schnappschuss rendert die ganze Seite."""

from __future__ import annotations

import re

import pytest
from bestand_pfad import (
    ARCHIV,
    AUTO_KATALOG,
    BILDER_BESTAND,
    BILDER_ZUSTAND,
    ZUSTAND,
    abbild,
    lese_wurzel,
)

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


_BILD = re.compile(r'"([0-9a-f]{16}-\d+\.jpg)"')


def _verweise(datei):
    return set(_BILD.findall(datei.read_text(encoding="utf-8")))


def _namen(ordner):
    return {p.name for p in ordner.iterdir()}


def test_jedes_promo_motiv_des_bestands_liegt_als_bild_vor():
    verweise = _verweise(ZUSTAND / "promo_db.json")
    assert len(verweise) == 70
    assert verweise == _namen(BILDER_ZUSTAND / "promo_images")


def test_jedes_meldungsbild_der_ausgabe_mit_bildern_liegt_vor():
    verweise = _verweise(BILDER_BESTAND / "reports" / "2026-08-08.json")
    assert len(verweise) == 52
    assert verweise == _namen(BILDER_BESTAND / "state" / "report_images")


def test_das_archiv_haelt_jede_ausgabe_ab_dem_sechsten_august():
    tage = sorted(p.stem for p in ARCHIV.glob("2026-*.json"))
    assert (tage[0], tage[-1], len(tage)) == ("2026-08-06", "2026-10-02", 21)
    assert (ARCHIV / "2026-10-02.json").read_bytes() == (
        ZUSTAND.parent / "reports" / "2026-10-02.json"
    ).read_bytes()
