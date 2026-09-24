"""P2/D4b: DER AKTIVE NAVIGATIONSEINTRAG STEHT MOBIL IM BILD.

Gemeldeter Befund (geraete.html, 390 px): der aktive Eintrag "Geräte" der
Rubrikleiste (`.subbar.subnav a.on`, `base.html.j2`) stand beim Laden bei
x=536-620 px - komplett ausserhalb des 390-px-Viewports -, und der davor
liegende Eintrag "Differenzierung" war 20 px abgeschnitten. Die Leiste war
FUNKTIONAL erreichbar (`overflow-x:auto`), nur wurde beim Laden nie zu
ihrem aktiven Eintrag gescrollt.

Diese Datei baut die reale Markup-Form der Leiste (aus `base.html.j2`
kopiert, Stand 24.09.2026) nach und laedt das ECHTE `app.js`/`style.css`
- ohne die volle Rendering-Pipeline (die `geraete_verlinkt`-Schwelle der
kleinen Test-Fixtures verhindert dort den Eintrag "Geräte" ganz, siehe
`test_geraete_zeitreihe_browser.py`)."""
from __future__ import annotations

import contextlib
import functools
import glob
import http.server
import pathlib
import socket
import threading

import pytest

from telco_radar.report import geraete_zeitreihe as gz
from telco_radar.report.anbieter_farben import in_stylesheet

# Wortgetreu die Struktur der Rubrikleiste aus `base.html.j2` (die fuenf
# Eintraege der Marktrecherche, "Geräte" als aktiver/letzter Eintrag -
# genau der gemeldete Fall).
_NAV = """
<nav class="subbar subnav" aria-label="Marktrecherche">
  <a href="index.html">Diese Woche</a>
  <a href="meldungen.html">Meldungen</a>
  <a href="differenzierung.html">Differenzierung</a>
  <a href="wettbewerb.html">Wettbewerb</a>
  <a href="geraete.html" class="on">Geräte</a>
</nav>
"""


def _chromium():
    for muster in ("/opt/pw-browsers/chromium-*/chrome-linux/chrome",
                   str(pathlib.Path.home() / ".cache/ms-playwright"
                       / "chromium*/chrome-linux*/chrome")):
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


def _seite(tmp_path: pathlib.Path) -> pathlib.Path:
    html = (f"<!doctype html><html><head><meta charset='utf-8'>"
           f"<link rel='stylesheet' href='style.css'></head>"
           f"<body>{_NAV}<script src='app.js'></script></body></html>")
    (tmp_path / "index.html").write_text(html, encoding="utf-8")
    tmpl_dir = pathlib.Path(gz.__file__).parent / "templates"
    css = in_stylesheet((tmpl_dir / "style.css").read_text(encoding="utf-8"))
    (tmp_path / "style.css").write_text(css, encoding="utf-8")
    (tmp_path / "app.js").write_text(
        (tmpl_dir / "app.js").read_text(encoding="utf-8"), encoding="utf-8")
    return tmp_path


def test_der_aktive_eintrag_wird_beim_laden_ins_bild_gescrollt(tmp_path):
    sync_playwright = pytest.importorskip(
        "playwright.sync_api", reason="playwright fehlt").sync_playwright
    root = _seite(tmp_path)
    exe = _chromium()
    with _server(root) as basis, sync_playwright() as p:
        browser = (p.chromium.launch(executable_path=exe) if exe
                   else p.chromium.launch())
        try:
            page = browser.new_context(
                viewport={"width": 390, "height": 400}).new_page()
            page.goto(f"{basis}/index.html", wait_until="load")
            page.wait_for_timeout(150)
            box = page.eval_on_selector(
                ".subbar.subnav a.on", "e => e.getBoundingClientRect()")
        finally:
            browser.close()
    assert box is not None
    assert box["left"] >= -0.5 and box["right"] <= 390.5, (
        f"'{box}' - der aktive Eintrag steht nicht vollstaendig im "
        "390-px-Viewport")
