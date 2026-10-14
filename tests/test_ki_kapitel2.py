"""Kapitel 2 der KI-Seite, „Was ist eigentlich KI?“ (Pitch 9).

``render_site`` schreibt ``ki-kapitel-2.html``; der zweite Knoten der
Schiene auf ``ki.html`` und „Weiter“ auf Kapitel 1 führen dorthin. Die Seite
hat die Machart von Kapitel 1 (dieselben Klassen, dieselbe Bewegung aus
``app.js``). Jede Zahl in den Sätzen kommt aus den Konstanten von
``ki_kapitel2`` und steht mit ihrer Quelle am Seitenende. Die Lehrbeispiele
sind so gewählt, dass die letzte Trennlinie alle zwölf richtig trennt und
jede frühere Linie an den neuen Beispielen scheitert; Gegenprobe: die Regel
„klick“ sortiert zwei der vier Mails falsch. Im Chromium: Pillen erscheinen
beim Scrollen, der Punkt läuft mit; bei reduzierter Bewegung und ohne
JavaScript steht alles da; kein Satz liegt auf einer Beschriftung.
"""

from __future__ import annotations

import re

import pytest
import test_ki_kapitel1 as k1
from test_ki_kapitel1 import DECKKRAFT, PUNKT_Y, SAETZE, UEBERLAPP
from test_ki_leiter_browser import site

from telco_radar.report import ki_kapitel, ki_kapitel2, ki_seite
from telco_radar.report import ki_kapitel2_bild as bild

__all__ = ["site"]

SEITE = "ki-kapitel-2.html"


def test_schiene_und_kapitel_1_fuehren_auf_kapitel_2(site):
    html = (site / "ki.html").read_text(encoding="utf-8")
    schiene = re.findall(
        r'<li class="ki-kapitel ki-kapitel--fertig"><a href="([^"]+)"', html
    )
    eins = (site / ki_kapitel.DATEI).read_text(encoding="utf-8")
    assert schiene[:2] == [ki_kapitel.DATEI, SEITE]
    assert schiene[:2] == [k["ziel"] for k in ki_seite.kapitel()[:2]]
    assert ki_kapitel2.DATEI == SEITE and (site / SEITE).is_file()
    assert f'<a href="{SEITE}">Kapitel 2 · {ki_seite.KAPITEL[1]}' in eins
    assert ki_seite.KAPITEL[1] == ki_kapitel2.TITEL


def test_zahlen_aus_den_konstanten_und_jede_quelle_verlinkt(site):
    html = (site / SEITE).read_text(encoding="utf-8")
    vorn = re.findall(r'<g class="ki-k1-station" data-station="([^"]+)"', html)
    texte = re.findall(r'class="ki-k1-ueber"[^>]*data-station="([^"]+)"', html)
    assert vorn == list(ki_kapitel2.STATIONEN)
    assert texte == sorted(texte, key=ki_kapitel2.STATIONEN.index)
    for zahl in (ki_kapitel2.KLICK_FANG, ki_kapitel2.GMAIL):
        assert f"{zahl} %" in html
    assert all(s in html for s in ki_kapitel2.SAMUEL)
    quellen = re.search(r'<p class="ki-k1-quellen">(.*?)</p>', html, re.S).group(1)
    links = re.findall(r'<a href="([^"]+)"', quellen)
    assert links == [u for _, u in ki_kapitel2.QUELLEN]
    assert all(u.startswith("https://") for u in links)
    assert ">Kapitel 2 · Was ist eigentlich KI?</h1>" in html
    assert "<i>KI<em>?</em></i>" in html and "?<em>.</em>" not in html
    assert "ki-k1-quellen" not in (site / ki_kapitel.DATEI).read_text("utf-8")


def test_regel_irrt_zweimal_und_die_letzte_linie_trennt_alle_beispiele():
    falsch = [w for w, _, _, spam in bild.MAILS if ("klick" in w.lower()) != spam]
    assert len(falsch) == 2 == len(bild.MAILS) // 2
    linien = [(a, b) for a, b, _ in bild.LINIEN]
    grenzen = [n for _, _, n in bild.LINIEN]
    assert grenzen == sorted(grenzen) and grenzen[-1] == len(bild.BEISPIELE)

    def fehler(linie, n):
        return [s for u, v, s in bild.BEISPIELE[:n] if bild.seite_von(linie, u, v) != s]

    for i, (linie, n) in enumerate(zip(linien, grenzen, strict=True)):
        assert fehler(linie, n) == []
        if i:
            assert fehler(linien[i - 1], n)
    assert bild.seite_von(linien[-1], *bild.NEU[1:])
    assert bild.NEU[0] in falsch


def test_die_fahrt_zeigt_pillen_erst_beim_scrollen(chromium, site):
    with k1._seite(chromium, site, name=SEITE) as page:
        page.wait_for_timeout(1200)
        start = page.evaluate(DECKKRAFT)
        y_start = page.evaluate(PUNKT_Y)
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
    assert len(deckkraft) > 30 and set(deckkraft) == {"1"}
    soll = [t for t in ki_kapitel2.TEXTE if t[1] == "satz"]
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
