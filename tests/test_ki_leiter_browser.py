"""Kopf, Fenster der Modelle und Rubrikleiste der KI-Seite im Chromium.

Antonio, 14.10.2026: kein Startbild, durch das man erst scrollen muss; die
Meldungen und die Wegweiser zu Verstehen, Prompts und Modellen stehen im
ersten Bildschirm. Die Rangliste ist ein kleines Fenster im ersten Ressort
neben den Artikeln, je Modell ein Punkt in der Farbe seiner Firma.
Der Kopf ist das Kopfband aller Reiter, ohne Kinostrecke. Der Store kommt
aus den echten Abrufen unter ``tests/fixtures/ki/``, Stand fest am 11.10.2026.
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


FENSTER = "document.getElementById('modelle')"
BOX = (
    "e => { const r = e.getBoundingClientRect();"
    " return [r.left, r.top, r.right, r.bottom]; }"
)
FARBEN = (
    "(() => { const probe = document.createElement('span');"
    " document.body.appendChild(probe);"
    " return [...document.querySelectorAll('#modelle .ki-rang-punkt')].map(p => {"
    " const farbe = p.style.getPropertyValue('--firma').slice(4, -1);"
    " probe.style.color = 'var(' + farbe + ')';"
    " return [getComputedStyle(p).backgroundColor,"
    " getComputedStyle(probe).color, farbe]; }); })()"
)


def _scrolle_zu(page, auswahl: str, rand: int = 100) -> None:
    page.evaluate(
        f"scrollTo(0, document.querySelector('{auswahl}')"
        f".getBoundingClientRect().top + scrollY - {rand})"
    )
    page.wait_for_timeout(600)


def test_fenster_listet_die_zehn_modelle_in_der_reihenfolge_der_liste(chromium, site):
    with _seite(chromium, site) as page:
        namen = page.evaluate(
            f"[...{FENSTER}.querySelectorAll('.ki-rang-name')].map(e => e.textContent)"
        )
        schrift = page.evaluate(
            f"[...{FENSTER}.querySelectorAll('.ki-rang-name')]"
            ".map(e => parseFloat(getComputedStyle(e).fontSize))"
        )
    assert namen == NAMEN
    assert all(schrift[0] > s for s in schrift[1:])


def test_firmenpunkt_hat_die_farbe_seiner_firma(chromium, site):
    with _seite(chromium, site) as page:
        paare = page.evaluate(FARBEN)
    assert len(paare) == 10
    for farbe, erwartet, _ in paare:
        assert farbe == erwartet
    assert paare[0][2] == "--ki-anthropic" and paare[1][2] == "--ki-google"
    assert paare[0][0] != paare[1][0]


def test_fenster_steht_klein_im_ersten_ressort_neben_dem_aufmacher(chromium, site):
    with _seite(chromium, site) as page:
        ressort = page.evaluate(
            f"{FENSTER}.closest('.ki-ressort') === "
            "document.querySelector('#meldungen .ki-ressort')"
        )
        fenster = page.evaluate(f"({BOX})({FENSTER})")
        kopf = page.evaluate(
            f"({BOX})(document.querySelector('.ki-ressort--fenster .ki-meldung--kopf'))"
        )
    assert ressort is True
    assert fenster[0] >= kopf[2]
    assert abs(fenster[1] - kopf[1]) < 40
    assert fenster[3] - fenster[1] < 520
    assert fenster[2] - fenster[0] < 1440 * 0.34


@pytest.mark.parametrize("breite", [1440, 390])
def test_meldungen_und_wegweiser_stehen_im_ersten_bildschirm(chromium, site, breite):
    with _seite(chromium, site, breite=breite) as page:
        hoehe = page.evaluate("innerHeight")
        aufmacher = page.evaluate(
            f"({BOX})(document.querySelector('.ki-meldung--aufmacher .ki-schlag'))"
        )
        tueren = page.evaluate(
            f"[...document.querySelectorAll('.ki-tuer')].map(a =>"
            f" [a.getAttribute('href'), ...({BOX})(a)])"
        )
        buehne = page.evaluate(
            "[!!document.querySelector('.ki-auftakt.kopfband'),"
            " !!document.querySelector('[data-buehne]')]"
        )
    assert aufmacher[1] < hoehe - 60
    assert [t[0] for t in tueren] == ["#verstehen", "#prompts", "#modelle"]
    for _, links, oben, rechts, unten in tueren:
        assert links >= 0 and rechts <= breite and oben > 0 and unten <= hoehe
    assert buehne == [True, False]


def test_wegweiser_fuehren_zu_ihrem_teil(chromium, site):
    with _seite(chromium, site) as page:
        lagen = {}
        for ziel in ("#verstehen", "#prompts", "#modelle"):
            page.evaluate("scrollTo(0, 0)")
            page.click(f".ki-tuer[href='{ziel}']")
            page.wait_for_timeout(1200)
            lagen[ziel] = page.evaluate(
                f"document.querySelector('{ziel}').getBoundingClientRect().top"
            )
    for ziel, oben in lagen.items():
        assert 0 <= oben < 200, (ziel, oben)


def test_kopf_steht_sofort_und_faehrt_beim_scrollen_nicht_mit(chromium, site):
    with _seite(chromium, site) as page:
        namen = page.evaluate(
            "[...document.querySelectorAll('.ki-auftakt .wa-motiv, .ki-tuer')]"
            ".map(e => getComputedStyle(e).animationName)"
        )
        vorher = page.evaluate(
            "document.querySelector('.ki-auftakt').getBoundingClientRect().height"
        )
        page.evaluate("scrollTo(0, 300)")
        page.wait_for_timeout(400)
        nachher = page.evaluate(
            "document.querySelector('.ki-auftakt').getBoundingClientRect().height"
        )
    assert len(namen) == 4 and set(namen) == {"none"}
    assert vorher == nachher <= 400


@pytest.mark.parametrize("breite", [1440, 390])
def test_rubrikleiste_erscheint_nach_dem_kopf_und_folgt_dem_lesen(
    chromium, site, breite
):
    with _seite(chromium, site, breite=breite) as page:
        vorher = page.evaluate(
            "getComputedStyle(document.getElementById('ki-rubriken')).opacity"
        )
        _scrolle_zu(page, "#modelle", 200)
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
        _scrolle_zu(page, ".ki-oben", 0)
        danach = page.evaluate(
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
    assert danach == ["#meldungen"]
    assert unter_leiste <= oben < 200
