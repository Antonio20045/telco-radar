"""P1/A2 (STRATEGIE_GERAETE_V3, 17.09.2026): das Klick-Panel fuer den
Rechenweg EINER Messung - im echten Chromium.

Abnahme des P1-Auftrags 2 als Messung (design.md Regel 6): Klick auf den
KURVENPUNKT (unsichtbare Trefferflaeche .gr-zr-hit, r=12, ueber dem
gezeichneten Kreis) UND auf die PREISZAHL im Antwort-Satz oeffnet EIN
Panel unter dem Graph mit den Werten GENAU dieser Messung - als gesetzte
Rechung („24 × 19,00 € = 456,00 €", das ×-Muster). Das Panel montiert das
serverseitige <template> (A1) per content.cloneNode; im JS wird keine
Zahl zusammengesetzt (0 Operator-Regel).

Die Pruefung „GENAU dieser Messung" vergleicht den Panel-Inhalt mit dem
<template> derselben (data-anb, data-m)-Kombination im selben Block -
zwei Darstellungen EINER Quelle, keine zweite Zahlenquelle im Test.
Dass der Vergleich etwas beweist, sichert ein Woechter: die Serie des
geklickten Anbieters traegt mindestens ZWEI Messtage (o2: drei), sonst
waere „genau diese" auch mit dem falschen Template erfuellt.

Bauform wie test_geraete_zeitreihe_browser.py (eigener Server auf
127.0.0.1, kein file://, Chromium an allen drei bekannten Orten).
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
    root, _ = _baue(tmp_path)
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
    site = _baue_site(tmp_path_factory.mktemp("zrpanel"))
    exe = _chromium()
    with _server(site) as basis, sync_playwright() as p:
        browser = (p.chromium.launch(executable_path=exe) if exe
                   else p.chromium.launch())
        yield browser, basis
        browser.close()


@contextlib.contextmanager
def _ansicht(_browser_seite, breite=1440, hoehe=900, touch=False):
    browser, basis = _browser_seite
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


# Ein UEBERLAPPUNGSFREIER Kurvenpunkt: benachbarte Trefferflaechen (r=12)
# koennen sich ueberdecken, wenn zwei Anbieter am selben Tag wenige Pixel
# auseinander liegen - dann gewinnt der Browser den obersten Kreis. Der
# Test klickt nur auf Flaechen, deren Mitte wirklich zum eigenen Kreis
# gehoert (document.elementFromPoint), sonst messte er einen anderen als
# den erwaehnten.
_FREIER_PUNKT = """(anb) => {
  const frei = [];
  document.querySelectorAll('circle.gr-zr-hit[data-m]').forEach(c => {
    if (anb && c.getAttribute('data-anb') !== anb) return;
    const b = c.getBoundingClientRect();
    if (!b.width) return;
    const el = document.elementFromPoint(b.x + b.width/2, b.y + b.height/2);
    if (el === c) {
      frei.push({anb: c.getAttribute('data-anb'), m: c.getAttribute('data-m'),
                 x: b.x + b.width/2, y: b.y + b.height/2});
    }
  });
  return frei;
}"""

_PANEL_EQ_TEMPLATE = """(z) => {
  const t = document.querySelector(
    ".gr-zr-rechnungen template[data-anb='" + z.anb + "'][data-m='" + z.m + "']");
  const panel = document.getElementById('gr-zr-panel');
  const inhalt = panel && panel.querySelector('.gr-zr-rech');
  if (!t || !inhalt) return 'FEHLT';
  const norm = e => e.textContent.replace(/\\s+/g, ' ').trim();
  return norm(t.content.querySelector('.gr-zr-rech')) === norm(inhalt);
}"""


def _freier_punkt(seite, anb=None):
    """Der juengste UEBERLAPPUNGSFREIE Kurvenpunkt einer Serie.

    Zwei Schritte, beide noetig: erst den letzten Kreis der Serie (in der
    Fixture steht der Graph weit unter der Falz) in den Blick scrollen -
    elementFromPoint liefert fuer Punkte ausserhalb des Viewports null -
    und DANN messen, ob die Kreismitte wirklich dem eigenen Kreis gehoert.
    Das Scrollen laeuft nativ per scrollIntoView: Playwrights eigenes
    scroll_into_view_if_needed unterstuetzt SVG-Kindkreise nicht.
    """
    adresse = "circle.gr-zr-hit[data-m]" + (
        f"[data-anb='{anb}']" if anb else "")
    # Der LETZTE Kreis im DOM gehoert zum (per CSS versteckten) schmalen
    # SVG - scrollIntoView auf ein unsichtbares Element wirkt nicht. Ziel
    # ist der letzte KREIS MIT Flaeche, also der sichtbaren Variante.
    seite.eval_on_selector_all(
        adresse,
        "els => { const da = els.filter("
        "e => e.getBoundingClientRect().width);"
        "if (da.length) da[da.length - 1].scrollIntoView({block:'center'}); }")
    seite.wait_for_timeout(200)
    aus = seite.evaluate(_FREIER_PUNKT, anb)
    return aus[-1] if aus else None


def _panel_offen(seite) -> bool:
    return not seite.eval_on_selector("#gr-zr-panel", "e => e.hidden")


def _kopf(seite) -> str:
    return seite.inner_text("#gr-zr-panel .gr-zr-rkopf").strip()


def test_klick_auf_den_punkt_oeffnet_das_panel_dieser_messung(schreibtisch):
    seite, _fehler = schreibtisch
    # Waechter: die o2-Serie hat MEHRERE Messtage (Fixture: drei) - nur dann
    # ist 'genau diese Messung' eine echte Unterscheidung.
    tage = seite.eval_on_selector_all(
        ".gr-zr-rechnungen template[data-anb='o2']",
        "els => els.map(e => e.getAttribute('data-m'))")
    assert len(set(tage)) >= 2
    ziel = _freier_punkt(seite, "o2")
    assert ziel, "kein ueberlappungsfreier o2-Punkt im Startgraphen"
    seite.mouse.click(ziel["x"], ziel["y"])
    seite.wait_for_timeout(300)

    assert _panel_offen(seite)
    assert ziel["anb"] in _kopf(seite)
    # Die Werte GENAU dieser Messung: der Panel-Inhalt ist der Klon des
    # Templates derselben (Anbieter, Messtag)-Kombination.
    assert seite.evaluate(_PANEL_EQ_TEMPLATE, ziel) is True
    # Das ×-Muster der gesetzten Rechung (design.md Regel 6) - mindestens
    # ein Posten traegt "ANZAHL × BETRAG".
    posten = seite.eval_on_selector_all(
        "#gr-zr-panel li.gr-zr-posten .gr-zr-pr",
        "els => els.map(e => e.textContent)")
    assert any("×" in p for p in posten), posten
    assert seite.inner_text("#gr-zr-panel .gr-zr-rsumme").strip()


def test_der_aktive_punkt_ist_in_beiden_svg_markiert(schreibtisch):
    seite, _fehler = schreibtisch
    ziel = _freier_punkt(seite, "o2")
    assert ziel
    seite.mouse.click(ziel["x"], ziel["y"])
    seite.wait_for_timeout(250)
    aktiv = seite.eval_on_selector_all(
        "circle.gr-zr-punkt.gr-zr-aktiv",
        "els => els.map(e => [e.getAttribute('data-anb'), "
        "e.getAttribute('data-m'), "
        "getComputedStyle(e).strokeWidth])")
    # BEIDE SVG-Varianten (breit + schmal; eine ist per CSS versteckt)
    # tragen die Markierung - sonst verschwaende sie beim Umklappen.
    assert aktiv == [[ziel["anb"], ziel["m"], "2.8px"],
                     [ziel["anb"], ziel["m"], "2.8px"]], aktiv


def test_klick_auf_die_preiszahl_oeffnet_den_rechenweg_des_anbieters(
        schreibtisch):
    seite, _fehler = schreibtisch
    satz = seite.inner_text("#gr-zr-antwort")
    # Waechter: der Satz nennt den Guenstigsten im festen Wortlaut, an dem
    # die Anbietererkennung haengt (drei Formen aus _antwort_html).
    assert "1&1 am günstigsten:" in satz, satz
    seite.locator("#gr-zr-antwort b.gr-zr-zahl").first.click()
    seite.wait_for_timeout(300)

    assert _panel_offen(seite)
    assert "1&1" in _kopf(seite)
    # Die Preiszahl nennt den Stand von HEUTE - es gibt kein Template zu
    # "heute"; geoeffnet wird der LETZTE Messtag der Serie. 1&1 hat in der
    # Fixture genau einen (2026-09-12), damit ist "letzter" hier hart
    # geprueft und nicht Verhandlungssache der Reihenfolge.
    erwartet = {"anb": "1&1", "m": "2026-09-12"}
    assert seite.evaluate(_PANEL_EQ_TEMPLATE, erwartet) is True
    assert "12. September 2026" in _kopf(seite)


def test_derselbe_klick_schliesst_ein_anderer_wechselt(schreibtisch):
    seite, _fehler = schreibtisch
    # Oeffnen per Preiszahl (deterministisch, unabhaengig vom Scroll).
    seite.locator("#gr-zr-antwort b.gr-zr-zahl").first.click()
    seite.wait_for_timeout(250)
    assert _panel_offen(seite)
    seite.locator("#gr-zr-antwort b.gr-zr-zahl").first.click()
    seite.wait_for_timeout(200)
    assert not _panel_offen(seite)

    # Wechsel: Panel per Preiszahl auf, dann einen ANDEREN Anbieter-Punkt
    # klicken - die Messung wechselt, das Panel bleibt offen.
    seite.locator("#gr-zr-antwort b.gr-zr-zahl").first.click()
    seite.wait_for_timeout(250)
    vorher = _kopf(seite)
    ziel = _freier_punkt(seite, "Vodafone")
    assert ziel, "kein ueberlappungsfreier Vodafone-Punkt"
    seite.mouse.click(ziel["x"], ziel["y"])
    seite.wait_for_timeout(300)
    assert _panel_offen(seite)
    assert _kopf(seite) != vorher
    assert ziel["anb"] in _kopf(seite)
    assert seite.evaluate(_PANEL_EQ_TEMPLATE, ziel) is True


def test_der_schliessen_knopf_und_die_tastatur_oeffnen_und_schliessen(
        schreibtisch):
    seite, _fehler = schreibtisch
    ziel = _freier_punkt(seite, "o2")
    assert ziel
    # Tastatur: Fokus auf die Trefferflaeche, Enter oeffnet (der Kreis
    # traegt role=button und tabindex aus app.js).
    seite.evaluate(
        "(z) => document.querySelector("
        "\"circle.gr-zr-hit[data-anb='\" + z.anb + \"'][data-m='\" + z.m"
        "+ \"']\").focus()", ziel)
    seite.keyboard.press("Enter")
    seite.wait_for_timeout(250)
    assert _panel_offen(seite)
    assert ziel["anb"] in _kopf(seite)
    # Der ×-Knopf des Panels schliesst (Delegation - er entsteht mit jedem
    # Rechenweg neu).
    seite.locator("#gr-zr-panel .gr-zr-zu").click()
    seite.wait_for_timeout(200)
    assert not _panel_offen(seite)


def test_der_modellwechsel_schliesst_das_panel(schreibtisch):
    seite, _fehler = schreibtisch
    seite.locator("#gr-zr-antwort b.gr-zr-zahl").first.click()
    seite.wait_for_timeout(250)
    assert _panel_offen(seite)
    # Bandwechsel laedt einen anderen Graphen - das Panel der ALTEN Messung
    # darf nicht unter dem neuen stehen bleiben.
    seite.locator("#gr-zr-baender button[data-band='mittel']").click()
    seite.wait_for_timeout(500)
    assert not _panel_offen(seite)


def test_mobil_390_panel_ohne_querscroll(telefon):
    seite, fehler = telefon
    ziel = _freier_punkt(seite, None)
    assert ziel, "kein antippbarer Punkt im schmalen Graphen"
    seite.touchscreen.tap(ziel["x"], ziel["y"])
    seite.wait_for_timeout(350)

    assert _panel_offen(seite)
    assert ziel["anb"] in _kopf(seite)
    assert seite.evaluate(_PANEL_EQ_TEMPLATE, ziel) is True
    breite = seite.evaluate("document.documentElement.scrollWidth")
    assert breite <= 390, breite
    assert not fehler, fehler


def test_keine_konsolenfehler_bei_den_klicks(schreibtisch):
    seite, fehler = schreibtisch
    ziel = _freier_punkt(seite, None)
    assert ziel
    seite.mouse.click(ziel["x"], ziel["y"])
    seite.wait_for_timeout(250)
    seite.locator("#gr-zr-antwort b.gr-zr-zahl").first.click()
    seite.wait_for_timeout(250)
    seite.locator("#gr-zr-panel .gr-zr-zu").click()
    seite.wait_for_timeout(150)
    assert not fehler, fehler


# --------------------------------------------------------------------------
# P1-Fix (17.09.2026): die Auflagen der Sicht-Pruefung - Karten-Preis als
# dritter Eingang (A1), bandgekoppelte Karten (B2), Leer-Hinweis statt
# Vodafone-Naherung fuer FREMDE Messungen (Code-S3-2), 12-px-Regel im
# geoeffneten Panel (Code-S3-1).
# --------------------------------------------------------------------------

def test_klick_auf_den_karten_preis_oeffnet_den_rechenweg(schreibtisch):
    """Sicht-A1: Antonios Geste ist „wenn man auf den Preis drueckt" - die
    Karten-Preiszahl ist der dritte Eingang des Panels. Der Klick auf den
    Preis der AKTIVEN Karte oeffnet den Rechenweg des Anbieters, den der
    Server am Band-Koerper nennt (data-anb), am LETZTEN Messtag."""
    seite, _fehler = schreibtisch
    karte = seite.locator(
        "#gr-zr-kacheln button[aria-pressed='true']").first
    span = karte.locator(".gr-zr-k-band[data-anb] .gr-zr-k-preis")
    assert span.count() >= 1
    anb = karte.locator(".gr-zr-k-band[data-anb]:not([hidden])") \
        .get_attribute("data-anb")
    span.first.click()
    seite.wait_for_timeout(300)

    assert _panel_offen(seite)
    assert anb in _kopf(seite)
    tage = seite.eval_on_selector_all(
        f".gr-zr-rechnungen template[data-anb='{anb}']",
        "els => els.map(e => e.getAttribute('data-m')).sort()")
    letzte = tage[-1]
    assert seite.evaluate(
        _PANEL_EQ_TEMPLATE, {"anb": anb, "m": letzte}) is True


def test_klick_auf_den_preis_einer_fremden_karte_waehlt_und_oeffnet(
        schreibtisch):
    """Sicht-A1, Wunsch-Pfad: der Preis einer NICHT aktiven Karte bestellt
    Modell UND Band und oeffnet nach dem Laden den Rechenweg dieses
    Anbieters - der Klick ist nie wirkungslos, aber nie eine fremde
    Messung. (Die Karte wird ueber data-modell adressiert: ein Live-
    Locator `:not([aria-pressed='true'])` zeigt nach dem Klick auf die
    ANDERE Karte - der Umschlag selbst wäre die Messung.)"""
    seite, _fehler = schreibtisch
    fremd = seite.locator(
        "#gr-zr-kacheln button:not([aria-pressed='true'])").first
    mid = fremd.get_attribute("data-modell")
    anb = fremd.locator(".gr-zr-k-band[data-anb]:not([hidden])") \
        .get_attribute("data-anb")
    band = fremd.locator(".gr-zr-k-band[data-anb]:not([hidden])") \
        .get_attribute("data-band")
    fremd.locator(".gr-zr-k-preis").first.click()
    seite.wait_for_timeout(700)

    dauerhaft = seite.locator(
        f"#gr-zr-kacheln button[data-modell='{mid}']")
    assert dauerhaft.get_attribute("aria-pressed") == "true", \
        "der Preis-Klick einer fremden Karte waehlt das Modell"
    assert _panel_offen(seite)
    assert anb in _kopf(seite)
    # das Paar ist gewechselt: die URL nennt Modell und Band des Klicks
    url = seite.evaluate("location.search")
    assert "band=" + band in url


def test_der_bandwechsel_stellt_auch_die_karten_um(schreibtisch):
    """Sicht-B2: bis zum Fix zeigten die Karten in jedem Band denselben
    bandunabhaengigen Preis - der Umschalter wirkte auf die prominenteste
    Ebene nicht. Jetzt traegt jede Karte JE Band ihre Werte, der Wechsel
    blendet um; eine Karte ohne dieses Band zeigt den benannten
    Leerzustand „—" statt leer zu stehen."""
    seite, _fehler = schreibtisch

    def _sichtbarer_preis(karte):
        return karte.locator(".gr-zr-k-band:not([hidden]) .gr-zr-k-preis"
                             ).first.inner_text()

    aktiv = seite.locator(
        "#gr-zr-kacheln button[aria-pressed='true']").first
    vorher = _sichtbarer_preis(aktiv)
    seite.locator("#gr-zr-baender button[data-band='mittel']").click()
    seite.wait_for_timeout(600)
    nachher = _sichtbarer_preis(aktiv)
    assert vorher != nachher, \
        f"die Karte zeigt nach dem Bandwechsel denselben Preis ({vorher})"
    # Die Bandlage der Karte ist die gewaehlte
    band = aktiv.locator(".gr-zr-k-band:not([hidden])").first
    assert band.get_attribute("data-band") == "mittel"


