"""Der Abschnitt „Verstehen“ der KI-Seite im Chromium (Pitch 9, Schnitt 9).

Unter dem Modelle-Band steht die Ansage „Wie antwortet eigentlich eine KI?“,
darunter eine Linie, die sich mit dem Scrollen zeichnet (strokeDashoffset
sinkt), und die Schiene mit allen Kapiteln aus ``ki_seite.KAPITEL``; nur
die fertigen sind rot und verlinkt. Gegenproben: bei reduzierter Bewegung
und ohne JavaScript ist die Linie voll gezeichnet, die Pillen sind sichtbar.
Auf 390 px wischt die Schiene seitlich, die Seite läuft nicht über. Der
Aufbau der Site kommt aus ``test_ki_leiter_browser`` (fester Tag).
"""

from __future__ import annotations

import contextlib
import functools
import http.server
import threading
from pathlib import Path

import pytest
from test_ki_leiter_browser import site

from telco_radar.report import ki_seite

__all__ = ["site"]

WEG = "document.querySelector('#verstehen .ki-fahrt-weg')"
VERSATZ = f"parseFloat(getComputedStyle({WEG}).strokeDashoffset)"
PILLEN = (
    "[...document.querySelectorAll('#verstehen .ki-zug')]"
    ".map(g => [g.textContent.trim(), getComputedStyle(g).opacity])"
)
SCHIENE = "document.querySelector('#verstehen ol.ki-schiene')"


class _Stumm(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


@contextlib.contextmanager
def _seite(chromium, wurzel: Path, breite: int = 1440, **optionen):
    handler = functools.partial(_Stumm, directory=str(wurzel))
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


def _bis_zur_schiene(page) -> None:
    page.evaluate(f"{SCHIENE}.scrollIntoView({{block: 'end'}})")
    page.wait_for_timeout(1800)


def test_schiene_zeigt_alle_kapitel_der_konstante_und_verlinkt_nur_kapitel_1(
    chromium, site
):
    with _seite(chromium, site) as page:
        knoten = page.evaluate(
            f"[...{SCHIENE}.children].map(li => [li.querySelector('b').textContent,"
            " li.textContent.slice(li.querySelector('b').textContent.length).trim(),"
            " li.querySelector('a') && li.querySelector('a').getAttribute('href'),"
            " getComputedStyle(li.querySelector('b')).color])"
        )
        spalten = page.evaluate(
            f"getComputedStyle({SCHIENE}).gridTemplateColumns.split(' ').length"
        )
        ansage = page.evaluate("document.querySelector('#verstehen h2').textContent")
        folge = page.evaluate(
            "[...document.querySelectorAll('main section[id]')].map(s => s.id)"
        )
    assert len(ki_seite.KAPITEL) == 12
    assert [k[1] for k in knoten] == list(ki_seite.KAPITEL)
    assert [k[0] for k in knoten] == [str(i) for i in range(1, 13)]
    fertig = [f"ki-kapitel-{n}.html" for n in (1, 2, 3, 4)]
    assert [k[2] for k in knoten] == fertig + [None] * 8
    assert {k[3] for k in knoten[:4]} == {"rgb(204, 0, 0)"}
    assert {k[3] for k in knoten[4:]} == {knoten[4][3]} != {knoten[0][3]}
    assert spalten == 12
    assert ansage == "Wie antworteteigentlicheine KI?"
    assert folge.index("verstehen") == folge.index("meldungen") + 1


def test_linie_zeichnet_sich_beim_scrollen_und_pillen_poppen_auf(chromium, site):
    with _seite(chromium, site) as page:
        page.wait_for_timeout(700)
        vorher = page.evaluate(VERSATZ)
        pillen_vorher = page.evaluate(PILLEN)
        page.evaluate(
            "scrollTo(0, document.getElementById('verstehen')"
            ".getBoundingClientRect().top + scrollY - innerHeight * 0.3)"
        )
        page.wait_for_timeout(1500)
        mitte = page.evaluate(VERSATZ)
        _bis_zur_schiene(page)
        nachher = page.evaluate(VERSATZ)
        pillen = page.evaluate(PILLEN)
        punkt = page.evaluate(
            "getComputedStyle(document.querySelector("
            "'#verstehen .ki-fahrt-punkt')).fill"
        )
    assert [p[0] for p in pillen] == ["Frage", "Wörter", "Bedeutung", "Antwort"]
    assert vorher > 500
    assert {p[1] for p in pillen_vorher[1:]} == {"0"}
    assert vorher > mitte > nachher
    assert nachher < 5
    assert [p[1] for p in pillen] == ["1"] * 4
    assert punkt == "rgb(230, 0, 0)"


@pytest.mark.parametrize(
    "optionen", [{"reduced_motion": "reduce"}, {"java_script_enabled": False}]
)
def test_gegenprobe_ruhig_und_ohne_js_ist_die_linie_voll(chromium, site, optionen):
    with _seite(chromium, site, **optionen) as page:
        versatz = page.evaluate(VERSATZ)
        pillen = page.evaluate(PILLEN)
        zeilen = page.evaluate(
            "[...document.querySelectorAll('#verstehen h2 i')]"
            ".map(e => getComputedStyle(e).transform)"
        )
    assert versatz == 0
    assert pillen and [p[1] for p in pillen] == ["1"] * 4
    assert len(zeilen) == 3 and set(zeilen) == {"none"}


def test_auf_390_px_wischt_die_schiene_und_die_seite_laeuft_nicht_ueber(chromium, site):
    with _seite(chromium, site, breite=390) as page:
        _bis_zur_schiene(page)
        breiten = page.evaluate(
            f"[{SCHIENE}.scrollWidth, {SCHIENE}.clientWidth,"
            " document.documentElement.scrollWidth, innerWidth]"
        )
        page.evaluate(f"{SCHIENE}.scrollLeft = 400")
        page.wait_for_timeout(600)
        links = page.evaluate(f"{SCHIENE}.scrollLeft")
        bild = page.evaluate(
            "document.querySelector('#verstehen svg').getAttribute('viewBox')"
        )
    schiene, sichtbar, dokument, fenster = breiten
    assert schiene > sichtbar + 600
    assert links > 100
    assert dokument <= fenster
    assert bild == "0 -60 1000 340"


def test_rubrikleiste_zeigt_verstehen_mit_der_zahl_der_kapitel(chromium, site):
    with _seite(chromium, site) as page:
        _bis_zur_schiene(page)
        eintraege = page.evaluate(
            "[...document.querySelectorAll('#ki-rubriken a')]"
            ".map(a => [a.getAttribute('href'), a.textContent.trim(),"
            " a.classList.contains('an')])"
        )
    assert ["#verstehen", "Verstehen 12", True] in eintraege
    assert [e[0] for e in eintraege][:3] == ["#meldungen", "#modelle", "#verstehen"]
