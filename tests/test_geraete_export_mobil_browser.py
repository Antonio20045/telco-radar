"""E5 (AUFTRAG_GERAETE_EINE_SEITE_V2 §7): die Export-Stelle auf dem
Telefon - sichtbar, benutzbar, und die Falz bleibt, wo sie ist.

Bis E5 war die Knopfreihe unter 900 px WEGGEBLENDET (O4: der Platz über
der Falz ging vor, "der CSV-Download ist ein Excel-Workflow des
Schreibtischs"). E5 dreht das auf dieselbe Stelle um, an der sie auch auf
dem Schreibtisch steht - die Strategie (§7 E5): "Export-Knöpfe mobil neu
bewerten (Auftrag: 'der Export ist Antonios Werkzeug')". Der Platz dafür
kommt aus der Kopfzeile selbst: das Datum rückt neben den Kicker
(Zeitungs-Datumszeile), die Export-Reihe übernimmt den Slot.

Gemessen im echten Chromium (dieselbe Bauform wie
test_geraete_zeitreihe_browser.py):
  - 390x844: alle vier Knöpfe sichtbar (Box > 0) und in EINER Zeile,
    die IN SICH rollt (overflow-x:auto), nie die Seite quer.
  - Die Falz-Kriterien von 11c bleiben erfüllt - die Sichtbarkeit darf
    nicht durch Falz-Bruch erkauft sein (deshalb steht die Messung hier
    ein zweites Mal, gekoppelt an die Reihe).
  - Der Kicker bricht nicht um: der Kopf ist auf dem Telefon eine
    SPALTE (Kicker, Schlagzeile, Datum, Export-Zeile) - die Regel, die
    den Platz für die Reihe freigibt.
"""
from __future__ import annotations

import contextlib
import functools
import glob
import http.server
import pathlib
import socket
import threading

import pytest

from telco_radar.report.html import render_site

from test_geraete_zeitreihe_ansicht import HEUTE, _baue

import json


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
    site = _baue_site(tmp_path_factory.mktemp("exmobil"))
    exe = _chromium()
    with _server(site) as basis, sync_playwright() as p:
        browser = (p.chromium.launch(executable_path=exe) if exe
                   else p.chromium.launch())
        yield browser, basis, site
        browser.close()


@contextlib.contextmanager
def _ansicht(_browser_seite, breite, hoehe):
    browser, basis, _ = _browser_seite
    context = browser.new_context(viewport={"width": breite, "height": hoehe})
    s = context.new_page()
    s.goto(f"{basis}/geraete.html", wait_until="load")
    s.wait_for_timeout(250)
    try:
        yield s
    finally:
        context.close()


@pytest.fixture
def telefon(_browser_seite):
    with _ansicht(_browser_seite, 390, 844) as s:
        yield s


@pytest.fixture
def schreibtisch(_browser_seite):
    with _ansicht(_browser_seite, 1440, 900) as s:
        yield s


def _reihe(s):
    return s.evaluate("""() => {
      const ex = document.querySelector('.page-hero-row .gr-export-knoepfe');
      if (!ex) return null;
      const knoepfe = [...ex.querySelectorAll('a')];
      const st = getComputedStyle(ex);
      return {
        hoehe: Math.round(ex.getBoundingClientRect().height),
        // Eine Zeile: alle Knöpfe starten auf derselben Oberkante
        zeile: knoepfe.every(k =>
          Math.abs(k.getBoundingClientRect().top -
                   knoepfe[0].getBoundingClientRect().top) < 1),
        sichtbar: knoepfe.filter(k => {
          const r = k.getBoundingClientRect();
          return r.height > 0 && r.width > 0;}).length,
        knoepfe: knoepfe.length,
        links: knoepfe.map(k => k.getAttribute('href')),
        overflow: st.overflowX,
        scroll: ex.scrollWidth, client: ex.clientWidth,
        quer: Math.max(document.documentElement.scrollWidth,
                       document.body.scrollWidth),
        antwort: (() => {
          const a = document.querySelector('#tafel-tco .gr-zr-antwort');
          return a ? Math.round(a.getBoundingClientRect().bottom) : null;})(),
        kopf: (() => {
          const k = document.querySelector('#tafel-tco .gr-zr-messtage');
          return k ? Math.round(k.getBoundingClientRect().bottom) : null;})(),
      };
    }""")


