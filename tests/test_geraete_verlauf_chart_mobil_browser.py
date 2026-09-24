"""QA-Fix 24.09.2026: drei Befunde am CLIENT-Chart des Reiters
„Preisverlauf" (`app.js` `zeichne(g)`), alle am selben Gerät und
denselben Rohdaten gemessen wie der QA-Screenshot (iPhone 17 256 GB,
Reiter „Preisverlauf"):

  1. MOBIL (390 px) lief das SVG breiter als sein Container (`min-width`
     an `.gr-vsvg`) - sichtbar war nur der Anfang der Kurve, der letzte
     Messpunkt (24.9.) lag ausserhalb.
  2. Die X-Achsen-Labels "11.9." und "12.9." lagen uebereinander.
  3. Das Label "billigster Stand …" konnte eine Linie kreuzen und wirkte
     durchgestrichen.
  4. Der Satz unter dem Diagramm ("liegen 16 Messtermine vor, …")
     doppelte die Kachel "Messtermine".

Fixture: dieselben sechs Anbieter, Tage und Preise wie am realen
iPhone 17 256 GB (16 Messtermine, `data-verlaufdaten` am 24.09.2026
gemessen) - keine erfundenen Zahlen, damit der Test dieselbe
Ueberlappung trifft wie der QA-Screenshot."""
from __future__ import annotations

import contextlib
import json

import pytest
import yaml

from telco_radar.report import geraete_verlauf
from telco_radar.report.html import render_site

from test_geraete_browser_fixture import _chromium, _server

HEUTE = "2026-09-24"

_KATALOG = {"geraete": [
    {"hersteller": "Apple", "modell": "iPhone 17", "generation": 17,
     "marktstart": "2025-09-19", "speicher": [256], "segment": "premium"},
]}
_FARBEN = {"farben": {"schwarz": ["Schwarz"]}}
_QUELLEN = {"anbieter": [
    {"name": "Vodafone", "typ": "netzbetreiber", "rang": 1, "eigen": True,
     "methode": "ldjson", "basis_url": "https://www.vodafone.de",
     "einstiege": [{"url": "https://www.vodafone.de/handys"}]},
    {"name": "o2", "typ": "netzbetreiber", "rang": 2, "methode": "ldjson",
     "basis_url": "https://www.o2online.de",
     "einstiege": [{"url": "https://www.o2online.de/handys"}]},
]}

DEVICE = "apple-iphone-17"
SPEICHER = 256

# (anbieter, [(datum, preis), ...]) - identisch zu den 16 Messterminen des
# realen iPhone 17 256 GB (sechs Anbieter, zehn Termine je Reihe gemischt,
# 16 EINDEUTIGE Tage insgesamt - "16 Messtermine").
_REIHEN = [
    ("Vodafone", [("2026-08-29", 949.90), ("2026-09-12", 1099.90),
                  ("2026-09-24", 1099.90)]),
    ("Saturn", [("2026-09-05", 939.99), ("2026-09-13", 949.99),
                ("2026-09-14", 959.99), ("2026-09-15", 999.99),
                ("2026-09-16", 1089.00), ("2026-09-19", 1089.00),
                ("2026-09-20", 1089.00), ("2026-09-21", 1089.00),
                ("2026-09-23", 1089.00), ("2026-09-24", 1089.00)]),
    ("congstar", [("2026-09-03", 919.00), ("2026-09-21", 1081.00),
                  ("2026-09-24", 1081.00)]),
    ("mobilcom-debitel", [("2026-08-10", 949.00), ("2026-09-11", 1099.00),
                          ("2026-09-24", 1099.00)]),
    ("o2", [("2026-08-29", 1027.00), ("2026-09-17", 1171.00),
            ("2026-09-24", 1171.00)]),
    ("Telekom", [("2026-09-05", 948.60), ("2026-09-15", 1096.20)]),
]


def _sku(device_id, speicher):
    return f"{device_id}-{speicher}gb-schwarz"


