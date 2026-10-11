"""Modelle-Leiter und Rubrikleiste der KI-Seite im Chromium (Pitch 9, Schnitte 7, 8).

``app.js`` baut aus den eingebetteten Daten des Bands eine Linienzeichnung:
zehn Stufen in der Reihenfolge der Liste, je Modell ein Punkt in der Farbe
seiner Firma, ein roter Punkt fällt mit dem Scrollen. Gegenproben: bei
reduzierter Bewegung ist alles sofort sichtbar, ohne JavaScript bleibt die
Liste stehen. Der Store kommt aus den echten Abrufen unter
``tests/fixtures/ki/``, Stand fest am 11.10.2026.
"""

from __future__ import annotations

import contextlib
import functools
import gzip
import http.server
import json
import threading
from datetime import date
from pathlib import Path

import pytest
from bestand_pfad import verlinke_neben_data

from telco_radar.analyze import ki_modelle
from telco_radar.collect import ki_ranglisten
from telco_radar.config import load_config
from telco_radar.report.html import render_site

WURZEL = Path(__file__).resolve().parents[1]
FIXTURES = WURZEL / "tests" / "fixtures" / "ki"
TAG = date(2026, 10, 11)
NAMEN = [
    "Claude Opus 5.5",
    "Gemini 4 Argon",
    "Claude Fable 5.1",
    "Claude Sonnet 5.5",
    "GPT-6.1 Sol",
    "Muse Spark 1.3",
    "GPT-6 Astra",
    "Gemini 3.8 Flash",
    "Qwen3.8 Max",
    "Grok 4.7",
]


