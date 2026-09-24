"""P2/D2: DIE X-ACHSE UEBERLAPPT NICHT - im echten Chromium gemessen.

Gemeldeter Befund (mobil, 390 px): bei dichten Tagesmessungen liefen die
X-Achsen-Labels ineinander ("12.913.914.915.916.917.918.919.920.9" statt
neun getrennter Marken). `geraete_zeitreihe._svg` beschriftete bis dahin
JEDEN echten Messtag - unabhaengig davon, wie viel Platz ihm die
Bildbreite liess.

Diese Datei rendert `_svg()` direkt (ohne die volle Pipeline: keine
Katalog-/Buendel-Fixtures noetig) mit zwoelf taeglichen Messtagen in eine
kleine, eigene HTML-Seite und misst die Boundingboxen der
`text.gr-zr-xtick`-Knoten in echtem Chromium auf 390 px Breite - dieselbe
Bauform (eigener Server, Chromium an beiden bekannten Orten) wie
`test_geraete_zeitreihe_browser.py`.
"""
from __future__ import annotations

import contextlib
import functools
import glob
import http.server
import pathlib
import socket
import threading
from datetime import date, timedelta

import pytest

from telco_radar.report import geraete_zeitreihe as gz
from telco_radar.report.anbieter_farben import in_stylesheet


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
def _server(root: pathlib.Path):
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    handler = functools.partial(http.server.SimpleHTTPRequestHandler,
                                directory=str(root))
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", port), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        httpd.shutdown()


def _dichte_seite(tmp_path: pathlib.Path, breit: bool) -> pathlib.Path:
    """Zwoelf taegliche Vodafone-Messtage - genug, um jede feste
    Labelzahl (bei 358 px schmal / 1136 px breit) zu sprengen, wenn KEINE
    Ausduennung stattfindet."""
    start = date(2026, 9, 1)
    tage = [(start + timedelta(days=i)).isoformat() for i in range(12)]
    serien = {"Vodafone": [(t, 900.0 + i) for i, t in enumerate(tage)]}
    beleg = {"Vodafone": ("https://example.de/vodafone", "2026-09-20")}
    svg = gz._svg(serien, breit, beleg, None)
    breite = gz.BREIT_W if breit else gz.SCHMAL_W
    html = (f"<!doctype html><html><head><meta charset='utf-8'>"
           f"<link rel='stylesheet' href='style.css'></head>"
           f"<body style='margin:0'><div class='gr-zr-bild' "
           f"style='width:{breite}px'>{svg}</div></body></html>")
    (tmp_path / "index.html").write_text(html, encoding="utf-8")
    css_pfad = (pathlib.Path(gz.__file__).parent / "templates" / "style.css")
    css = in_stylesheet(css_pfad.read_text(encoding="utf-8"))
    (tmp_path / "style.css").write_text(css, encoding="utf-8")
    return tmp_path


def _messe_ueberlapp(tmp_path, breite_px, breit):
    sync_playwright = pytest.importorskip(
        "playwright.sync_api", reason="playwright fehlt").sync_playwright
    root = _dichte_seite(tmp_path, breit)
    exe = _chromium()
    with _server(root) as basis, sync_playwright() as p:
        browser = (p.chromium.launch(executable_path=exe) if exe
                   else p.chromium.launch())
        try:
            context = browser.new_context(
                viewport={"width": breite_px, "height": 700})
            page = context.new_page()
            page.goto(f"{basis}/index.html", wait_until="load")
            boxen = page.eval_on_selector_all(
                "text.gr-zr-xtick",
                "els => els.map(e => {"
                "const r = e.getBoundingClientRect();"
                "return {links: r.left, rechts: r.right, "
                "text: e.textContent};})")
        finally:
            browser.close()
    return boxen


def test_x_labels_ueberlappen_nicht_schmal_390px(tmp_path):
    boxen = _messe_ueberlapp(tmp_path, 390, breit=False)
    assert len(boxen) >= 2, "zu wenige X-Labels fuer eine Ueberlapp-Probe"
    boxen.sort(key=lambda b: b["links"])
    for a, b in zip(boxen, boxen[1:]):
        assert a["rechts"] <= b["links"] + 0.5, (
            f"X-Labels ueberlappen: {a['text']!r} "
            f"({a['links']:.1f}-{a['rechts']:.1f}) trifft "
            f"{b['text']!r} ({b['links']:.1f}-{b['rechts']:.1f})")


def test_x_labels_ueberlappen_nicht_breit_1440px(tmp_path):
    boxen = _messe_ueberlapp(tmp_path, 1440, breit=True)
    assert len(boxen) >= 2, "zu wenige X-Labels fuer eine Ueberlapp-Probe"
    boxen.sort(key=lambda b: b["links"])
    for a, b in zip(boxen, boxen[1:]):
        assert a["rechts"] <= b["links"] + 0.5, (
            f"X-Labels ueberlappen: {a['text']!r} "
            f"({a['links']:.1f}-{a['rechts']:.1f}) trifft "
            f"{b['text']!r} ({b['links']:.1f}-{b['rechts']:.1f})")


def test_jeder_messtag_traegt_trotzdem_eine_rasterlinie(tmp_path):
    """Die Ausduennung betrifft nur die TEXT-Marke - Antonios Wunsch
    ("ich möchte dann genau die verschiedenen Messtage immer sehen")
    bleibt als Rasterlinie je Messtag stehen."""
    root = _dichte_seite(tmp_path, breit=False)
    svg = (root / "index.html").read_text(encoding="utf-8")
    # eine Rasterlinie je Messtag PLUS die y-Rasterlinien - untere Grenze
    # reicht: mindestens 12 vertikale x1==x2 Linien.
    import re
    linien = re.findall(r"<line class='gr-zr-raster' x1='([\d.]+)' "
                        r"y1='[\d.]+' x2='([\d.]+)'", svg)
    vertikale = [l for l in linien if l[0] == l[1]]
    assert len(vertikale) == 12, (
        f"{len(vertikale)} vertikale Rasterlinien statt 12 Messtagen")