def _listung(anbieter, preis):
    return {"id": f"{anbieter.lower()}--{_sku(DEVICE, SPEICHER)}",
            "sku_id": _sku(DEVICE, SPEICHER), "device_id": DEVICE,
            "anbieter": anbieter, "anbieter_typ": "netzbetreiber",
            "netz": anbieter, "speicher_gb": SPEICHER, "farbe_roh": "Schwarz",
            "farbe_normalisiert": "schwarz", "zustand": "neu",
            "first_seen": "2026-08-01", "last_verified": HEUTE,
            "status": "aktiv", "missed_checks": 0,
            "preis_ohne_vertrag": preis, "erstpreis": preis,
            "erstpreis_art": "ohne_vertrag", "erstpreis_am": "2026-08-01",
            "quelle_url": f"https://example.de/{anbieter.lower()}/{DEVICE}",
            "abgerufen_am": HEUTE, "verfuegbarkeit": "lieferbar",
            "confidence": "hoch", "einstiege": ["https://example.de/liste"]}


def _baue(tmp_path):
    root = tmp_path / "site_baum"
    (root / "config").mkdir(parents=True)
    for name, daten in (("geraete_katalog.yaml", _KATALOG),
                        ("farben.yaml", _FARBEN),
                        ("geraete_quellen.yaml", _QUELLEN)):
        (root / "config" / name).write_text(
            yaml.safe_dump(daten, allow_unicode=True, sort_keys=False),
            encoding="utf-8")
    state = root / "data" / "state"
    state.mkdir(parents=True)
    listungen = [_listung(a, punkte[-1][1]) for a, punkte in _REIHEN]
    (state / "geraete_db.json").write_text(json.dumps({
        "updated": HEUTE,
        "anbieter": {a: {"laeufe": 8, "funde_gesamt": len(p)}
                     for a, p in _REIHEN},
        "listungen": listungen}), encoding="utf-8")
    preiszeilen = []
    for anbieter, punkte in _REIHEN:
        listung_id = f"{anbieter.lower()}--{_sku(DEVICE, SPEICHER)}"
        for datum, preis in punkte:
            preiszeilen.append(json.dumps({
                "listung_id": listung_id, "datum": datum,
                "preis_ohne_vertrag": preis, "preisart": "ohne_vertrag",
                "quelle_url": "https://example.de/beleg"}))
    (state / "geraete_preise.jsonl").write_text(
        "\n".join(preiszeilen) + "\n", encoding="utf-8")
    # KEIN Bündel noetig - der Verlaufs-Reiter braucht nur Listungen und
    # Preishistorie; ein leeres TCO-Bündel haelt das Gatter der Tafel 1
    # (Vergleich) aus dem Weg, ohne diesen Test zu verkomplizieren.
    (state / "geraete_tco.json").write_text(json.dumps({
        "updated": HEUTE, "buendel": [], "sim_only": []}), encoding="utf-8")
    (state / "tarife.jsonl").write_text("", encoding="utf-8")
    reports = root / "data" / "reports"
    reports.mkdir(parents=True)
    (reports / f"{HEUTE}.json").write_text(json.dumps({
        "date": HEUTE, "language": "de",
        "briefing_md": "## Auf einen Blick\n\n- Nichts.\n",
        "stats": {}, "regions": []}), encoding="utf-8")
    (reports / f"{HEUTE}.md").write_text("# Bericht\n", encoding="utf-8")
    site = root / "site"
    render_site(site, reports)
    return site


@contextlib.contextmanager
def _browser_ctx(tmp_path_factory):
    sync_playwright = pytest.importorskip(
        "playwright.sync_api", reason="playwright fehlt").sync_playwright
    site = _baue(tmp_path_factory.mktemp("verlaufmobil"))
    exe = _chromium()
    with _server(site) as wurzel, sync_playwright() as p:
        browser = (p.chromium.launch(executable_path=exe) if exe
                   else p.chromium.launch())
        try:
            yield wurzel, browser
        finally:
            browser.close()