class _Stumm(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


@pytest.fixture(scope="module")
def site(tmp_path_factory) -> Path:
    tmp = tmp_path_factory.mktemp("ki-leiter")
    root = tmp / "repo"
    berichte = root / "data" / "reports"
    berichte.mkdir(parents=True)
    verlinke_neben_data(root)
    meldungen = [
        {
            "url": f"https://example.org/ki-anbieter/m{i}",
            "title": f"Neues Sprachmodell {i} vorgestellt",
            "summary": "Ein Anbieter zeigt ein neues Modell.",
            "source": "Beispielquelle",
            "date": TAG.isoformat(),
            "relevance": 3,
            "category": "Netz/Technologie",
        }
        for i in range(9)
    ]
    bericht = {
        "date": TAG.isoformat(),
        "regions": {"KI-Anbieter": {"highlights": meldungen}},
    }
    (berichte / f"{TAG.isoformat()}.json").write_text(json.dumps(bericht))
    roh = gzip.decompress((FIXTURES / "aa_tabelle.html.gz").read_bytes())
    arena = (FIXTURES / "arena_ldjson.html").read_text(encoding="utf-8")
    abruf = {
        "aa": {
            "url": "https://aa.example",
            "eintraege": ki_ranglisten.aa_index(roh.decode()),
        },
        "arena": {
            "url": "https://arena.example",
            "eintraege": ki_ranglisten.arena_plaetze(arena),
        },
    }
    katalog = ki_modelle.katalog(WURZEL)
    ki_modelle.aktualisiere(root / "data" / "state", katalog, abruf, TAG)
    ziel = tmp / "site"
    render_site(ziel, berichte, load_config(root))
    return ziel


@contextlib.contextmanager
def _seite(chromium, site: Path, breite: int = 1440, **optionen):
    handler = functools.partial(_Stumm, directory=str(site))
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    kontext = chromium.new_context(
        viewport={"width": breite, "height": 800}, **optionen
    )
    try:
        page = kontext.new_page()
        page.goto(
            f"http://127.0.0.1:{httpd.server_address[1]}/ki.html", wait_until="load"
        )
        page.wait_for_timeout(200)
        yield page
    finally:
        kontext.close()
        httpd.shutdown()


STUFEN = "[...document.querySelectorAll('#ki-leiter .ki-stufe')]"
PUNKT = "document.querySelector('#ki-leiter .ki-leiter-punkt')"
PUNKT_Y = f"+{PUNKT}.getAttribute('cy')"
ZEILEN = "[...document.querySelectorAll('.ki-ansage i')]"
TRANSFORM = f"{ZEILEN}.map(e => getComputedStyle(e).transform)"
FARBEN = (
    "(() => { const d = JSON.parse("
    "document.getElementById('ki-modelle-daten').textContent);"
    " const probe = document.createElement('span');"
    " document.body.appendChild(probe);"
    f" return {STUFEN}.map((g, i) => {{"
    " probe.style.color = 'var(' + d[i].farbe + ')';"
    " return [getComputedStyle(g.querySelector('.ki-stufe-punkt')).fill,"
    " getComputedStyle(probe).color, d[i].farbe]; }); })()"
)


def _scrolle_durch_band(page) -> None:
    ende = page.evaluate(
        "(() => { const b = document.getElementById('modelle').getBoundingClientRect();"
        " return b.bottom + scrollY - innerHeight; })()"
    )
    page.evaluate(f"scrollTo(0, {ende})")
    page.wait_for_timeout(1500)


def test_leiter_hat_zehn_stufen_in_der_reihenfolge_der_liste(chromium, site):
    with _seite(chromium, site) as page:
        namen = page.evaluate(
            f"{STUFEN}.map(g => g.querySelector('.ki-stufe-name').textContent)"
        )
        liste = page.evaluate(
            "[...document.querySelectorAll('.ki-rang-name')].map(e => e.textContent)"
        )
        ol = page.evaluate(
            "getComputedStyle(document.querySelector('.ki-rang')).display"
        )
    assert namen == NAMEN == liste
    assert ol == "none"


def test_firmenpunkt_hat_die_farbe_seiner_firma(chromium, site):
    with _seite(chromium, site) as page:
        paare = page.evaluate(FARBEN)
    assert len(paare) == 10
    for fill, erwartet, _ in paare:
        assert fill == erwartet
    assert paare[0][2] == "--ki-anthropic" and paare[1][2] == "--ki-google"
    assert paare[0][0] != paare[1][0]


def test_roter_punkt_faellt_beim_scrollen_und_stufen_erscheinen(chromium, site):
    with _seite(chromium, site) as page:
        vorher = page.evaluate(PUNKT_Y)
        sichtbar_vorher = page.evaluate(
            f"{STUFEN}.filter(g => g.classList.contains('da')).length"
        )
        letzte = page.evaluate(f"getComputedStyle({STUFEN}[9]).opacity")
        _scrolle_durch_band(page)
        nachher = page.evaluate(PUNKT_Y)
        sichtbar = page.evaluate(
            f"{STUFEN}.filter(g => getComputedStyle(g).opacity === '1').length"
        )
        rot = page.evaluate(f"getComputedStyle({PUNKT}).fill")
    assert sichtbar_vorher == 0 and letzte == "0"
    assert nachher > vorher + 300
    assert sichtbar == 10
    assert rot == "rgb(230, 0, 0)"


def test_gegenprobe_reduzierte_bewegung_zeigt_alles_sofort(chromium, site):
    with _seite(chromium, site, reduced_motion="reduce") as page:
        deckkraft = page.evaluate(f"{STUFEN}.map(g => getComputedStyle(g).opacity)")
        zeilen = page.evaluate(TRANSFORM)
        punkt = page.evaluate(PUNKT_Y)
        unten = page.evaluate(
            "+document.getElementById('ki-leiter').viewBox.baseVal.height"
        )
    assert deckkraft == ["1"] * 10
    assert zeilen and set(zeilen) == {"none"}
    assert punkt == unten - 10


def test_gegenprobe_ohne_javascript_bleibt_die_liste(chromium, site):
    with _seite(chromium, site, java_script_enabled=False) as page:
        hoehe = page.evaluate(
            "document.querySelector('.ki-rang').getBoundingClientRect().height"
        )
        svg = page.evaluate("document.getElementById('ki-leiter')")
        zeilen = page.evaluate(TRANSFORM)
    assert hoehe > 200
    assert svg is None
    assert set(zeilen) == {"none"}


@pytest.mark.parametrize("breite", [1440, 390])
def test_rubrikleiste_erscheint_nach_dem_kopf_und_passt_auf_den_schirm(
    chromium, site, breite
):
    with _seite(chromium, site, breite=breite) as page:
        vorher = page.evaluate(
            "getComputedStyle(document.getElementById('ki-rubriken')).opacity"
        )
        _scrolle_durch_band(page)
        box = page.evaluate(
            "document.getElementById('ki-rubriken').getBoundingClientRect().toJSON()"
        )
        deck = page.evaluate(
            "getComputedStyle(document.getElementById('ki-rubriken')).opacity"
        )
        aktiv = page.evaluate(
            "[...document.querySelectorAll('#ki-rubriken a.an')]"
            ".map(a => a.getAttribute('href'))"
        )
        page.click("#ki-rubriken a[href='#meldungen']")
        page.wait_for_timeout(1500)
        oben = page.evaluate(
            "document.getElementById('meldungen').getBoundingClientRect().top"
        )
        unter_leiste = page.evaluate(
            "document.getElementById('ki-rubriken').getBoundingClientRect().bottom"
        )
    assert vorher == "0" and deck == "1"
    assert box["left"] >= 0 and box["right"] <= breite
    assert aktiv == ["#modelle"]
    assert unter_leiste <= oben < 200
