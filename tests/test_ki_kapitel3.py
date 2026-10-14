"""Kapitel 3 der KI-Seite, „Wie eine KI lernt“ (Pitch 9).

``render_site`` schreibt ``ki-kapitel-3.html``; „Weiter“ auf Kapitel 2 führt
dorthin. Machart und Bewegung wie Kapitel 1. Die Rundenzahlen, Textproben
und Chip-Stunden kommen aus den Konstanten, die Jahre auf einem Chip aus
``chip_jahre()`` (Gegenprobe von Hand: 30,84 Mio. Stunden / 8760 = 3520,5).
Im Chromium: Pillen erscheinen beim Scrollen, der Punkt läuft mit; ruhig und
ohne JavaScript steht alles da; kein Satz liegt auf einer Beschriftung,
keine Ansagezeile bricht um.
"""

from __future__ import annotations

import html as h
import re

import pytest
import test_ki_kapitel1 as k1
from test_ki_kapitel1 import DECKKRAFT, PUNKT_Y, SAETZE, UEBERLAPP
from test_ki_leiter_browser import site

from telco_radar.report import ki_kapitel2, ki_kapitel3, ki_seite
from telco_radar.report import ki_kapitel3_bild as bild

__all__ = ["site"]

SEITE = "ki-kapitel-3.html"


def test_kapitel_2_fuehrt_weiter_und_die_schiene_kennt_kapitel_3(site):
    zwei = (site / ki_kapitel2.DATEI).read_text(encoding="utf-8")
    assert f'<a href="{SEITE}">Kapitel 3 · {ki_seite.KAPITEL[2]}' in zwei
    assert ki_seite.kapitel()[2]["ziel"] == SEITE == ki_kapitel3.DATEI
    assert (site / SEITE).is_file()
    assert ki_seite.KAPITEL[2] == ki_kapitel3.TITEL


def test_zahlen_proben_und_quellen_aus_den_konstanten(site):
    seite = h.unescape((site / SEITE).read_text(encoding="utf-8"))
    assert ki_kapitel3.chip_jahre() == 3520
    assert "30,84 Mio. Chip-Stunden" in seite and "über 3.520 Jahre" in seite
    assert "Llama 3.1 " in seite
    assert "nach 100, 300, 700 und 2000 Runden" in seite
    runden = re.findall(r">Runde (\d+)<", seite)
    assert [int(r) for r in runden] == [r for r, _ in bild.PROBEN]
    assert runden == sorted(runden, key=int)
    for _, probe in bild.PROBEN:
        assert f">{probe}<" in seite
    quellen = re.search(r'<p class="ki-k1-quellen">(.*?)</p>', seite, re.S).group(1)
    assert re.findall(r'<a href="([^"]+)"', quellen) == [
        u for _, u in ki_kapitel3.QUELLEN
    ]
    vorn = re.findall(r'<g class="ki-k1-station" data-station="([^"]+)"', seite)
    assert vorn == list(ki_kapitel3.STATIONEN)


def test_die_fahrt_zeigt_pillen_erst_beim_scrollen(chromium, site):
    with k1._seite(chromium, site, name=SEITE) as page:
        page.wait_for_timeout(1200)
        start, y_start = page.evaluate(DECKKRAFT), page.evaluate(PUNKT_Y)
        k1._nach(page, 0.5)
        mitte, y_mitte = page.evaluate(DECKKRAFT), page.evaluate(PUNKT_Y)
        k1._nach(page, 1)
        ende, y_ende = page.evaluate(DECKKRAFT), page.evaluate(PUNKT_Y)
        saetze = page.evaluate(SAETZE)
    assert start[-1] == "0" and start.count("1") < len(start) / 4
    assert start.count("1") < mitte.count("1") < len(mitte)
    assert y_start < y_mitte < y_ende
    assert set(ende) == {"1"} and set(saetze) == {"1"}


@pytest.mark.parametrize(
    "optionen", [{"reduced_motion": "reduce"}, {"java_script_enabled": False}]
)
def test_gegenprobe_ruhig_und_ohne_js_steht_alles_da(chromium, site, optionen):
    with k1._seite(chromium, site, name=SEITE, **optionen) as page:
        deckkraft = page.evaluate(DECKKRAFT)
        saetze = page.evaluate(SAETZE)
    assert len(deckkraft) > 20 and set(deckkraft) == {"1"}
    soll = [t for t in ki_kapitel3.TEXTE if t[1] == "satz"]
    assert len(saetze) == len(soll) and set(saetze) == {"1"}


@pytest.mark.parametrize("breite", [390, 1440])
def test_kein_satz_liegt_auf_einer_beschriftung(chromium, site, breite):
    with k1._seite(
        chromium, site, name=SEITE, breite=breite, reduced_motion="reduce"
    ) as page:
        treffer = page.evaluate(UEBERLAPP)
        breiten = page.evaluate("[document.documentElement.scrollWidth, innerWidth]")
        zeilen = page.evaluate(
            "[...document.querySelectorAll('.ki-k1-ansage i')].map(e =>"
            " e.getBoundingClientRect().height"
            " < parseFloat(getComputedStyle(e).fontSize) * 1.5)"
        )
    assert treffer == []
    assert breiten[0] <= breiten[1]
    assert len(zeilen) == 9 and set(zeilen) == {True}