@pytest.fixture(scope="module")
def _wurzel_browser(tmp_path_factory):
    with _browser_ctx(tmp_path_factory) as paar:
        yield paar


def _oeffne(browser, wurzel, breite):
    """DER NUTZERWEG (Lead-Befund, 24.09.2026): Seite mit dem
    STANDARDREITER "Vergleich" laden, DANN auf "Preisverlauf" klicken,
    800 ms warten. KEIN Suchfeld-Umweg - die Auto-Vorauswahl zeichnet das
    erste Geraet der Liste beim Laden, WAEHREND der Reiter noch
    `.gr-tafel--aus` (`display:none`) ist. Der fruehere Test fuellte das
    Suchfeld NACH dem Tab-Klick und loeste damit einen ZWEITEN, sichtbaren
    Redraw aus - das verdeckte genau den Fehler, den dieser Weg zeigt."""
    ctx = browser.new_context(viewport={"width": breite, "height": 900})
    s = ctx.new_page()
    s.goto(f"{wurzel}/geraete.html", wait_until="networkidle")
    s.click('.gr-reiter [data-tafel="tafel-verlauf"]')
    s.wait_for_timeout(800)
    return s


@pytest.fixture(scope="module")
def seite(_wurzel_browser):
    wurzel, browser = _wurzel_browser
    yield _oeffne(browser, wurzel, 390)


def _messen(seite):
    return seite.evaluate("""() => {
      const svg = document.querySelector('#gr-vbild svg');
      const bild = document.querySelector('#gr-vbild');
      const sr = svg.getBoundingClientRect(), br = bild.getBoundingClientRect();
      const kreise = [...svg.querySelectorAll('circle.gr-vpunkt')]
        .map(c => c.getBoundingClientRect());
      const achsen = [...svg.querySelectorAll('text.gr-vachse')]
        .filter(t => t.getAttribute('text-anchor') === 'middle')
        .map(t => t.getBoundingClientRect());
      const ersteAchsenmarke = svg.querySelector('text.gr-vachse');
      const bestmarke = svg.querySelector('text.gr-vbestmarke');
      return {
        svg: { left: sr.left, right: sr.right, top: sr.top, bottom: sr.bottom },
        bild: { left: br.left, right: br.right, top: br.top, bottom: br.bottom },
        letzterKreisRechts: Math.max(...kreise.map(k => k.right)),
        letzterKreisLinks: Math.min(...kreise.map(k => k.left)),
        marken: achsen.map(a => ({ left: a.left, right: a.right })),
        achsenmarkeHoehe: ersteAchsenmarke ?
          ersteAchsenmarke.getBoundingClientRect().height : null,
        bestmarke: bestmarke ? {
          stroke: getComputedStyle(bestmarke).stroke,
          strokeWidth: parseFloat(getComputedStyle(bestmarke).strokeWidth),
          paintOrder: getComputedStyle(bestmarke).paintOrder,
        } : null,
        satz: (() => {
          const p = document.getElementById('gr-vstand');
          return p ? { hidden: p.hidden, text: p.textContent } : null;
        })(),
      };
    }""")


def test_das_svg_passt_in_den_container_mobil(seite):
    """Kriterium 1: das SVG-Rechteck liegt im Container-Rechteck - kein
    `min-width`, das die volle 640-px-Breite erzwingt und den Rest der
    Kurve aus dem sichtbaren Bereich schiebt."""
    m = _messen(seite)
    assert m["svg"]["left"] >= m["bild"]["left"] - 1, m
    assert m["svg"]["right"] <= m["bild"]["right"] + 1, (
        f"SVG rechts ({m['svg']['right']}) ragt aus dem Container "
        f"({m['bild']['right']}): {m}")


