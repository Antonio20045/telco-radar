"""congstar führt das iPhone Duo nicht: Beleg ist die Kategorie, keine Soft-404-Seite.

Bis 09.11.2026 stützte die belegte Lücke sich auf die geratene Einzelseite
`/geraete/apple/apple-iphone-duo/` (HTTP 200 mit Error-404-Inhalt). Am 10.11.2026
ist die Lücke am Original neu belegt (`docs/belege/congstar-duo-1011/`): die
Kategorie „iPhones mit Vertrag“ (über Menü-Links erreicht) hat 28 Einträge ohne
„Duo“. Seite (Portfolio-Vergleich) und Beleg-Link lesen dieselbe Config. Gegenprobe:
nach `bis` ist die Ausnahme keine Lücke mehr; das 17 Pro bleibt eigene Lücke.
Feste Bezugstage, kein heutiges Datum.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import test_geraete_portfolio as tp

from telco_radar.analyze.buendel_abdeckung import lade_pflicht
from telco_radar.geraete_model import Katalog
from telco_radar.report import geraete_portfolio as pf
from telco_radar.report.geraete_sortiment import GRUND_ABGELAUFEN, beleg_fuer

WURZEL = Path(__file__).resolve().parents[1]
HEUTE = "2026-11-10"
SCHLUESSEL = ("congstar", "apple-iphone-duo")
DUO = tp._g("Apple", "iPhone Duo", 18)
KATEGORIE = "https://www.congstar.de/geraete/apple/"
SOFT_404 = "https://www.congstar.de/geraete/apple/apple-iphone-duo/"


@pytest.fixture(scope="module")
def belege():
    return lade_pflicht(WURZEL / "config" / "geraete_abdeckung.yaml")["belege"]


def test_beleg_ist_die_kategorie_und_das_bild_liegt_im_repo(belege):
    b = belege[SCHLUESSEL]
    assert b["original"] == KATEGORIE
    assert b["original"] != SOFT_404 and "Soft-404" not in b["grund"]
    assert b["geprueft"].isoformat() == HEUTE
    assert "/docs/belege/congstar-duo-1011/" in b["beleg"]
    assert (
        WURZEL / "docs/belege/congstar-duo-1011" / b["beleg"].rsplit("/", 1)[1]
    ).is_file()


def test_geraeteseite_verweist_im_portfolio_auf_den_kategorie_screenshot(belege):
    modelle = [
        tp._modell(DUO, tp._karte("Vodafone")),
        tp._modell(tp.I17AIR, tp._karte("Vodafone"), tp._karte("congstar")),
    ]
    katalog = Katalog(geraete=[DUO, tp.I17AIR])
    a = pf.berechne(modelle, katalog, belege, HEUTE)
    p = tp._paar(a, "congstar")
    assert (p["n_v"], p["n_offen"]) == (1, 0)
    text = p["nur_v"][0]["geraete"][0]["beleg"]
    assert text["original"] == KATEGORIE
    assert "congstar-duo-1011" in text["url"] and text["url"].endswith(".png")
    s = tp._rendern({**a, "hinweis": ""})
    links = [x["href"] for x in s.select(".gr-pf-zahl small a")]
    assert links == [text["url"], KATEGORIE]
    assert SOFT_404 not in str(s)


def test_gegenprobe_nach_bis_keine_belegte_luecke_und_17_pro_bleibt(belege):
    gueltig, _ = beleg_fuer(belege, "congstar", "apple-iphone-duo", "2026-11-24")
    assert gueltig is not None
    abgelaufen, grund = beleg_fuer(belege, "congstar", "apple-iphone-duo", "2026-11-25")
    assert abgelaufen is None and grund.startswith(GRUND_ABGELAUFEN)
    assert belege[("congstar", "apple-iphone-17-pro")]["original"] != KATEGORIE
