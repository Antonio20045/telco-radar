"""P2/D4b: DAS ALTERUNGS-ABZEICHEN BRICHT MOBIL NICHT IN EINEN STAPEL
EINZELKAESTCHEN.

Gemeldeter Befund: "kein aktueller Stand seit 15.09.2026"
(`.gr-kk-marke.gr-kk-marke--alt`, gesetzt am Buendel-Kopf
`_geraete_buendel.html.j2` UND an der Katalogzeile `geraete.html.j2`)
brach in der schmalen Anbieterspalte des Buendel-Kopfs auf dem Telefon in
mehrere Zeilen - und weil `.gr-kk-marke` bis dahin `display:inline` war,
zeichnete jede umgebrochene Zeile ihren EIGENEN 1-px-Rahmen: ein Stapel
kleiner Kaesten statt EINER Marke.

Dieser Test baut die REALE Markup-Form des Buendel-Kopfs nach (Stand
24.09.2026, aus einem echten `render_site()`-Lauf kopiert - siehe
Kommentar unten) in eine kleine eigenstaendige Seite und misst mit
`getClientRects()`, ob der Rahmen EIN zusammenhaengendes Rechteck bleibt.
`_geraete_buendel.html.j2` selbst gehoert nicht zu diesem Paket (Phase P2,
D3 baut parallel an der Buendel-TABELLE) - der Fix ist rein CSS
(`.gr-kk-marke{display:inline-block}`), reproduziert hier deshalb ohne
die volle Buendel-Pipeline."""
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

# Wortgetreu aus einem echten `render_site()`-Lauf (data/reports, Stand
# 24.09.2026) kopiert: der Buendel-Kopf einer ALTEN o2-Zeile in der
# schmalen Grid-Spalte ".gr-bnd-an".
_BUNDLE_KOPF = """
<div class="gr-bndliste">
<details class="gr-bnd gr-bnd--alt" open data-anbieter="o2"
         style="--anb:#0019a5">
  <summary>
    <span class="gr-bnd-an"><span class="gr-bnd-name">o2</span>
      <span class="gr-kk-marke gr-kk-marke--alt">kein aktueller Stand seit
        15.09.2026</span></span>
    <span class="gr-bnd-tarif">O2 Mobile L Plus mit 150 GB+ (24 Mon.)</span>
    <span class="gr-bnd-tco">1.794,76 €
      <em class="gr-bnd-label">Kosten über 24 Monate</em></span>
    <span class="gr-bnd-delta">–</span>
    <span class="gr-bnd-bar">1.315,00 €</span>
    <span class="gr-bnd-chev" aria-hidden="true"></span>
  </summary>
</details>
</div>
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
           f"<body style='margin:0;width:390px'>{_BUNDLE_KOPF}</body>"
           f"</html>")
    (tmp_path / "index.html").write_text(html, encoding="utf-8")
    css_pfad = pathlib.Path(gz.__file__).parent / "templates" / "style.css"
    css = in_stylesheet(css_pfad.read_text(encoding="utf-8"))
    (tmp_path / "style.css").write_text(css, encoding="utf-8")
    return tmp_path


def test_das_abzeichen_bleibt_ein_zusammenhaengender_rahmen(tmp_path):
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
            rechtecke = page.eval_on_selector(
                ".gr-kk-marke--alt", "e => e.getClientRects().length")
            anzeige = page.eval_on_selector(
                ".gr-kk-marke--alt", "e => getComputedStyle(e).display")
        finally:
            browser.close()
    assert anzeige == "inline-block", anzeige
    # EIN Rechteck, auch wenn der Text selbst innerhalb der Box mehrzeilig
    # umbricht (inline-block zeichnet den Rahmen einmal UM den ganzen
    # Inhalt) - "inline" zeichnet bei mehrzeiligem Text einen Rahmen JE
    # ZEILE (der gemeldete "Stapel Einzelkaestchen").
    assert rechtecke == 1, (
        f"das Abzeichen zerfaellt in {rechtecke} Rahmen-Rechtecke statt "
        "eines zusammenhaengenden")
