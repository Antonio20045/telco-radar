"""Kapitel 1 der KI-Seite, „Wie eine KI antwortet“ (Pitch 9, Schnitte 10–12).

``render_site`` schreibt ``ki-kapitel-1.html``; Knopf und erster Knoten der
Schiene auf ``ki.html`` führen dorthin. Die Seite ist eine lange
Linienzeichnung mit den Stationen aus ``ki_kapitel.STATIONEN``; jede Zahl
(Token-Nummern, Anteile) kommt aus den Konstanten von ``ki_kapitel_bild``.
Im Chromium wird die Fahrt am computed style gemessen: Pillen weiter unten
sind beim Start unsichtbar, beim Scrollen erscheinen sie, der Punkt läuft die
Route ab, Zähler enden bei ihrer Nummer. Gegenproben: bei reduzierter
Bewegung und ohne JavaScript steht alles fertig da. Auf 390 px läuft die
Seite nicht über, nichts klebt und kein Satz liegt auf einer Beschriftung.
Der Aufbau der Site kommt aus ``test_ki_leiter_browser`` (fester Tag).
"""

from __future__ import annotations

import contextlib
import functools
import http.server
import re
import threading
from pathlib import Path

import pytest
from test_ki_leiter_browser import site

from telco_radar.report import ki_kapitel, ki_seite
from telco_radar.report import ki_kapitel_bild as bild

__all__ = ["site"]

SEITE = "ki-kapitel-1.html"
ZUEGE = "[...document.querySelectorAll('#ki-k1-welt .ki-k1-zug')]"
DECKKRAFT = f"{ZUEGE}.map(g => getComputedStyle(g).opacity)"
SAETZE = (
    "[...document.querySelectorAll('.ki-k1-satz')]"
    ".map(e => getComputedStyle(e).opacity)"
)
ROUTE = "document.querySelector('#ki-k1-welt .ki-k1-route')"
VERSATZ = f"parseFloat(getComputedStyle({ROUTE}).strokeDashoffset)"
PUNKT_Y = "+document.querySelector('#ki-k1-welt .ki-k1-punkt').getAttribute('cy')"
ZAHLEN = "[...document.querySelectorAll('.ki-k1-zahl')].map(e => e.textContent)"
FUELLUNG = (
    "[getComputedStyle(document.querySelector('.ki-k1-fokus rect')).fill,"
    " getComputedStyle(document.querySelector('.ki-k1-wahl rect')).fill]"
)
UEBERLAPP = """() => {
  const box = e => e.getBoundingClientRect();
  const beschriftet = [...document.querySelectorAll('#ki-k1-welt text')]
    .map(t => [t.textContent, box(t)]).filter(([, r]) => r.width > 0);
  const saetze = [...document.querySelectorAll('.ki-k1-satz, .ki-k1-ansage span')]
    .map(e => [e.textContent, box(e)]);
  const treffer = [];
  for (const [s, a] of saetze) for (const [t, b] of beschriftet) {
    if (a.left < b.right && b.left < a.right && a.top < b.bottom && b.top < a.bottom)
      treffer.push([s, t]);
  }
  return treffer;
}"""