def test_fremder_punkt_ohne_vorlage_bekommt_den_leerhinweis(schreibtisch):
    """Code-S3-2: bis zum Fix fiel ein o2-Punkt ohne Vorlage (Buendel
    unlesbar) auf die „Vodafone · Referenzrechnung" - eine falsche
    Antwort auf „rechne MIR DIESE Messung vor". Fehlerinjektion im DOM:
    alle o2-Vorlagen entfernen, dann einen o2-Punkt klicken - es kommt
    der ehrliche Leer-Hinweis, nie die Naehrung eines Fremdanbieters."""
    seite, _fehler = schreibtisch
    seite.eval_on_selector_all(
        ".gr-zr-rechnungen template[data-anb='o2']",
        "els => els.forEach(e => e.remove())")
    ziel = _freier_punkt(seite, "o2")
    assert ziel, "kein ueberlappungsfreier o2-Punkt"
    seite.mouse.click(ziel["x"], ziel["y"])
    seite.wait_for_timeout(300)

    assert _panel_offen(seite)
    text = seite.eval_on_selector("#gr-zr-panel", "e => e.innerText")
    assert "kein Rechenweg bereit" in text
    assert "Referenzrechnung" not in text, \
        "fremde Messung fiel auf die Vodafone-Näherung (S3-2)"


def test_im_geoeffneten_panel_gibt_es_keine_schrift_unter_zwoelf_pixel(
        schreibtisch):
    """Code-S3-1: die 12-px-Regel gilt auch dem Panel - seine Texte
    entstehen erst nach dem Klick aus dem <template> (DocumentFragment),
    deshalb sahen die statischen Messungen die 11-px-Klassen nie. Hier
    wird das Panel WIRKLICH geoeffnet und im Dokument gemessen."""
    seite, _fehler = schreibtisch
    seite.locator("#gr-zr-antwort b.gr-zr-zahl").first.click()
    seite.wait_for_timeout(300)
    zu_klein = seite.evaluate("""() => Array.from(
      document.querySelectorAll('#gr-zr-panel *')).filter(el =>
        el.textContent.trim()
        && el.children.length === 0
        && parseFloat(getComputedStyle(el).fontSize) < 12
      ).map(el => el.className + ': ' + el.textContent.trim().slice(0, 30))""")
    assert zu_klein == [], f"Panel-Schrift unter 12 px: {zu_klein}"
