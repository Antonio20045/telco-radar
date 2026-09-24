"""E5 (AUFTRAG_GERAETE_EINE_SEITE_V2 §7) / P4-D4 (STRATEGIE_GERAETE_V3,
18.09.2026): die Export-Stelle auf dem Telefon - sichtbar, benutzbar,
und die Falz bleibt, wo sie ist.

Bis P4/D4 stand die Knopfreihe in der KOPFZEILE (O4 zentral, E5 mobil
sichtbar): am Telefon belegte sie dort die Zeile ÜBER der Reiter-
Steuerung und drückte Antwort-Satz und Graphkopf Richtung Falz (11c,
gemessen 837 von 844 px). P4/D4 verschiebt sie als EINE Fußzeile ans
Seitenende (.gr-export-fuss) - dieselben sechs Dateien (P3 hat die
beiden Katalog-Ansichten dazu gebracht), dieselben Ziele, EINE Stelle
für alle Reiter bleibt gewahrt (O4-Regel gegen Reiter-Duplikate).

Gemessen im echten Chromium (dieselbe Bauform wie
test_geraete_zeitreihe_browser.py):
  - 390x844: alle sechs Knöpfe sichtbar (Box > 0) und in EINER Zeile,
    die IN SICH rollt (overflow-x:auto), nie die Seite quer.
  - Die Falz-Kriterien von 11c bleiben erfüllt - der Kopf ist ohne die
    Reihe KÜRZER geworden und die neue LEITZAHL des Vergleichs-Reiters
    (.gr-zr-leit, DIE ANTWORT IST DIE GROESSTE ZAHL) darf die gewonnene
    Luft nicht wieder verbrauchen.
  - Der Kicker bricht nicht um: der Kopf ist auf dem Telefon eine
    SPALTE (Kicker, Schlagzeile, Datum).
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


def _oeffne_export(s):
    """P2/D4b: die sechs Knöpfe stehen seit diesem Paket hinter EINEM
    "Export ▾"-Aufklapper (`<details class="gr-export-menu">`) - wer die
    Zeile misst, muss sie erst öffnen."""
    s.click(".gr-export-fuss .gr-export-oeffner")
    s.wait_for_timeout(100)


def _reihe(s):
    return s.evaluate("""() => {
      const ex = document.querySelector('.gr-export-fuss .gr-export-knoepfe');
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


def test_am_telefon_ist_das_export_menue_zugeklappt_ein_knopf(telefon):
    """P2/D4b: SECHS Knöpfe standen bis hierhin immer offen in einer Zeile
    - jetzt steht am Fuß GENAU EIN Knopf ("Export ▾"), die sechs Ziele
    stehen dahinter. Ohne Klick ist die Reihe (`.gr-export-knoepfe`)
    unsichtbar (Höhe 0) - der Öffner selbst hat eine Box."""
    zustand = telefon.evaluate("""() => {
      const menu = document.querySelector('.gr-export-fuss .gr-export-menu');
      const oeffner = document.querySelector(
        '.gr-export-fuss .gr-export-oeffner');
      const knoepfe = document.querySelector(
        '.gr-export-fuss .gr-export-knoepfe');
      return {
        offen: menu ? menu.hasAttribute('open') : null,
        oeffnerBox: oeffner ? Math.round(
          oeffner.getBoundingClientRect().height) : 0,
        knoepfeBox: knoepfe ? Math.round(
          knoepfe.getBoundingClientRect().height) : null,
        sichtbareKnoepfeAusserhalb: document.querySelectorAll(
          '.gr-hero-export a[href^="exporte/"], '
          + '.gr-werkzeug a[href^="exporte/"]').length,
      };
    }""")
    assert zustand["offen"] is False, "das Export-Menü ist ungefragt offen"
    assert zustand["oeffnerBox"] > 0, "der 'Export ▾'-Knopf ist unsichtbar"
    assert zustand["knoepfeBox"] == 0, (
        f"die sechs Ziele stehen schon vor dem Klick im Bild "
        f"({zustand['knoepfeBox']} px hoch)")
    assert zustand["sichtbareKnoepfeAusserhalb"] == 0


def test_am_telefon_ist_die_export_zeile_nach_dem_oeffnen_vollstaendig(
        telefon):
    """Alle Export-Dateien sind vom Telefon aus erreichbar, sobald das
    Menü offen ist - die Reihe steht da (Hoehe > 0), jeder Knopf hat eine
    Box, und alle liegen in EINER Zeile (die Reihe rollt in sich, sie
    stapelt nicht). Bis P3 waren es vier Knöpfe, der Modell-Katalog hat
    zwei weitere gebracht (eine Datei je Ansicht - E5-Regel)."""
    _oeffne_export(telefon)
    r = _reihe(telefon)
    assert r is not None, "keine Export-Reihe in der Fußzeile der Seite"
    assert r["hoehe"] > 0, "die Export-Reihe ist auf 390 px unsichtbar"
    assert r["sichtbar"] == r["knoepfe"] == 6, (r["sichtbar"], r["knoepfe"])
    assert r["zeile"], "die Knöpfe stapeln statt in einer Zeile zu rollen"
    assert r["overflow"] == "auto", (
        f"overflow-x ist {r['overflow']} - die Reihe kann nicht in sich "
        "rollen, der vierte Knopf wäre unerreichbar oder drückt die Seite "
        "quer")


def test_am_telefon_rollt_die_geoeffnete_seite_nicht_quer(telefon):
    _oeffne_export(telefon)
    r = _reihe(telefon)
    assert r is not None
    assert r["quer"] <= 391, (
        f"Seite {r['quer']} px breit - die Knopfreihe drückt das Dokument "
        "in die Waagerechte statt selbst zu rollen")
    assert r["scroll"] > r["client"] or r["scroll"] == r["client"], (
        "scrollWidth kleiner als clientWidth - da stimmt die Messung nicht")


def test_am_telefon_bleibt_die_falz_von_11c_erfuellt(telefon):
    """Die Fußzeile ist an die Falz GEKOPPELT: Antwort-Satz und Graphkopf
    bleiben über 844 px - gemessen im ZUGEKLAPPTEN Ausgangszustand (P2/
    D4b: die Fußzeile ist jetzt noch kürzer als zu P4/D4, ein einzelner
    "Export ▾"-Knopf statt einer offenen Sechserreihe. Die LEITZAHL des
    Vergleichs-Reiters (.gr-zr-leit, DIE ANTWORT IST DIE GROESSTE ZAHL)
    bleibt die groesste Zahl der Tafel, der Kopf bekommt keinen neuen
    Inhalt."""
    r = _reihe(telefon)
    assert r is not None, "keine Export-Reihe in der Fußzeile der Seite"
    assert r["antwort"] is not None and r["antwort"] <= 844, (
        f"Antwort-Satz endet bei {r['antwort']} px")
    assert r["kopf"] is not None and r["kopf"] <= 844, (
        f"Graphkopf endet bei {r['kopf']} px")


def test_der_kicker_bricht_auf_dem_telefon_nicht_um(telefon):
    """Die Regel, die den Kopf trägt: auf dem Telefon ist der Kopf eine
    SPALTE (Kicker, Schlagzeile, Datum - die Export-Zeile steht seit
    P4/D4 in der Fußzeile), und der Kicker bleibt EINZEILIG. Ein
    Nebeneinander von Kicker und Datum ist bei 390 px ausgeschlossen
    (Kicker 163 px + Datum 214 px gegen 334 px Zeilenbreite) - die erste
    Fassung dieser Änderung brach den Kicker mitten im Wort um, gefunden
    am Screenshot, nicht am Messwert."""
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


def test_am_schreibtisch_steht_die_reihe_nach_dem_oeffnen_in_der_fusszeile(
        schreibtisch):
    """Der Desktop verhält sich wie das Telefon: EIN "Export ▾"-Knopf am
    Fuß, nach dem Öffnen dieselben sechs Ziele in EINER Zeile. Bis P4/D4
    stand die Reihe im Hero, bis P2/D4b immer offen in der Fußzeile."""
    r = _reihe(schreibtisch)
    assert r is not None
    assert r["sichtbar"] == 0, "die Reihe steht schon vor dem Klick offen"
    _oeffne_export(schreibtisch)
    r = _reihe(schreibtisch)
    assert r["sichtbar"] == 6
    assert r["zeile"], "auch auf dem Schreibtisch stehen die Knöpfe versetzt"