class _Stumm(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


@contextlib.contextmanager
def _seite(chromium, wurzel: Path, name=SEITE, breite=1440, hoehe=800, **optionen):
    handler = functools.partial(_Stumm, directory=str(wurzel))
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    kontext = chromium.new_context(
        viewport={"width": breite, "height": hoehe}, **optionen
    )
    try:
        page = kontext.new_page()
        page.goto(
            f"http://127.0.0.1:{httpd.server_address[1]}/{name}", wait_until="load"
        )
        page.wait_for_timeout(300)
        yield page
    finally:
        kontext.close()
        httpd.shutdown()


def _nach(page, anteil: float) -> None:
    page.evaluate(
        f"scrollTo(0, (document.documentElement.scrollHeight - innerHeight) * {anteil})"
    )
    page.wait_for_timeout(1800)


def test_knopf_und_schiene_fuehren_auf_die_seite_des_kapitels(site):
    html = (site / "ki.html").read_text(encoding="utf-8")
    knopf = re.search(r'<a class="ki-fahrt" href="([^"]+)"', html)
    schiene = re.findall(
        r'<li class="ki-kapitel ki-kapitel--fertig"><a href="([^"]+)"', html
    )
    assert knopf and knopf.group(1) == SEITE
    assert schiene == [SEITE]
    assert (site / SEITE).is_file()
    assert ki_seite.kapitel()[0]["ziel"] == SEITE == ki_kapitel.DATEI
    assert [k["ziel"] for k in ki_seite.kapitel()[1:]] == [None] * 11


def test_stationen_in_ihrer_reihenfolge_und_zahlen_aus_den_konstanten(site):
    html = (site / SEITE).read_text(encoding="utf-8")
    vorn = re.findall(r'<g class="ki-k1-station" data-station="([^"]+)"', html)
    texte = re.findall(r'class="ki-k1-ueber"[^>]*data-station="([^"]+)"', html)
    zahlen = re.findall(r'class="ki-k1-zahl"[^>]*>(\d+)<', html)
    anteile = re.findall(r'class="ki-k1-anteil[^"]*"[^>]*>(\d+) %<', html)
    werte = re.findall(r'class="ki-k1-wert[^"]*"[^>]*>(\d+) %<', html)
    assert ki_kapitel.STATIONEN == (
        "Frage",
        "Wörter",
        "Bedeutung",
        "Aufmerksamkeit",
        "Antwort",
    )
    assert vorn == list(ki_kapitel.STATIONEN)
    assert texte == sorted(texte, key=ki_kapitel.STATIONEN.index)
    assert set(texte) == set(ki_kapitel.STATIONEN)
    assert [int(z) for z in zahlen] == [n for _, n in bild.TOKENS]
    gross = [g for g in bild.GEWICHTE if g >= bild.ANTEIL_AB]
    assert [int(a) for a in anteile] == [round(g * 100) for g in gross]
    assert len(gross) < len(bild.GEWICHTE) - 1
    assert [int(w) for w in werte] == [round(p * 100) for _, p, _ in bild.KANDIDATEN]
    assert "Kann ich meinen Vertrag kündigen?" in html
    assert ">Kapitel 1 · Wie eine KI antwortet</h1>" in html


def test_die_fahrt_zeigt_pillen_erst_beim_scrollen_und_der_punkt_laeuft_mit(
    chromium, site
):
    with _seite(chromium, site) as page:
        page.wait_for_timeout(1200)
        start = page.evaluate(DECKKRAFT)
        saetze_start = page.evaluate(SAETZE)
        versatz_start, y_start = page.evaluate(VERSATZ), page.evaluate(PUNKT_Y)
        zahlen_start = page.evaluate(ZAHLEN)
        fuellung_start = page.evaluate(FUELLUNG)
        _nach(page, 0.45)
        mitte = page.evaluate(DECKKRAFT)
        versatz_mitte, y_mitte = page.evaluate(VERSATZ), page.evaluate(PUNKT_Y)
        _nach(page, 1)
        ende = page.evaluate(DECKKRAFT)
        saetze_ende = page.evaluate(SAETZE)
        versatz_ende, y_ende = page.evaluate(VERSATZ), page.evaluate(PUNKT_Y)
        zahlen_ende = page.evaluate(ZAHLEN)
        fuellung_ende = page.evaluate(FUELLUNG)
    assert start[-1] == "0" and start.count("1") < len(start) / 4
    assert set(saetze_start) == {"0"}
    assert versatz_start > 1000
    assert y_start < bild.FRAGE_Y
    assert set(zahlen_start) == {"00000"}
    assert fuellung_start == ["rgb(255, 255, 255)"] * 2
    assert start.count("1") < mitte.count("1") < len(mitte)
    assert versatz_start > versatz_mitte > versatz_ende
    assert y_start < y_mitte < y_ende
    assert set(ende) == {"1"}
    assert set(saetze_ende) == {"1"}
    assert versatz_ende < 5
    assert y_ende > bild.ANTWORT_Y
    assert zahlen_ende == [f"{n:05d}" for _, n in bild.TOKENS]
    assert fuellung_ende == ["rgb(19, 20, 23)", "rgb(230, 0, 0)"]


@pytest.mark.parametrize(
    "optionen", [{"reduced_motion": "reduce"}, {"java_script_enabled": False}]
)
def test_gegenprobe_ruhig_und_ohne_js_steht_alles_fertig_da(chromium, site, optionen):
    with _seite(chromium, site, **optionen) as page:
        deckkraft = page.evaluate(DECKKRAFT)
        saetze = page.evaluate(SAETZE)
        versatz = page.evaluate(VERSATZ)
        zahlen = page.evaluate(ZAHLEN)
        fuellung = page.evaluate(FUELLUNG)
        zeilen = page.evaluate(
            "[...document.querySelectorAll('.ki-k1-ansage i')]"
            ".map(e => getComputedStyle(e).transform)"
        )
    assert len(deckkraft) == 40 and set(deckkraft) == {"1"}
    assert len(saetze) == 5 and set(saetze) == {"1"}
    assert versatz == 0
    assert zahlen == [f"{n:05d}" for _, n in bild.TOKENS]
    assert fuellung == ["rgb(19, 20, 23)", "rgb(230, 0, 0)"]
    assert len(zeilen) == 9 and set(zeilen) == {"none"}


def test_der_knopf_auf_ki_html_oeffnet_die_fahrt(chromium, site):
    with _seite(chromium, site, name="ki.html") as page:
        with page.expect_navigation(wait_until="load"):
            page.evaluate("document.querySelector('#verstehen .ki-fahrt').click()")
        adresse = page.url
        titel = page.evaluate("document.querySelector('h1').textContent")
    assert adresse.endswith("/" + SEITE)
    assert titel == "Kapitel 1 · Wie eine KI antwortet"


@pytest.mark.parametrize("breite", [390, 1440])
def test_kein_satz_liegt_auf_einer_beschriftung(chromium, site, breite):
    with _seite(chromium, site, breite=breite, reduced_motion="reduce") as page:
        treffer = page.evaluate(UEBERLAPP)
        page.evaluate(
            "(() => { const t = document.querySelector('.ki-k1-ueber');"
            " const p = document.querySelector('.ki-k1-station .ki-k1-zug text');"
            " const r = p.getBoundingClientRect();"
            " const o = t.parentNode.getBoundingClientRect();"
            " t.style.top = (r.top - o.top - 20) + 'px'; })()"
        )
        gegenprobe = page.evaluate(UEBERLAPP)
    assert treffer == []
    assert gegenprobe


def test_auf_390_px_klebt_nichts_und_die_seite_laeuft_nicht_ueber(chromium, site):
    with _seite(chromium, site, breite=390, hoehe=844) as page:
        _nach(page, 0.5)
        breiten = page.evaluate("[document.documentElement.scrollWidth, innerWidth]")
        lagen = page.evaluate(
            "[...new Set([...document.querySelectorAll('body *')]"
            ".map(e => getComputedStyle(e).position))]"
        )
        gross = page.evaluate(
            "[...document.querySelectorAll('.ki-k1-ansage')]"
            ".map(e => parseFloat(getComputedStyle(e).fontSize))"
        )
        satz = page.evaluate(
            "parseFloat(getComputedStyle(document.querySelector('.ki-k1-satz')).fontSize)"
        )
    dokument, fenster = breiten
    assert dokument <= fenster
    assert "sticky" not in lagen and "fixed" not in lagen
    assert min(gross) > satz
