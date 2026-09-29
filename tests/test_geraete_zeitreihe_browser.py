"""Die Geräteseite im echten Chromium an der Zeitreihen-Fixture - Konsole
und Querscroll. Dieselbe Bauform wie die übrigen Browser-Tests (eigener
Server auf 127.0.0.1, kein file://, Chromium an beiden bekannten Orten).

Bis zum Neuentwurf (29.09.2026) prüfte diese Datei die Zeitreihen-
Hauptansicht (Falz, Suche, Band-Wahl, Deep-Link); mit ihr sind diese Tests
gefallen. Geblieben sind die zwei Aussagen, die für jede Fassung der Seite
gelten: null JavaScript-Konsolenfehler und kein seitenweiter Querscroll
auf dem Telefon. Die Kosten-Rangliste selbst misst
`tests/test_geraete_kosten_browser.py`.
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

from browser_konsole import konsole_sammeln
from test_geraete_zeitreihe_ansicht import HEUTE, _baue


def _baue_site(tmp_path: pathlib.Path) -> pathlib.Path:
    root, state = _baue(tmp_path)
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
def _browser_seite(tmp_path_factory):
    sync_playwright = pytest.importorskip(
        "playwright.sync_api", reason="playwright fehlt").sync_playwright
    site = _baue_site(tmp_path_factory.mktemp("zrbrowser"))
    exe = _chromium()
    with _server(site) as basis, sync_playwright() as p:
        browser = (p.chromium.launch(executable_path=exe) if exe
                   else p.chromium.launch())
        yield browser, basis
        browser.close()


@contextlib.contextmanager
def _ansicht(_browser_seite, breite=1440, hoehe=900, touch=False):
    browser, basis = _browser_seite
    # touch=True (E2-F3): erst ein Kontext mit has_touch kann tap() senden -
    # die Mobil-Tests gehen den echten Fingerweg, nicht den Mausklick.
    context = browser.new_context(viewport={"width": breite, "height": hoehe},
                                  has_touch=touch)
    s = context.new_page()
    fehler = konsole_sammeln(s)
    s.goto(f"{basis}/geraete.html", wait_until="load")
    s.wait_for_timeout(250)
    try:
        yield s, fehler
    finally:
        context.close()


@pytest.fixture
def schreibtisch(_browser_seite):
    with _ansicht(_browser_seite) as paar:
        yield paar


@pytest.fixture
def telefon(_browser_seite):
    with _ansicht(_browser_seite, 390, 844, touch=True) as paar:
        yield paar


# --------------------------------------------------------------------------
# Konsole und Querscroll
# --------------------------------------------------------------------------

def test_keine_javascript_fehler_auf_der_startansicht(schreibtisch):
    s, fehler = schreibtisch
    # Gegenprobe: die Seite trägt die Rangliste, deren Skript läuft -
    # sonst wäre "keine Fehler" die Aussage über eine leere Seite.
    assert s.query_selector("#kv-daten") is not None, \
        "die Fixture rendert keine Kosten-Rangliste - Test prüft nichts"
    assert s.query_selector_all("#kv-ergebnis .kv-zeile"), \
        "keine Zeile in der Rangliste"
    assert fehler == [], f"Konsolenfehler: {fehler[:3]}"


def test_die_seite_verursacht_keinen_seitenweiten_querscroll(telefon):
    s, _ = telefon
    breite = s.evaluate("() => Math.max(document.documentElement.scrollWidth,"
                        " document.body.scrollWidth)")
    assert breite <= 391, f"die Seite ist {breite} px breit (Telefon 390 px)"
