"""P5-Live-Pruefung R3: der Neu-Hinweis am Zeitreihen-Suchfeld - im
echten Chromium gemessen.

Warum im Browser: der Hinweis entsteht im JS (0 Treffer in der WAHL,
Treffer im Katalog-Teil desselben Knotens), und sein Klick verkettet
drei Mechaniken (Reiter-Umschaltung + Katalog-Sprung-Handler + Zeilen-
Markierung). Im statischen HTML steht nur der JSON-Knoten - ob die
Zeile erscheint, springt und trifft, sieht man erst im gerenderten
Dokument. Bauform wie `test_geraete_zeitreihe_browser.py` (eigener
Server auf 127.0.0.1, kein file://, Chromium an beiden bekannten Orten).

Fixture: `_baue_buendel_modell` aus der P5-Sichtbarkeits-Datei - ein
Auto-Modell (iPad Pro 13) mit EINEM Bündel-Messtag, ohne Listung: der
gemessene iPhone-18-Weg vom 17.09.
"""
from __future__ import annotations

import contextlib
import functools
import glob
import http.server
import json
import pathlib
import socket
import threading

import pytest

from telco_radar.report.html import render_site

from test_geraete_zeitreihe_ansicht import HEUTE
from test_geraete_sichtbarkeit_p5 import _MID, _baue_buendel_modell


def _baue_site(tmp_path: pathlib.Path) -> pathlib.Path:
    root, _ = _baue_buendel_modell(tmp_path, ["2026-09-15"])
    reports = root / "data" / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    (reports / f"{HEUTE}.json").write_text(json.dumps({
        "date": HEUTE, "language": "de",
        "briefing_md": "## Auf einen Blick\n\n- Nichts.\n",
        "stats": {}, "regions": []}), encoding="utf-8")
    (reports / f"{HEUTE}.md").write_text("# B\n", encoding="utf-8")
    site = root / "site"
    render_site(site, reports)
    return site


def _chromium():
    for muster in ("/opt/pw-browsers/chromium-*/chrome-linux/chrome",
                   str(pathlib.Path.home() / ".cache/ms-playwright"
                       / "chromium*/chrome-linux*/chrome"),
                   "/Applications/Chromium.app/Contents/MacOS/Chromium"):
        treffer = sorted(glob.glob(muster))
        if treffer:
            return treffer[-1]
    return None


@contextlib.contextmanager
def _server(site: pathlib.Path):
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    handler = functools.partial(http.server.SimpleHTTPRequestHandler,
                                directory=str(site))
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", port), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        httpd.shutdown()


@pytest.fixture(scope="module")
def paar(tmp_path_factory):
    pytest.importorskip("playwright")
    from playwright.sync_api import sync_playwright
    site = _baue_site(tmp_path_factory.mktemp("p5-neu"))
    with _server(site) as basis:
        with sync_playwright() as p:
            exe = _chromium()
            browser = (p.chromium.launch(executable_path=exe) if exe
                       else p.chromium.launch())
            seite = browser.new_page(viewport={"width": 1440, "height": 900})
            seite.goto(f"{basis}/geraete.html", wait_until="load")
            yield seite
            browser.close()


def _suche(seite, begriff):
    # Das Suchfeld lebt im VERGLEICHs-Reiter - nach dem Sprungtest steht
    # der Katalog aktiv, und fill() auf ein unsichtbares Feld laeuft in
    # einen Timeout. Erst zurueckschalten, dann tippen.
    knopf = seite.query_selector('.gr-reiter button[data-tafel="tafel-tco"]')
    if knopf and knopf.get_attribute("aria-selected") != "true":
        knopf.click()
        seite.wait_for_timeout(80)
    feld = seite.query_selector("#gr-zr-suche")
    assert feld is not None, "Zeitreihen-Suchfeld fehlt"
    feld.fill(begriff)
    seite.wait_for_timeout(80)


def test_null_treffer_mit_katalog_treffer_zeigt_den_neu_hinweis(paar):
    """"ipad" in die Zeitreihen-Suche: die Wahl kennt das Modell nicht
    (ein Messtag), der Katalog traegt es - der Hinweis nennt Datum und
    fuehrt auf die Katalog-Zeile, der Zaehler sagt "kein Treffer"."""
    _suche(paar, "ipad")
    assert paar.eval_on_selector("#gr-zr-treffer", "e => e.textContent") \
        .strip() == "kein Treffer"
    hinweis = paar.query_selector(".gr-zr-vorschau a.gr-zr-v-neu")
    assert hinweis is not None, "Neu-Hinweis erscheint nicht"
    assert hinweis.get_attribute("data-modell") == _MID
    assert "Neu seit" in (hinweis.text_content() or "")
    assert "Katalog ansehen" in (hinweis.text_content() or "")


def test_der_hinweis_springt_auf_die_katalog_zeile(paar):
    """Der Klick nimmt denselben Weg wie die Radar-Liste: Katalog-Reiter
    aktiv, Zielzeile EINMAL markiert (.gr-k-ziel) - und sichtbar."""
    _suche(paar, "ipad")
    paar.click(".gr-zr-vorschau a.gr-zr-v-neu")
    paar.wait_for_timeout(200)
    assert paar.eval_on_selector(
        '.gr-reiter button[data-tafel="tafel-katalog"]',
        "e => e.getAttribute('aria-selected')") == "true", \
        "der Katalog-Reiter ist nach dem Klick nicht aktiv"
    ziel = paar.query_selector(f'tr.gr-k-zeile[data-modell="{_MID}"]')
    assert ziel is not None, "Katalog-Zeile des Modells fehlt"
    assert "gr-k-ziel" in (ziel.get_attribute("class") or ""), \
        "die Zielzeile ist nach dem Sprung nicht markiert"


def test_ohne_katalog_treffer_bleibt_die_vorschau_leer(paar):
    """Ein Begriff, den weder Wahl noch Katalog kennen: nur "kein
    Treffer", kein Zusatz - der Hinweis ist kein Dauerzustand."""
    _suche(paar, "qq")
    assert paar.eval_on_selector("#gr-zr-treffer", "e => e.textContent") \
        .strip() == "kein Treffer"
    assert paar.query_selector(".gr-zr-vorschau a.gr-zr-v-neu") is None


def test_mit_wahl_treffer_steht_kein_neu_hinweis(paar):
    """Gegenprobe am normalen Fall: "iphone 17" trifft die Wahl - normale
    Trefferliste, kein Neu-Hinweis daneben."""
    _suche(paar, "iphone 17")
    treffer = paar.eval_on_selector("#gr-zr-treffer", "e => e.textContent")
    assert "kein Treffer" not in treffer
    assert paar.query_selector(".gr-zr-vorschau a.gr-zr-v-neu") is None
    assert paar.query_selector_all(".gr-zr-vorschau button"), \
        "die Trefferliste selbst fehlt - der Test prueft dann nichts"
