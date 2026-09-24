"""E2: die Zeitreihen-Hauptansicht im echten Chromium - Falz, Suche,
Band-Wahl, Deep-Link, Konsole. Dieselbe Bauform wie
`tests/test_geraete_o1_hauptgraph_browser.py` (eigener Server auf
127.0.0.1, kein file://, Chromium an beiden bekannten Orten).

Abnahmekriterien des E2-Auftrags als Messung:
  - 390x844: Antwort-Satz UND Graphkopf (Messtag-Zeile) oberhalb der Falz,
    kein Querscroll (scrollWidth <= 390).
  - Null JavaScript-Konsolenfehler.
  - Suchfeld: Live-Vorschau ab 2 Zeichen, hoechstens 8 Treffer, klickbar
    vor vollstaendiger Eingabe (Antonios Beispiel: "iphone 17").
  - Band-Wahl und Deep-Link ?modell=&band= wechseln den Graphen - ohne
    dass der Client eine Zahl rechnet (alle Werte kommen fertig).
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
# Die Falz auf dem Telefon (Kriterium 11c, hier an der Fixture)
# --------------------------------------------------------------------------

def test_am_telefon_steht_die_antwort_ueber_der_falz(telefon):
    s, _ = telefon
    box = s.evaluate("""() => {
      const a = document.querySelector('#tafel-tco .gr-zr-antwort');
      const m = document.querySelector('#tafel-tco .gr-zr-messtage');
      return {antwort: a ? Math.round(a.getBoundingClientRect().bottom) : null,
              kopf: m ? Math.round(m.getBoundingClientRect().bottom) : null,
              quer: Math.max(document.documentElement.scrollWidth,
                             document.body.scrollWidth)};
    }""")
    assert box["antwort"] is not None, "der Antwort-Satz fehlt"
    assert box["antwort"] <= 844, f"Antwort-Satz endet bei {box['antwort']} px"
    assert box["kopf"] is not None and box["kopf"] <= 844, \
        f"der Graphkopf endet bei {box['kopf']} px"
    assert box["quer"] <= 391, f"Seite {box['quer']} px breit"


def test_am_telefon_beginnt_die_kurve_oberhalb_der_falz(telefon):
    """P4b (Re-Check 18.09.2026): 11c misst Antwort-Satz und GraphKOPF -
    die KURVE selbst begann auf 390x844 bei 921 px, 77 px unter der Falz,
    weil die Legende (drei Zeilen, 74 px) zwischen Kopf und Bild stand.
    Seither steht die Legende mobil UNTER dem Bild, und die Kette ueber
    dem Bild ist gestrafft. Gemessen wird nicht der Kopf, sondern das
    SVG selbst UND der oberste Kurvenpunkt (min ueber Punkte, Halos und
    Linien) - mindestens 1 px Kurve muessen im ersten Viewport stehen,
    sonst oeffnet der Reiter mit Geruest statt Antwort. Am echten Bestand
    nach dem Fix: SVG-Top 813, Punkt 843 (Falz 844)."""
    s, _ = telefon
    mess = s.evaluate("""() => {
      const svg = document.querySelector(
        '#gr-zr-gruppe svg.gr-zr--schmal') ||
        document.querySelector('#gr-zr-gruppe svg');
      if (!svg) return null;
      const top = sel => {
        const e = [...svg.querySelectorAll(sel)];
        return e.length ? Math.min(
          ...e.map(x => Math.round(x.getBoundingClientRect().top))) : null;
      };
      return {svg: Math.round(svg.getBoundingClientRect().top),
              punkt: top('circle.gr-zr-punkt'),
              halo: top('circle.gr-zr-halo'),
              linie: top('path'),
              legendeUnten: (() => {
                const l = document.querySelector('#gr-zr-gruppe .gr-zr-legende');
                return l ? Math.round(l.getBoundingClientRect().top)
                         > Math.round(svg.getBoundingClientRect().bottom)
                         : null; })()};
    }""")
    assert mess, "die Zeitreihe zeichnet kein SVG (Fixture prüfen)"
    assert mess["svg"] <= 844, (
        f"das SVG beginnt bei {mess['svg']} px - {mess['svg'] - 844} px "
        "unter der Falz 844")
    kurve = min(p for p in (mess["punkt"], mess["halo"], mess["linie"])
                if p is not None) if any(
        p is not None for p in (mess["punkt"], mess["halo"], mess["linie"])) \
        else None
    assert kurve is not None and kurve <= 844, (
        f"der oberste Kurvenpunkt liegt bei {kurve} px - die Kurve steht "
        "komplett unter der Falz 844, der Reiter öffnet mit Gerüst")


def test_die_kachelzeile_drueckt_die_falz_nicht_unter_844(telefon):
    """§3.2 + P1/F3: die Karten sind kein Chip-Streifen mehr, aber 11c
    geht weiter vor - die Kartenreihe bleibt im ersten Viewport und
    drueckt weder sich selbst noch den Antwort-Satz unter die Falz."""
    s, _ = telefon
    box = s.evaluate("""() => {
      const k = document.querySelector('#tafel-tco .gr-zr-kacheln');
      return {karten: k ? Math.round(k.getBoundingClientRect().bottom) : null,
              hoehe: k ? Math.round(k.getBoundingClientRect().height) : 0};
    }""")
    assert box["karten"] is not None, "die Kartenreihe fehlt"
    assert box["karten"] <= 844, \
        f"Kartenreihe endet bei {box['karten']} px (Falz 844)"


def test_die_karten_preiszahl_ist_mindestens_20px(schreibtisch, telefon):
    """P1/F3-Messlatte der Abnahme: die Preiszahl je Karte steht in
    MINDESTENS 20 px - auf dem Schreibtisch UND auf dem Telefon (per
    Playwright gezaehlt, nicht behauptet)."""
    for s, _ in (schreibtisch, telefon):
        groessen = s.evaluate(
            """() => [...document.querySelectorAll(
                 '#gr-zr-kacheln .gr-zr-k-preis b')]
               .map(b => parseFloat(getComputedStyle(b).fontSize))""")
        assert groessen, "keine Karte mit Preiszahl gefunden"
        assert min(groessen) >= 20, \
            f"kleinste Preiszahl {min(groessen)} px (< 20)"


def test_alle_karten_im_ersten_viewport_beim_schreibtisch(schreibtisch):
    """P1/F3-Messlatte: alle sechs Karten stehen IM ERSTEN Viewport
    (1440x900) - der Schnelleingang ist kein Scroll-Fund."""
    s, _ = schreibtisch
    erg = s.evaluate("""() => {
      const knoepfe = [...document.querySelectorAll(
        '#gr-zr-kacheln button[data-modell]')];
      return {n: knoepfe.length,
              unten: Math.max(...knoepfe.map(
                k => Math.round(k.getBoundingClientRect().bottom))),
              rechts: Math.max(...knoepfe.map(
                k => Math.round(k.getBoundingClientRect().right)))};
    }""")
    assert 1 <= erg["n"] <= 6
    assert erg["unten"] <= 900, \
        f"Karten enden bei {erg['unten']} px (Falz 900)"
    assert erg["rechts"] <= 1440


def test_die_aktive_karte_ist_deutlich_markiert(schreibtisch):
    """P1/F3-Messlatte: die gewaehlte Karte hebt sich DEUTLICH ab - Rahmen
    mindestens 2 px PLUS eine andere Flaeche als die inaktiven."""
    s, _ = schreibtisch
    karten = s.evaluate("""() => [...document.querySelectorAll(
        '#gr-zr-kacheln button[data-modell]')].map(b => {
      const st = getComputedStyle(b);
      return {aktiv: b.getAttribute('aria-pressed') === 'true',
              rand: parseFloat(st.borderWidth),
              flaeche: st.backgroundColor};
    })""")
    aktive = [k for k in karten if k["aktiv"]]
    inaktive = [k for k in karten if not k["aktiv"]]
    assert aktive, "keine Karte als aktiv markiert (aria-pressed)"
    assert inaktive, "alle Karten markiert - die Messung prueft nichts"
    assert aktive[0]["rand"] >= 2, \
        f"aktive Karte hat {aktive[0]['rand']} px Rahmen (< 2)"
    assert aktive[0]["flaeche"] != inaktive[0]["flaeche"], \
        "aktive Karte hat dieselbe Flaeche wie eine inaktive"


# --------------------------------------------------------------------------
# Konsole
# --------------------------------------------------------------------------

def test_keine_javascript_fehler_auf_der_startansicht(schreibtisch):
    s, fehler = schreibtisch
    assert fehler == [], f"Konsolenfehler: {fehler[:3]}"


# --------------------------------------------------------------------------
# Das Suchfeld - Antonios Beispiel
# --------------------------------------------------------------------------

def test_die_vorschau_kommt_ab_zwei_zeichen_und_bleibt_klein(schreibtisch):
    s, _ = schreibtisch
    feld = s.query_selector("#gr-zr-suche")
    feld.fill("i")
    s.wait_for_timeout(120)
    assert s.query_selector_all("#gr-zr-vorschau button") == []
    feld.fill("iphone 17")
    s.wait_for_timeout(200)
    treffer = s.query_selector_all("#gr-zr-vorschau button")
    assert 1 <= len(treffer) <= 8
    text = treffer[0].inner_text()
    assert "iPhone 17 Pro" in text and "GB" in text


def test_der_vorschau_treffer_ist_vor_vollstaendiger_eingabe_klickbar(
        schreibtisch):
    s, _ = schreibtisch
    vorher = s.eval_on_selector("#tafel-tco .gr-zr-antwort",
                                "e => e.textContent")
    s.fill("#gr-zr-suche", "iph")
    s.wait_for_timeout(150)
    s.click("#gr-zr-vorschau button")
    s.wait_for_timeout(400)
    nachher = s.eval_on_selector("#tafel-tco .gr-zr-antwort",
                                 "e => e.textContent")
    assert vorher != nachher or "iPhone 17 Pro" in nachher
    assert "iPhone 17 Pro" in nachher


def test_auftippen_und_schreiben_ersetzt_die_vorbelegung(schreibtisch):
    """E2-F2: das Suchfeld traegt den Titel des Startgeraets als
    Vorbelegung. Antonios Weg - Feld antippen, „pixel 11" schreiben - muss
    beim ERSTEN Versuch die Vorschau liefern. Vor dem Fix stand der Cursor
    am Ende: Tippen haengte an („Apple iPhone 17 Pro 256 GBpixel 11"),
    die Vorschau meldete „kein Treffer"."""
    s, _ = schreibtisch
    s.click("#gr-zr-suche")
    value, von, bis = s.eval_on_selector(
        "#gr-zr-suche",
        "e => [e.value, e.selectionStart, e.selectionEnd]")
    assert von == 0 and bis == len(value), \
        f"Fokus markiert nicht die Vorbelegung: [{von},{bis}] von {len(value)}"
    s.type("#gr-zr-suche", "galaxy")
    s.wait_for_timeout(200)
    value = s.eval_on_selector("#gr-zr-suche", "e => e.value")
    assert value == "galaxy", f"Tippen hat nicht ersetzt: {value!r}"
    treffer = s.eval_on_selector("#gr-zr-treffer", "e => e.textContent")
    assert "kein Treffer" not in treffer, \
        "die ersetzte Eingabe findet nichts - der erste Versuch scheitert"


def test_die_unveraenderte_vorbelegung_oeffnet_die_vorschau_nicht(telefon):
    """E2-F3 (Mitgift): Fokus allein darf die Liste nicht oeffnen - ihre
    Treffer waeren das aktuelle Geraet allein, und auf dem Telefon
    verdeckt sie die Band-Knoepfe, bevor ueberhaupt getippt wurde."""
    s, _ = telefon
    s.click("#gr-zr-suche")
    s.wait_for_timeout(250)
    assert s.query_selector_all("#gr-zr-vorschau button") == []


def test_nach_der_auswahl_ist_die_vorschau_zu(telefon):
    """E2-F3: auf dem Telefon blieb die Trefferliste nach dem Antippen
    offen (191 px) und verdeckte Klein/Mittel/Groß komplett - der
    Band-Klick schlug 60-mal am Overlay fehl. Eine Wahl schließt die
    Liste, auf jedem Geraet gleich."""
    s, _ = telefon
    s.fill("#gr-zr-suche", "iph")
    s.wait_for_timeout(200)
    assert s.query_selector_all("#gr-zr-vorschau button"), \
        "die Vorschau oeffnet nicht - der Test misst seinen eigenen Vorweg"
    s.tap("#gr-zr-vorschau button")
    s.wait_for_timeout(500)
    hoehe = s.eval_on_selector("#gr-zr-vorschau",
                               "e => Math.round(e.getBoundingClientRect()"
                               ".height)")
    assert hoehe == 0, f"die Vorschau steht offen ({hoehe} px) nach Auswahl"
    # Der Band-Knopfe muss ohne Umweg treffbar sein: der Klick wartet
    # kurze Zeit - ein Overlay davor waere der Timeout.
    s.tap("#gr-zr-baender button[data-band='mittel']", timeout=4000)
    s.wait_for_timeout(500)
    antwort = s.eval_on_selector("#tafel-tco .gr-zr-antwort",
                                 "e => e.textContent")
    assert "Mittel" in antwort


def test_ausstapschliesst_die_vorschau(telefon):
    """Der Tap daneben ist der intuitve Weg, eine offene Liste zu schliessen
    - er darf nicht vom blur-Timing abhaengen (E2-F3)."""
    s, _ = telefon
    s.fill("#gr-zr-suche", "iph")
    s.wait_for_timeout(200)
    assert s.query_selector_all("#gr-zr-vorschau button")
    s.tap(".gr-zr-antwort")
    s.wait_for_timeout(250)
    hoehe = s.eval_on_selector("#gr-zr-vorschau",
                               "e => Math.round(e.getBoundingClientRect()"
                               ".height)")
    assert hoehe == 0, "Tap daneben laesst die Vorschau offen"


def test_die_kachel_waehlt_das_geraet(schreibtisch):
    s, _ = schreibtisch
    s.click("#gr-zr-kacheln button")
    s.wait_for_timeout(400)
    assert "iPhone 17 Pro" in s.eval_on_selector(
        "#tafel-tco .gr-zr-antwort", "e => e.textContent")


# --------------------------------------------------------------------------
# Band-Wahl und Deep-Link
# --------------------------------------------------------------------------

def test_der_bandwechsel_liefert_den_graphen_des_bandes(schreibtisch):
    s, _ = schreibtisch
    vor = s.eval_on_selector_all("#tafel-tco svg.gr-zr circle.gr-zr-punkt",
                                 "es => es.map(e => e.getAttribute('cx'))")
    s.click("#gr-zr-baender button[data-band='mittel']")
    s.wait_for_timeout(400)
    nach = s.eval_on_selector_all("#tafel-tco svg.gr-zr circle.gr-zr-punkt",
                                  "es => es.map(e => e.getAttribute('cx'))")
    antwort = s.eval_on_selector("#tafel-tco .gr-zr-antwort",
                                 "e => e.textContent")
    assert "Mittel" in antwort
    assert len(nach) < len(vor) or vor != nach


def test_der_deep_link_setzt_modell_und_band(_browser_seite):
    browser, basis = _browser_seite
    s = browser.new_page(viewport={"width": 1440, "height": 900})
    try:
        s.goto(f"{basis}/geraete.html?modell=samsung-galaxy-s26-256"
               f"&band=klein", wait_until="load")
        s.wait_for_timeout(450)
        antwort = s.eval_on_selector("#tafel-tco .gr-zr-antwort",
                                     "e => e.textContent")
        assert "Galaxy S26" in antwort and "Klein" in antwort
        url = s.url
        assert "modell=samsung-galaxy-s26-256" in url
    finally:
        s.close()


def test_der_modellwechsel_holt_den_graphen_aus_dem_fragment(schreibtisch):
    """Alle NICHT-Startzustaende kommen aus dem lazy Fragment - der
    Server-Block bleibt auf das Startpaar beschränkt (O1-Größenregel)."""
    s, _ = schreibtisch
    s.fill("#gr-zr-suche", "galaxy")
    s.wait_for_timeout(200)
    s.click("#gr-zr-vorschau button")
    s.wait_for_timeout(450)
    antwort = s.eval_on_selector("#tafel-tco .gr-zr-antwort",
                                 "e => e.textContent")
    assert "Galaxy S26" in antwort
    assert s.query_selector("#tafel-tco svg.gr-zr circle.gr-zr-punkt")


# Die Bündel-Tabelle unter dem Graph - Titel und Zeilen meinen dasselbe Band
# (Wahrheitstest zur QA-Zurückweisung E2-F1, 17.09.2026)
# --------------------------------------------------------------------------

def test_der_bandtitel_und_die_sichtbaren_zeilen_meinen_dasselbe_band(
        schreibtisch):
    """E2-F1 wurde mit dieser Messung ZURÜCKGEWIESEN: der QA las `innerText`
    über ALLE .gr-bnd-Zeilen (auch die per `hidden` versteckten - innerText
    fällt auf display:none-Elemente auf textContent zurück) und zählte
    DOM-Reihenfolge statt Sichtbarkeit. Gemessen mit offsetParent: im
    Band-Zustand sind genau die Zeilen sichtbar, deren data-band dem
    gewählten Band entspricht - plus die eigenüberschriebene Gruppe
    „Ohne Tarifband" (§7: unbegrenzte Tarife stehen bewusst UNTER dem
    Bandblock, nicht heimlich in einem Band). Dieser Test nagelt die
    Zusicherung fest, damit der Filter nicht still entfallen kann."""
    s, _ = schreibtisch
    s.click("#gr-zr-baender button[data-band='mittel']")
    s.wait_for_timeout(500)
    titel = s.eval_on_selector("#gr-bnd-titel", "e => e.textContent")
    assert "Band Mittel" in titel
    zeilen = s.evaluate("""() => Array.from(
      document.querySelectorAll('#gr-bnd-gruppe .gr-bnd')).map(z => ({
        band: z.getAttribute('data-band'),
        sichtbar: !!(z.offsetParent || z.getClientRects().length),
        ohneband: !!z.closest('.gr-ohneband')}))""")
    assert zeilen, "keine Bündel-Zeilen im DOM"
    sichtbar = [z for z in zeilen if z["sichtbar"]]
    assert sichtbar, "im Band-Zustand ist keine Zeile sichtbar"
    # JEDE sichtbare Zeile MIT data-band gehört zum gewählten Band - der
    # Titel „Alle Bündel im Band Mittel" darf nichts anderes überstehen
    # haben. Zeilen OHNE data-band sind die §7-Gruppe „Ohne Tarifband".
    for z in sichtbar:
        if z["ohneband"]:
            assert z["band"] is None, \
                "eine Band-Zeile steht in der Ohne-Band-Gruppe"
        else:
            assert z["band"] == "mittel", \
                f"sichtbare Zeile mit data-band={z['band']!r} unter " \
                f"dem Titel 'Band Mittel'"
    # und umgekehrt: jede Zeile eines ANDEREN Bands ist wirklich weg
    for z in zeilen:
        if z["band"] not in (None, "mittel"):
            assert not z["sichtbar"], \
                f"Zeile data-band={z['band']!r} ist sichtbar geblieben"


# --------------------------------------------------------------------------
# --------------------------------------------------------------------------
# Die Schrift im Graphen
# --------------------------------------------------------------------------

def test_keine_schrift_unter_zwoelf_pixel_im_sichtbaren_graphen(
        schreibtisch):
    """Die 12-px-Regel der Seite gilt den LESSENDEN Labels (Werte, Namen,
    Achsen, Ticks). Die Meta-Etiketten des genehmigten Prototyps (kleiner
    Erst-Wert, "unser Angebot"-Chip, Abrufdatum am Linienende) stehen
    bewusst bei 10-11 px - sie wiederholen bzw. stützen, sie tragen keine
    einzige Information allein."""
    s, _ = schreibtisch
    befund = s.evaluate("""() => {
      const svg = [...document.querySelectorAll('#tafel-tco svg.gr-zr')]
        .find(e => e.getBoundingClientRect().width > 0);
      if (!svg) return null;
      const pflicht = '.gr-zr-wert:not(.gr-zr-wert--erst), .gr-zr-name, ' +
                      '.gr-zr-achse, .gr-zr-xtick';
      const neben = '.gr-zr-wert--erst, .gr-zr-chip, .gr-zr-datum';
      const px = (sel) => [...svg.querySelectorAll(sel)].map(t => ({
        text: t.textContent.trim().slice(0, 16),
        px: parseFloat(window.getComputedStyle(t).fontSize)})
      ).filter(t => t.text);
      return {pflicht: px(pflicht).filter(t => t.px < 12),
              neben: px(neben).filter(t => t.px < 10)};
    }""")
    assert befund is not None, "kein sichtbares SVG"
    assert befund["pflicht"] == [], f"Lesende Schrift unter 12 px: {befund['pflicht'][:4]}"
    assert befund["neben"] == [], f"Meta-Etikett unter 10 px: {befund['neben'][:4]}"


# --------------------------------------------------------------------------
# Wahl-Helfer fuer die uebrigen Geraete-Browsertests (E2): der alte
# Modell-<select> ist weg - Modellwahl ueber das Suchfeld (Enter waehlt den
# ersten Treffer; Titel sind eindeutig), Bandwahl ueber die Knoepfe. Beide
# Wege sind die echten Bedienelemente der Seite, keine Testklopfer.
# --------------------------------------------------------------------------

def waehle_modell(s, mid: str) -> None:
    titel = s.eval_on_selector(
        "#gr-zeitreihe-daten",
        "k => JSON.parse(k.textContent).titel[" + json.dumps(mid) + "]")
    assert titel, f"Modell {mid} kennt der Knoten nicht"
    s.fill("#gr-zr-suche", "")
    s.type("#gr-zr-suche", titel)
    s.press("#gr-zr-suche", "Enter")
    s.wait_for_timeout(500)


def waehle_band(s, band: str) -> None:
    s.click(f"#gr-zr-baender button[data-band='{band}']")
    s.wait_for_timeout(500)


# --------------------------------------------------------------------------
# P2/D2: Endlabels statt Legende - auf breit ersetzen die Namen am
# Linienende die HTML-Legende ganz (dieselbe Aussage nicht zweimal); auf
# schmal bleibt sie stehen, sie traegt dort die "ab/zuletzt"-Werte, die
# das schmale Bild selbst nicht zeigt.
# --------------------------------------------------------------------------

def test_die_legende_weicht_den_endlabels_auf_dem_schreibtisch(schreibtisch):
    s, _ = schreibtisch
    anzeige = s.eval_on_selector(
        "#tafel-tco .gr-zr-legende",
        "el => getComputedStyle(el).display")
    assert anzeige == "none", f"Legende zeigt sich trotz Endlabels: {anzeige}"
    # Die Endlabels selbst stehen im SVG - die Aussage bleibt sichtbar,
    # nur nicht zweimal.
    namen = s.eval_on_selector_all(
        "#tafel-tco svg.gr-zr--breit text.gr-zr-name",
        "els => els.length")
    assert namen and namen > 0


def test_die_legende_bleibt_auf_dem_telefon(telefon):
    s, _ = telefon
    anzeige = s.eval_on_selector(
        "#tafel-tco .gr-zr-legende",
        "el => getComputedStyle(el).display")
    assert anzeige != "none", "Legende fehlt mobil - dort traegt sie ab/zuletzt"


# P2/D4b: der aktive Navigationseintrag ("Geräte") steht auf dem Telefon
# beim Laden im Bild - vorher stand er bei x=536-620 komplett ausserhalb
# des 390-px-Viewports, und "Differenzierung" davor war 20 px abgeschnitten.
# Diese kleine Test-Fixture rendert den Eintrag "Geräte" selbst NICHT (die
# `geraete_verlinkt`-Sichtbarkeitsschwelle greift nicht), deshalb steht die
# Messung dafuer eigenstaendig in `test_navigation_aktiver_eintrag_browser.
# py` - hier nur der Scroll-Hinweis der Reiterleiste dieser Seite selbst.

def test_die_reiterleiste_braucht_keinen_scroll_mehr(telefon):
    """QA-Fix 24.09.2026: die Leiste ROLLTE bis zu diesem Fix in sich
    (`test_kein_reitertext_wird_abgeschnitten` hielt fest, dass das am
    390-px-Telefon den letzten Reiter abschnitt statt ihn scrollbar zu
    machen). Mit nur noch vier Reitern bricht sie stattdessen um
    (`flex-wrap:wrap`, Basisregel) - sie braucht darum keinen Scroll-
    Hinweis mehr, weil sie gar nicht mehr innerlich scrollt: ihre
    scrollWidth darf ihre clientWidth nicht mehr uebersteigen."""
    s, _ = telefon
    breiten = s.eval_on_selector(
        "#tafel-tco .gr-reiter, .gr-reiter",
        "e => ({sw: e.scrollWidth, cw: e.clientWidth})")
    assert breiten["sw"] <= breiten["cw"] + 1, (
        f"die Reiterleiste rollt noch innerlich: scrollWidth {breiten['sw']} "
        f"> clientWidth {breiten['cw']}")


# --------------------------------------------------------------------------
# C4 (QA-Fix 24.09.2026): DAS ENDLABEL RAGT NICHT AUS DEM SVG. Mobil (390 px)
# lief "UNSER ANGEBOT" (und jedes andere Endlabel) rechts aus dem SVG-
# Rechteck - der Fix (`geraete_zeitreihe._svg`) haengt jedes Endlabel
# rechtsbuendig an einem FESTEN X (`ENDLABEL_RAND` vom rechten Bildrand),
# statt am Linienende zu beginnen und mit der Textbreite nach rechts zu
# wachsen: die rechte Kante bleibt im SVG, unabhaengig von der Glyphenbreite.
# --------------------------------------------------------------------------

_ENDLABEL_SEL = ('.gr-zr-name, .gr-zr-chip, .gr-zr-datum, .gr-zr-mon')


def _endlabel_lage(s):
    """{svg, labels: [{text, links, rechts}]} des SICHTBAREN SVG - misst nur
    das Bild, das die aktuelle Bildschirmbreite per Mediaquery zeigt
    (`display:none` nimmt das andere aus dem Layout, `getBoundingClientRect`
    liefert dafuer ein Nullrechteck)."""
    return s.evaluate("""() => {
      const svg = [...document.querySelectorAll('#tafel-tco svg.gr-zr')]
        .find(e => e.getBoundingClientRect().width > 0);
      if (!svg) return null;
      const sr = svg.getBoundingClientRect();
      const labels = [...svg.querySelectorAll('""" + _ENDLABEL_SEL + """')]
        .map(e => {
          const r = e.getBoundingClientRect();
          return { text: e.textContent, links: r.left, rechts: r.right };
        });
      return { svgLinks: sr.left, svgRechts: sr.right, labels };
    }""")


def test_jedes_endlabel_liegt_vollstaendig_im_svg(schreibtisch, telefon):
    """C4: jedes Endlabel-Rechteck liegt GANZ im SVG-Rechteck - gemessen mit
    `getBoundingClientRect()`, nicht am Quelltext. Auf 1440 UND 390 px."""
    for s, _ in (schreibtisch, telefon):
        lage = _endlabel_lage(s)
        assert lage, "kein sichtbares SVG mit Endlabels gefunden"
        assert lage["labels"], "keine Endlabels im sichtbaren SVG gefunden"
        for l in lage["labels"]:
            assert l["links"] >= lage["svgLinks"] - 0.5, (
                f"Endlabel {l['text']!r} beginnt links vor dem SVG: {l} "
                f"gegen SVG-links {lage['svgLinks']}")
            assert l["rechts"] <= lage["svgRechts"] + 0.5, (
                f"Endlabel {l['text']!r} ragt rechts aus dem SVG: {l} "
                f"gegen SVG-rechts {lage['svgRechts']}")


def test_endlabel_bleibt_im_svg_auch_bei_verbreitertem_text(telefon):
    """Google Fonts laden in der Sandbox nicht (CLAUDE.md-Fallstrick) - die
    Rueckfallschrift kann schmaler sein als die echte. Mit kuenstlich
    vergroessertem `letter-spacing` auf den Endlabel-Klassen (eigenschafts-
    basiert, keine Pixelzahl behauptet) bleibt die rechte Kante trotzdem im
    SVG, weil `text-anchor='end'` an einem FESTEN X verankert ist - der
    Text waechst nach LINKS, unabhaengig von der Glyphenbreite."""
    s, _ = telefon
    s.evaluate("""() => {
      const style = document.createElement('style');
      style.textContent = '.gr-zr-name, .gr-zr-chip, .gr-zr-datum, ' +
        '.gr-zr-mon { letter-spacing: 6px !important; }';
      document.head.appendChild(style);
    }""")
    lage = _endlabel_lage(s)
    assert lage and lage["labels"], "kein sichtbares SVG mit Endlabels"
    for l in lage["labels"]:
        assert l["rechts"] <= lage["svgRechts"] + 0.5, (
            f"Endlabel {l['text']!r} ragt bei verbreitertem Text rechts "
            f"aus dem SVG: {l} gegen SVG-rechts {lage['svgRechts']}")


# --------------------------------------------------------------------------
# C5 (QA-Fix 24.09.2026): KEIN REITER WIRD ABGESCHNITTEN. Mobil (390 px) war
# "GERÄTEKATALOG" als "GERÄTEKATAL" zu sehen. `.gr-reiter button` ist
# `flex:0 0 auto` mit `white-space:nowrap` (style.css) - jeder Reiter ist so
# breit wie sein Text, die Leiste selbst rollt (`overflow-x:auto`), statt den
# Text zu kappen. Gemessen im echten Chromium, nicht am Quelltext.
# --------------------------------------------------------------------------

def test_kein_reitertext_wird_abgeschnitten(telefon):
    """QA-Fix 24.09.2026: die alte Fassung mass `scrollWidth` gegen
    `clientWidth` DES KNOPFS - das haelt nur fest, dass der TEXT nicht im
    Knopf selbst umbricht, nicht, dass der Knopf in die Leiste passt. Am
    390-px-Telefon gemessen reichte "Gerätekatalog" bis x=393, die Leiste
    endete bei x=362 - der alte Test blieb gruen, weil scrollWidth ==
    clientWidth am Knopf selbst war (der Text brach nicht, der KNOPF lief
    nur aus der Leiste). Gemessen wird jetzt die Geometrie: jedes
    Reiterknopf-Rechteck muss vollstaendig im sichtbaren Rechteck der
    Leiste liegen, ohne dass gescrollt wird."""
    s, _ = telefon
    daten = s.evaluate("""() => {
      const leiste = document.querySelector('.gr-reiter');
      const lr = leiste.getBoundingClientRect();
      return {
        leiste: { left: lr.left, right: lr.right },
        knoepfe: [...leiste.querySelectorAll('button')].map(b => {
          const r = b.getBoundingClientRect();
          return { text: b.textContent.trim(), left: r.left, right: r.right };
        }),
      };
    }""")
    assert daten["knoepfe"], "keine Reiter gefunden"
    for k in daten["knoepfe"]:
        assert k["left"] >= daten["leiste"]["left"] - 1, (
            f"Reiter {k['text']!r} beginnt links ausserhalb der Leiste: "
            f"{k['left']} < {daten['leiste']['left']}")
        assert k["right"] <= daten["leiste"]["right"] + 1, (
            f"Reiter {k['text']!r} ist abgeschnitten: rechte Kante "
            f"{k['right']} > Leiste {daten['leiste']['right']}")


def test_die_reiterleiste_verursacht_keinen_seitenweiten_querscroll(telefon):
    s, _ = telefon
    breite = s.evaluate("() => Math.max(document.documentElement.scrollWidth,"
                        " document.body.scrollWidth)")
    assert breite <= 391, f"die Seite ist {breite} px breit (Telefon 390 px)"