def test_am_telefon_ist_die_export_zeile_sichtbar_und_vollstaendig(telefon):
    """Alle Export-Dateien sind vom Telefon aus erreichbar - die Reihe
    steht da (Hoehe > 0), jeder Knopf hat eine Box, und alle liegen in
    EINER Zeile (die Reihe rollt in sich, sie stapelt nicht). Bis P3
    waren es vier Knöpfe, der Modell-Katalog hat zwei weitere gebracht
    (eine Datei je Ansicht - E5-Regel)."""
    r = _reihe(telefon)
    assert r is not None, "keine Export-Reihe im Kopf der Seite"
    assert r["hoehe"] > 0, "die Export-Reihe ist auf 390 px unsichtbar"
    assert r["sichtbar"] == r["knoepfe"] == 6, (r["sichtbar"], r["knoepfe"])
    assert r["zeile"], "die Knöpfe stapeln statt in einer Zeile zu rollen"
    assert r["overflow"] == "auto", (
        f"overflow-x ist {r['overflow']} - die Reihe kann nicht in sich "
        "rollen, der vierte Knopf wäre unerreichbar oder drückt die Seite "
        "quer")


def test_am_telefon_rollt_die_seite_nicht_quer(telefon):
    r = _reihe(telefon)
    assert r is not None
    assert r["quer"] <= 391, (
        f"Seite {r['quer']} px breit - die Knopfreihe drückt das Dokument "
        "in die Waagerechte statt selbst zu rollen")
    assert r["scroll"] > r["client"] or r["scroll"] == r["client"], (
        "scrollWidth kleiner als clientWidth - da stimmt die Messung nicht")


def test_am_telefon_bleibt_die_falz_von_11c_erfuellt(telefon):
    """Die Sichtbarkeit der Reihe ist an die Falz GEKOPPELT: Antwort-Satz
    und Graphkopf bleiben über 844 px. Ohne diese Messung könnte jemand
    die Reihe sichtbar machen, indem er 11c bricht - genau der Tausch,
    den O4 seinerzeit mit dem Wegblenden beantwortet hat."""
    r = _reihe(telefon)
    assert r is not None
    assert r["antwort"] is not None and r["antwort"] <= 844, (
        f"Antwort-Satz endet bei {r['antwort']} px")
    assert r["kopf"] is not None and r["kopf"] <= 844, (
        f"Graphkopf endet bei {r['kopf']} px")


def test_der_kicker_bricht_auf_dem_telefon_nicht_um(telefon):
    """Die Regel, die den Platz freigibt: auf dem Telefon ist der Kopf
    eine SPALTE (Kicker, Schlagzeile, Datum, Export-Zeile), und der
    Kicker bleibt EINZEILIG. Ein Nebeneinander von Kicker und Datum ist
    bei 390 px ausgeschlossen (Kicker 163 px + Datum 214 px gegen 334 px
    Zeilenbreite) - die erste Fassung dieser Änderung brach den Kicker
    mitten im Wort um, gefunden am Screenshot, nicht am Messwert."""
    box = telefon.evaluate("""() => {
      const k = document.querySelector('.gr-hero-export .page-kicker');
      const d = document.querySelector('.gr-hero-export .page-date');
      if (!k || !d) return null;
      return {kh: Math.round(k.getBoundingClientRect().height),
              lh: Math.round(parseFloat(getComputedStyle(k).lineHeight)),
              drechts: Math.round(
                d.getBoundingClientRect().right),
              breite: Math.round(
                document.querySelector('.gr-hero-export').clientWidth)};
    }""")
    assert box is not None, "Kopf ohne Kicker oder Datum - Messung ins Leere"
    assert box["kh"] <= box["lh"] + 2, (
        f"der Kicker ist {box['kh']} px hoch bei {box['lh']} px Zeilenhöhe "
        "- er bricht um")
    # Das Datum endet rechtsbündig an derselben Kante wie der Kopf
    # (Grid-Spalte, justify-self:end) - es steht UNTER der Schlagzeile,
    # nicht mehr am Flex-Grund neben dem Text-Block.
    assert box["breite"] - box["drechts"] <= 2, (
        f"Datumszeile endet {box['breite'] - box['drechts']} px vor der "
        "rechten Kopf-Kante")


def test_die_vier_links_zielen_auf_vier_dateien(_browser_seite):
    """Jeder Knopf zeigt auf eine Datei, die der Render WIRKLICH
    geschrieben hat - ein Link auf eine fehlende Datei ist ein Download,
    der im Browser in einem 404 endet."""
    _, _, site = _browser_seite
    for name in ("geraete-aktuell.csv", "geraete-historie.csv",
                 "geraete-tco.csv", "wettbewerbsradar.csv"):
        assert (site / "exporte" / name).exists(), (
            f"exporte/{name} fehlt im gerenderten site/-Verzeichnis")


def test_am_schreibtisch_steht_die_reihe_noch_im_kopf(schreibtisch):
    """Der Desktop ist unangetastet: die Reihe steht im Hero, alle vier
    Knöpfe sichtbar - das mobile Grid greift erst unter 900 px."""
    r = _reihe(schreibtisch)
    assert r is not None
    assert r["sichtbar"] == 6
    assert r["zeile"], "auch auf dem Schreibtisch stehen die Knöpfe versetzt"