def test_der_letzte_messpunkt_ist_sichtbar_mobil(seite):
    """Kriterium 1: der letzte Datenpunkt (24.9.) liegt im sichtbaren
    Bereich, nicht rechts ausserhalb (der QA-Screenshot zeigte nur
    10.8. bis 29.8.)."""
    m = _messen(seite)
    assert m["letzterKreisRechts"] <= m["bild"]["right"] + 1, (
        f"der rechteste Messpunkt ({m['letzterKreisRechts']}) liegt "
        f"ausserhalb des Containers ({m['bild']['right']})")
    assert m["letzterKreisLinks"] >= m["bild"]["left"] - 1, m


@pytest.mark.parametrize("breite", [390, 1440])
def test_keine_zwei_x_achsen_marken_ueberlappen(_wurzel_browser, breite):
    """Kriterium 2: kein Paar von Tick-Label-Rechtecken ueberschneidet
    sich - weder am Telefon noch am Schirm."""
    wurzel, browser = _wurzel_browser
    s = _oeffne(browser, wurzel, breite)
    m = _messen(s)
    s.context.close()
    marken = sorted(m["marken"], key=lambda r: r["left"])
    for a, b in zip(marken, marken[1:]):
        assert a["right"] <= b["left"] + 0.5, (
            f"zwei Datumsmarken ueberlappen bei {breite} px: {a} vs {b} "
            f"(alle Marken: {marken})")


def test_die_achsenschrift_ist_lesbar_mobil(seite):
    """Lead-Befund 24.09.2026 (c): das SVG wurde bis zu diesem Fix mit
    einer festen Zeichenflaeche (1080x340 Einheiten) gebaut und per
    `viewBox` auf die ~340 px breite Telefon-Containerbreite
    HERUNTERSKALIERT - aus 12 px Schrift wurden rund 3-4 CSS-Pixel. Das
    SVG zeichnet jetzt in der ECHTEN, gemessenen Containerbreite (1
    SVG-Einheit = 1 CSS-Pixel); eine Tick-Marke muss darum eine normale
    Zeilenhoehe erreichen, nicht ein Drittel davon."""
    m = _messen(seite)
    assert m["achsenmarkeHoehe"] is not None, "keine X-Achsen-Marke gefunden"
    assert m["achsenmarkeHoehe"] >= 9, (
        f"die Achsenbeschriftung ist nur {m['achsenmarkeHoehe']} px hoch "
        "- das SVG wurde vermutlich noch herunterskaliert")


def test_die_bestmarke_traegt_einen_halo(seite):
    """Kriterium 3: das Label "billigster Stand …" traegt einen Halo in
    Papierfarbe (paint-order: stroke), statt durchgestrichen zu wirken,
    wenn es eine Linie kreuzt."""
    m = _messen(seite)
    assert m["bestmarke"], "kein Bestpreis-Etikett gezeichnet"
    assert "stroke" in m["bestmarke"]["paintOrder"], m["bestmarke"]
    assert m["bestmarke"]["strokeWidth"] > 0, m["bestmarke"]
    assert m["bestmarke"]["stroke"] not in ("none", ""), m["bestmarke"]


def test_der_satz_schweigt_bei_dieser_vielen_terminen(seite):
    """Kriterium 5: bei 16 Messterminen (> `VERLAUF_SATZ_MAX_TERMINE`)
    schweigt der Satz - er doppelte sonst wortgleich die Kachel
    "Messtermine"."""
    m = _messen(seite)
    assert m["satz"] is not None, "kein #gr-vstand-Knoten"
    assert m["satz"]["hidden"], (
        f"der Satz steht trotz 16 Messterminen: {m['satz']['text']!r}")


def test_die_schwelle_ist_eine_zahl_aus_python():
    """Die Schwelle ist EINE Zahl (`geraete_verlauf.VERLAUF_SATZ_MAX_TERMINE`),
    ueber `data-satzmaxtermine` gereicht - kein zweiter Wert in app.js."""
    assert geraete_verlauf.VERLAUF_SATZ_MAX_TERMINE == 8
    assert 16 > geraete_verlauf.VERLAUF_SATZ_MAX_TERMINE
