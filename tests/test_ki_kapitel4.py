"""Kapitel 4 der KI-Seite, „Warum sie würfelt“ (Pitch 9).

``render_site`` schreibt ``ki-kapitel-4.html``; „Weiter“ auf Kapitel 3 führt
dorthin. Jede Prozentzahl rechnet ``verteilung()`` aus den Kandidaten von
Kapitel 1; Gegenprobe von Hand: bei T = 0,5 ist „Ja“ 0,62² / (0,62² + 0,17²
+ 0,11² + 0,06² + 0,04²) = 89 %, bei T = 2 √0,62 / Σ√p = 40 %. Kälter heißt
immer mehr „Ja“. Die fünf Versuche kommen aus ``ziehungen()``. Im Chromium wie
die anderen Kapitel: Fahrt, ruhige Gegenprobe, keine Überlappung.
"""

from __future__ import annotations

import html as h
import re

import pytest
import test_ki_kapitel1 as k1
from test_ki_kapitel1 import DECKKRAFT, PUNKT_Y, SAETZE, UEBERLAPP
from test_ki_leiter_browser import site

from telco_radar.report import ki_kapitel3, ki_kapitel4, ki_seite
from telco_radar.report import ki_kapitel4_bild as bild
from telco_radar.report import ki_kapitel_bild as k1bild

__all__ = ["site"]

SEITE = "ki-kapitel-4.html"


def test_kapitel_3_fuehrt_weiter_und_die_schiene_kennt_kapitel_4(site):
    drei = (site / ki_kapitel3.DATEI).read_text(encoding="utf-8")
    assert f'<a href="{SEITE}">Kapitel 4 · {ki_seite.KAPITEL[3]}' in drei
    assert ki_seite.kapitel()[3]["ziel"] == SEITE == ki_kapitel4.DATEI
    assert ki_seite.KAPITEL[3] == ki_kapitel4.TITEL
    assert (site / SEITE).is_file()


def test_verteilung_gegen_die_handrechnung():
    eins = [p for _, p in bild.verteilung(1.0)]
    assert eins == pytest.approx([p for _, p, _ in k1bild.KANDIDATEN])
    assert bild.prozent(bild.verteilung(0.5)[0][1]) == "89 %"
    assert bild.prozent(bild.verteilung(2.0)[0][1]) == "40 %"
    ja = [bild.verteilung(t)[0][1] for t, _ in bild.TEMPERATUREN]
    assert ja == sorted(ja)
    assert bild.ziehungen() == ["Ja", "Ja", "Das", "Ja", "Grundsätzlich"]


def test_prozente_und_quellen_auf_der_seite(site):
    seite = h.unescape((site / SEITE).read_text(encoding="utf-8"))
    werte = re.findall(r'class="ki-k1-wert[^"]*"[^>]*>(\d+ %)<', seite)
    soll = [bild.prozent(p) for p in (q for _, q in bild.verteilung(1.0))]
    for t, _ in bild.TEMPERATUREN:
        soll += [bild.prozent(p) for _, p in bild.verteilung(t)]
    assert werte == soll
    assert "Bei Temperatur 0,5 gewinnt „Ja“ 89 %, bei 2 nur noch 40 %." in seite
    gezogen = re.findall(r">([^<>]+) …</text>", seite)
    assert gezogen == bild.ziehungen()
    quellen = re.search(r'<p class="ki-k1-quellen">(.*?)</p>', seite, re.S).group(1)
    assert re.findall(r'<a href="([^"]+)"', quellen) == [
        u for _, u in ki_kapitel4.QUELLEN
    ]


def test_die_fahrt_zeigt_pillen_erst_beim_scrollen(chromium, site):
    with k1._seite(chromium, site, name=SEITE) as page:
        page.wait_for_timeout(1200)
        start, y_start = page.evaluate(DECKKRAFT), page.evaluate(PUNKT_Y)
        k1._nach(page, 0.5)
        mitte, y_mitte = page.evaluate(DECKKRAFT), page.evaluate(PUNKT_Y)
        k1._nach(page, 1)
        ende, y_ende = page.evaluate(DECKKRAFT), page.evaluate(PUNKT_Y)
        saetze = page.evaluate(SAETZE)
    assert start[-1] == "0" and start.count("1") < len(start) / 2
    assert start.count("1") < mitte.count("1") <= len(mitte)
    assert y_start < y_mitte < y_ende
    assert set(ende) == {"1"} and set(saetze) == {"1"}


@pytest.mark.parametrize(
    "optionen", [{"reduced_motion": "reduce"}, {"java_script_enabled": False}]
)
def test_gegenprobe_ruhig_und_ohne_js_steht_alles_da(chromium, site, optionen):
    with k1._seite(chromium, site, name=SEITE, **optionen) as page:
        deckkraft = page.evaluate(DECKKRAFT)
        saetze = page.evaluate(SAETZE)
    assert len(deckkraft) > 8 and set(deckkraft) == {"1"}
    soll = [t for t in ki_kapitel4.TEXTE if t[1] == "satz"]
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
