"""P2 (03.11.2026): Geräteseite ohne Erklär-Unterzeilen, ohne Fachwörter und
ohne Einblend-Animation im Abschnitt „teurer". Das Kopffoto (P3,
03.11.2026) ist wieder da - dieselbe Kopfband-Komponente wie auf den
Schwesterseiten."""

from __future__ import annotations

import json

import pytest
import test_geraete_zeitreihe_ansicht as za
from bs4 import BeautifulSoup

from telco_radar.report.html import render_site

HEUTE = za.HEUTE

FACHWOERTER = (
    "Product Advertising",
    "PA-API",
    "Scraping",
    "Konfigurationsschalter",
    "Bündel-TCO",
)


@pytest.fixture(scope="module")
def seite(tmp_path_factory):
    root, _state = za._baue(tmp_path_factory.mktemp("p2"))
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
    render_site(site, reports)
    html = (site / "geraete.html").read_text(encoding="utf-8")
    return BeautifulSoup(html, "html.parser")


def test_der_kopf_hat_dasselbe_kopfbild_wie_die_schwesterseiten(seite):
    kopf = seite.select_one(".gx-auftakt")
    assert kopf is not None
    assert kopf.select_one(".wa-bild") is not None
    assert kopf.select_one(".wa-schleier") is not None
    bild = kopf.select_one(".wa-bild img")
    assert bild is not None
    assert "band-geraete" in bild["src"]


def test_unter_der_ueberschrift_teurer_stehen_keine_zaehl_unterzeilen(seite):
    kopf = seite.select_one("#teuer .gx-kopf")
    assert kopf is not None
    text = kopf.get_text(" ", strip=True)
    assert "Geräte mit Tarif" not in text and "Einzelgeräte" not in text
    assert kopf.select_one(".gx-art") is None


def test_kein_verwaister_satz_zum_externen_tarifshop(seite):
    assert "externen Tarifshop" not in seite.get_text(" ")
    assert seite.select_one(".gr-ruhe") is None


def test_der_abschnitt_teurer_blendet_nichts_erst_beim_scrollen_ein(seite):
    assert seite.select_one("#teuer").get("data-puls") is None


def test_die_seite_nennt_keine_fachwoerter(seite):
    text = seite.get_text(" ")
    for wort in FACHWOERTER:
        assert wort not in text, wort


def test_die_leitzahl_nennt_den_vodafone_betrag_nur_im_hinweis(seite):
    labels = seite.select("span.gr-leit-label[title]")
    assert labels, "keine Leitzahl auf der Seite"
    for leit in labels:
        sichtbar = leit.get_text(" ", strip=True)
        assert "(" not in sichtbar, sichtbar
        assert sichtbar.endswith("günstiger als Vodafone"), sichtbar
        assert leit["title"].startswith("Vodafone: ")
