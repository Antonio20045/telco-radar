"""Wie lang ist die Geraeteseite? Gemessen, nicht geschaetzt.

Der Befund der Evaluation vom 29.08.2026 war eine Zahl: **18412 px**,
290 Tabellenzeilen, 65 Aufklapper. Die Vergleichstabelle hatte 62 Zeilen,
davon 36 mit dem Inhalt "niemand guenstiger" - zwei Bildschirme, die nichts
sagen. Ein Manager, der wissen will "wo sind wir teurer", scrollte durch
zwanzig Bildschirme, um sechs relevante Zeilen zu finden.

Genau das laesst sich im HTML nicht sehen: ob eine Seite sechs oder zwanzig
Bildschirme lang ist, entscheiden Schriftgroessen, Zeilenumbrueche,
Rasterumbrueche und - vor allem - welche Aufklapper zugeklappt sind. Ein
`<details>` steht im HTML in voller Laenge und auf der Seite in einer Zeile.
Dieser Test misst deshalb an einem echten Chromium.

Er ist die Gegenprobe zu jeder kuenftigen Sektion. Wer eine ergaenzt, sieht
hier, was sie kostet.
"""
from __future__ import annotations

import contextlib
import functools
import glob
import http.server
import shutil
import socket
import threading
from pathlib import Path

import pytest

from telco_radar.config import load_config
from telco_radar.report.html import render_site

REPO = Path(__file__).resolve().parents[1]

# Das Mass aus dem Auftrag: "Seitenhöhe unter 6 Bildschirmen auf 1440 px".
# 900 px ist die Fensterhoehe, mit der auch `scripts/pruefe_portal.py` und
# `tests/test_falz_browser.py` messen.
BREITE, BILDSCHIRM = 1440, 900
MAX_BILDSCHIRME = 6


def _chromium() -> str | None:
    """Zwei Orte, weil es zwei Maschinen gibt - dieselbe Rechnung wie in
    `tests/test_falz_browser.py`. Nur den Sandbox-Pfad zu kennen hiesse,
    dass dieser Test auf der Maschine schweigt, die Merges absichert."""
    for muster in ("/opt/pw-browsers/chromium-*/chrome-linux/chrome",
                   str(Path.home() / ".cache/ms-playwright"
                       / "chromium*/chrome-linux*/chrome")):
        treffer = sorted(glob.glob(muster))
        if treffer:
            return treffer[-1]
    return None


@contextlib.contextmanager
def _server(site: Path):
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
def _gemessen(tmp_path_factory):
    sync_playwright = pytest.importorskip(
        "playwright.sync_api",
        reason="playwright fehlt - Browser-Messung entfaellt").sync_playwright

    tmp_path = tmp_path_factory.mktemp("geraetehoehe")
    reports = tmp_path / "data" / "reports"
    reports.mkdir(parents=True)
    vorhanden = sorted((REPO / "data" / "reports").glob("*.json"))
    if not vorhanden:
        pytest.skip("kein Bericht im Archiv")
    for endung in (".json", ".md"):
        auch = vorhanden[-1].with_suffix(endung)
        if auch.exists():
            shutil.copy(auch, reports / auch.name)
    (tmp_path / "data" / "state").symlink_to(REPO / "data" / "state")
    site = tmp_path / "site"
    # MIT cfg - ohne den dritten Parameter rendert `render_site` eine
    # stillschweigend halbe Seite (CLAUDE.md §6), und der Test maesse eine
    # Hoehe, die es nicht gibt.
    render_site(site, reports, load_config(REPO))
    if not (site / "geraete.html").exists():
        pytest.skip("geraete.html wurde nicht gebaut")

    pfad = _chromium()
    with _server(site) as wurzel, sync_playwright() as p:
        try:
            browser = p.chromium.launch(
                **({"executable_path": pfad} if pfad else {}))
        except Exception as exc:                       # noqa: BLE001
            pytest.skip(f"Chromium startet nicht: {exc}")
        seite = browser.new_page(viewport={"width": BREITE,
                                           "height": BILDSCHIRM})
        seite.goto(f"{wurzel}/geraete.html")
        seite.wait_for_timeout(1200)
        werte = {
            "hoehe": seite.evaluate("document.body.scrollHeight"),
            # Bei einem Durchfaller soll die Meldung sagen, WO die Hoehe
            # steckt. Ein rotes "5600 statt 5400" allein zwingt die naechste
            # Sitzung, die Messung von Hand zu wiederholen.
            "abschnitte": seite.evaluate(
                """() => [...document.querySelectorAll('section')]
                     .map(s => [s.className,
                                Math.round(s.getBoundingClientRect().height)])
                     .filter(r => r[1] > 100)
                     .sort((a, b) => b[1] - a[1]).slice(0, 6)"""),
            "aufklapper_offen": seite.evaluate(
                "document.querySelectorAll('details[open]').length"),
            "waagerecht": seite.evaluate(
                "document.documentElement.scrollWidth > "
                "document.documentElement.clientWidth"),
        }
        browser.close()
    return werte


def test_die_seite_ist_kuerzer_als_sechs_bildschirme(_gemessen):
    bildschirme = _gemessen["hoehe"] / BILDSCHIRM
    abschnitte = ", ".join(f"{k or '?'} {h} px"
                           for k, h in _gemessen["abschnitte"])
    assert bildschirme < MAX_BILDSCHIRME, (
        f"{_gemessen['hoehe']} px = {bildschirme:.1f} Bildschirme "
        f"(am 29.08.2026: 18412 px = 20,5). Die größten Abschnitte: "
        f"{abschnitte}. Wächst die Vergleichstabelle, ist "
        f"`geraete_vergleich.UEBERSICHT_MAX_ZEILEN` die Stellschraube.")


def test_kein_aufklapper_steht_offen(_gemessen):
    """Die Kuerze haengt daran, dass die Aufklapper ZU sind. Ein
    versehentliches `open` macht die Seite wieder zwanzig Bildschirme lang,
    ohne dass sich eine Zeile Inhalt aendert."""
    assert _gemessen["aufklapper_offen"] == 0


def test_die_seite_rollt_nicht_waagerecht(_gemessen):
    assert not _gemessen["waagerecht"]
