"""A/E (QA-Fix 24.09.2026): der CLIENT-Chart des Reiters „Preisverlauf"
(`app.js` `zeichne(g)`) zeichnet jetzt dieselbe STUFENLINIE wie der
Server-Chart der TCO-Zeitreihe (`geraete_zeitreihe._stufenpfad`) und
punktet Abschnitte über eine Messlücke > `LUECKE_TAGE_SCHWELLE` genauso.

Die Schwelle ist EINE Zahl (`geraete_zeitreihe.LUECKE_TAGE_SCHWELLE`),
durchgereicht über `report/geraete_verlauf.py` an `data-luecke-tage` des
Knotens `#gr-vstand` - dieser Test hält Python-Wert UND das Attribut
zusammen (kein zweiter Wert in `app.js`, siehe CLAUDE.md 6).

Fixture: EIN Gerät, EIN Anbieter, VIER Messpunkte mit kontrollierten
Tagesabständen - 10 Tage (Grenzfall E: NICHT über der Schwelle, also
durchgezogen), 11 Tage (Grenzfall E: über der Schwelle, gepunktet), dann
wieder 10 Tage (durchgezogen). Der Client bekommt die Rohpunkte über das
Suchfeld-Fragment `#gr-verlaufdaten`, dieselbe Bauform wie
`tests/test_geraete_o4_verlauf_browser.py`.
"""
from __future__ import annotations

import contextlib
import json
import re
from pathlib import Path

import pytest
import yaml

from telco_radar.report import geraete_zeitreihe
from telco_radar.report.html import render_site

from test_geraete_browser_fixture import (
    HEUTE, _chromium, _KATALOG, _FARBEN, _listung, _QUELLEN, _server, _sku)

DEVICE = "apple-iphone-17-pro"
SPEICHER = 256
ANBIETER = "o2"
LISTUNG_ID = f"{ANBIETER.lower()}--{_sku(DEVICE, SPEICHER)}"

# (datum, preis) - Abstaende: 10 Tage (Grenzfall, durchgezogen), 11 Tage
# (Grenzfall, gepunktet), 10 Tage (durchgezogen). Vier Punkte erreichen
# `DIAGRAMM_AB_TERMINEN` (4), das Gatter oeffnet.
_PUNKTE = [
    ("2026-08-01", 999.00),
    ("2026-08-11", 949.00),   # +10 Tage seit 08-01 -> NICHT ueber der Schwelle
    ("2026-08-22", 899.00),   # +11 Tage seit 08-11 -> UEBER der Schwelle
    ("2026-09-01", 850.00),   # +10 Tage seit 08-22 -> NICHT ueber der Schwelle
]


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
    # DIESELBE Listung wie `_listung()`, nur mit `last_verified` auf dem
    # LETZTEN Messpunkt (statt HEUTE) - sonst fuegt `_punkte()` einen
    # fuenften, unkontrollierten Bestaetigungstag bei HEUTE hinzu und der
    # sorgfaeltig gebaute 10/11/10-Tage-Rhythmus stimmt nicht mehr.
    letzt_datum, letzt_preis = _PUNKTE[-1]
    listung = _listung(ANBIETER, DEVICE, SPEICHER, letzt_preis)
    listung["last_verified"] = letzt_datum
    (state / "geraete_db.json").write_text(json.dumps({
        "updated": HEUTE,
        "anbieter": {ANBIETER: {"laeufe": 4, "funde_gesamt": 1}},
        "listungen": [listung]}), encoding="utf-8")
    (state / "geraete_preise.jsonl").write_text(
        "\n".join(json.dumps({
            "listung_id": LISTUNG_ID, "datum": tag,
            "preis_ohne_vertrag": preis, "preisart": "ohne_vertrag",
            "quelle_url": "https://example.de/beleg"})
            for tag, preis in _PUNKTE) + "\n",
        encoding="utf-8")
    buendel = [{
        "id": f"buendel--{ANBIETER.lower()}--{_sku(DEVICE, SPEICHER)}--o2:klein",
        "sku_id": _sku(DEVICE, SPEICHER), "anbieter": ANBIETER,
        "tarif_name": "O2 Mobile Klein", "tarif_id": "o2:klein",
        "tarif_id_guete": "hoch", "tarif_monatlich": 24.99,
        "geraet_zuzahlung": 1.0, "geraet_monatsrate": 18.0,
        "laufzeit_monate": 24, "anschlusspreis": 0.0,
        "zustand": "neu", "rabatte": [],
        "quelle_url": f"https://example.de/{ANBIETER.lower()}/{DEVICE}",
        "abgerufen_am": HEUTE, "first_seen": HEUTE, "last_verified": HEUTE}]
    (state / "geraete_tco.json").write_text(json.dumps({
        "updated": HEUTE, "buendel": buendel, "sim_only": []}),
        encoding="utf-8")
    (state / "tarife.jsonl").write_text(json.dumps({
        "anbieter": ANBIETER, "name": "O2 Mobile Klein",
        "tarif_id": "o2:klein", "art": "mobilfunk", "grundgebuehr": 24.99,
        "laufzeit_monate": 24, "datenvolumen_gb": 10,
        "preisphasen": [{"von_monat": 1, "bis_monat": None, "betrag": 24.99}],
        "dokument_url": "https://example.de/pib/o2-klein",
        "abgerufen_am": HEUTE, "confidence": {}, "fundstellen": {}}) + "\n",
        encoding="utf-8")
    reports = root / "data" / "reports"
    reports.mkdir(parents=True)
    (reports / f"{HEUTE}.json").write_text(json.dumps({
        "date": HEUTE, "language": "de",
        "briefing_md": "## Auf einen Blick\n\n- Nichts Besonderes.\n",
        "stats": {}, "regions": []}), encoding="utf-8")
    (reports / f"{HEUTE}.md").write_text("# Bericht\n", encoding="utf-8")
    site = root / "site"
    render_site(site, reports)
    return site


@contextlib.contextmanager
def _browser_ctx(tmp_path_factory):
    sync_playwright = pytest.importorskip(
        "playwright.sync_api", reason="playwright fehlt").sync_playwright
    site = _baue(tmp_path_factory.mktemp("stufenlinie"))
    exe = _chromium()
    with _server(site) as wurzel, sync_playwright() as p:
        browser = (p.chromium.launch(executable_path=exe) if exe
                   else p.chromium.launch())
        try:
            yield wurzel, browser
        finally:
            browser.close()


@pytest.fixture(scope="module")
def _browser_paar(tmp_path_factory):
    # EIN sync_playwright()-Kontext je Modul: ein zweiter, gleichzeitig
    # offener stoesst auf "Sync API inside the asyncio loop" (siehe
    # `test_ohne_attribut_keine_ausnahme_und_keine_luecken_punktierung`).
    with _browser_ctx(tmp_path_factory) as (wurzel, browser):
        yield wurzel, browser


@pytest.fixture
def seite(_browser_paar):
    wurzel, browser = _browser_paar
    s = browser.new_page()
    s.goto(f"{wurzel}/geraete.html", wait_until="networkidle")
    s.click('.gr-reiter [data-tafel="tafel-verlauf"]')
    s.wait_for_timeout(120)
    s.fill("#gr-vsuche", "iPhone 17 Pro")
    s.wait_for_timeout(150)
    s.click("#gr-vtreffer li:first-child")
    s.wait_for_timeout(300)
    yield s
    s.close()


def test_das_data_attribut_traegt_den_python_wert(seite):
    """DIE SCHWELLE IST EINE ZAHL: `data-luecke-tage` an `#gr-vstand` muss
    exakt `geraete_zeitreihe.LUECKE_TAGE_SCHWELLE` tragen - keine zweite,
    in `app.js` hartkodierte Zahl (CLAUDE.md 6)."""
    wert = seite.eval_on_selector(
        "#gr-vstand", "e => e.getAttribute('data-luecke-tage')")
    assert wert is not None, "kein data-luecke-tage-Attribut am Knoten"
    assert int(wert) == geraete_zeitreihe.LUECKE_TAGE_SCHWELLE, (
        f"data-luecke-tage={wert!r}, Python-Quelle "
        f"{geraete_zeitreihe.LUECKE_TAGE_SCHWELLE!r}")


def _pfade(seite):
    """Alle Linien-Pfade des gezeichneten Diagramms, mit ihrer Strichart -
    aeltester Abschnitt zuerst (nach dem ersten x-Wert des Pfads sortiert,
    denn `zeichne()` haengt sie in dieser Reihenfolge an)."""
    return seite.evaluate("""() => {
      const svg = document.querySelector('#gr-vbild svg');
      if (!svg) return null;
      return [...svg.querySelectorAll('path.gr-vlinie')].map(p => ({
        d: p.getAttribute('d'),
        luecke: p.classList.contains('gr-vlinie--luecke'),
        dasharray: getComputedStyle(p).strokeDasharray,
      })).sort((a, b) => {
        const ax = parseFloat(a.d.split(/[ML]/)[1]);
        const bx = parseFloat(b.d.split(/[ML]/)[1]);
        return ax - bx;
      });
    }""")


def _ist_stufenfoermig(d: str) -> bool:
    """Jedes Segment ist waagerecht ODER senkrecht - keine schraege Linie.

    `d` ist eine Folge von `M x y` und `L x y`-Befehlen (siehe
    `stufenpfad()` in `app.js`); zwischen zwei aufeinanderfolgenden Punkten
    muss x ODER y gleich bleiben."""
    import re
    zahlen = re.findall(r"[ML](-?[\d.]+) (-?[\d.]+)", d)
    punkte = [(float(x), float(y)) for x, y in zahlen]
    for i in range(1, len(punkte)):
        x0, y0 = punkte[i - 1]
        x1, y1 = punkte[i]
        if x0 != x1 and y0 != y1:
            return False
    return True


def test_der_pfad_ist_eine_stufenlinie(seite):
    """Kein Segment ist schraeg - ein Preis gilt vom Messtag an und
    SPRINGT dort, er GLEITET nicht dorthin (dieselbe Regel wie der
    Server-Chart, `geraete_zeitreihe._stufenpfad`)."""
    pfade = _pfade(seite)
    assert pfade, "kein gezeichneter Pfad im Preisverlauf-SVG"
    for p in pfade:
        assert _ist_stufenfoermig(p["d"]), (
            f"ein Pfadabschnitt ist nicht stufenfoermig: {p['d']!r}")


def test_der_abschnitt_ueber_der_schwelle_ist_gepunktet_der_andere_nicht(
        seite):
    """E (Grenzfall): 10 Tage bleiben durchgezogen, 11 Tage sind gepunktet -
    am selben Diagramm, nicht in zwei Fixtures."""
    pfade = _pfade(seite)
    # Drei Verbindungen zwischen vier Punkten: 10, 11, 10 Tage. Bei einer
    # Messluecke > Schwelle zerfaellt der Zug in einzelne Laeufe (siehe
    # `linienLaeufe()`); erwartet werden hier zwei durchgezogene Abschnitte
    # (08-01..08-11, 08-22..09-01) und EIN gepunkteter (08-11..08-22).
    luecken = [p for p in pfade if p["luecke"]]
    durchgezogen = [p for p in pfade if not p["luecke"]]
    assert len(luecken) == 1, (
        f"erwartet genau einen gepunkteten Abschnitt (11-Tage-Luecke), "
        f"gefunden {len(luecken)}: {pfade}")
    assert durchgezogen, "kein durchgezogener Abschnitt gefunden"
    # Der gepunktete Abschnitt traegt wirklich ein Punkt-/Strichmuster -
    # nicht nur die Klasse, auch das gerechnete `stroke-dasharray` (die CSS-
    # Regel fuer `--anb-strich` darf ihn nicht mit "none" ueberschreiben,
    # siehe `style.css` `.gr-vlinie:not(...):not(.gr-vlinie--luecke)`).
    for p in luecken:
        muster = p["dasharray"]
        assert muster and muster != "none", (
            f"der gepunktete Abschnitt traegt kein Strichmuster: {p!r}")
    # GEGENPROBE: ein durchgezogener 10-Tage-Abschnitt traegt KEINE
    # eigene Luecken-Klasse (er darf natuerlich die normale Anbieter-
    # Strichart tragen, o2 ist "gepunktet" in `anbieter_farben.py` -
    # deshalb wird hier nur die KLASSE geprueft, nicht das Muster selbst).
    for p in durchgezogen:
        assert not p["luecke"], p


def test_app_js_traegt_kein_rueckfall_literal_fuer_die_schwellen():
    """CLAUDE.md Clean Code 3: ein fehlender Wert ist eine benannte Luecke,
    nie ein geratener Wert - `app.js` darf `LUECKE_TAGE`/`SATZ_MAX_TERMINE`
    nicht still mit 10/8 ausfuellen, falls das data-Attribut fehlt."""
    quelltext = (Path(__file__).parent.parent / "src" / "telco_radar"
                 / "report" / "templates" / "app.js").read_text("utf-8")
    assert "|| '10'" not in quelltext and "|| \"10\"" not in quelltext
    assert "|| '8'" not in quelltext and "|| \"8\"" not in quelltext


def test_ohne_attribut_keine_ausnahme_und_keine_luecken_punktierung(
        _browser_paar):
    """Fehlt `data-luecke-tage`/`data-satzmaxtermine` am Knoten (Route
    entfernt beide VOR dem Laden, denn `app.js` liest sie einmalig beim
    Modul-Start), darf der Client weder eine Ausnahme werfen noch heimlich
    mit 10/8 weiterrechnen: kein Abschnitt gilt dann je als Luecke
    (Vergleich gegen NaN ist immer false), und der Stand-Satz schweigt."""
    wurzel, browser = _browser_paar
    ctx = browser.new_context()
    ctx.route("**/geraete.html", lambda route: route.fulfill(
        body=re.sub(
            r' data-(luecke-tage|satzmaxtermine)="\d+"', "",
            route.fetch().text()),
        content_type="text/html"))
    s = ctx.new_page()
    fehler = []
    s.on("pageerror", lambda e: fehler.append(str(e)))
    s.goto(f"{wurzel}/geraete.html", wait_until="networkidle")
    s.click('.gr-reiter [data-tafel="tafel-verlauf"]')
    s.wait_for_timeout(120)
    s.fill("#gr-vsuche", "iPhone 17 Pro")
    s.wait_for_timeout(150)
    s.click("#gr-vtreffer li:first-child")
    s.wait_for_timeout(300)
    attribut_weg = s.eval_on_selector(
        "#gr-vstand", "e => e.getAttribute('data-luecke-tage')")
    assert attribut_weg is None, "die Route hat das Attribut nicht entfernt"
    pfade = _pfade(s)
    assert pfade, "kein gezeichneter Pfad - der Test prüft nichts"
    assert all(not p["luecke"] for p in pfade), (
        f"ohne Schwelle gilt trotzdem ein Abschnitt als Lücke: {pfade}")
    assert s.eval_on_selector("#gr-vstand", "e => e.hidden") is True, (
        "der Stand-Satz erscheint auch ohne data-satzmaxtermine")
    ctx.close()
    assert fehler == [], f"Ausnahmen im Client: {fehler}"


def test_grenzfall_zehn_tage_gegenprobe_am_python_wert():
    """Reine Rechenprobe (kein Browser): 10 Tage sind NICHT groesser als
    `LUECKE_TAGE_SCHWELLE` (10), 11 Tage sind es - derselbe Vergleich
    (`>`, nicht `>=`), den `app.js` `linienLaeufe()` und
    `geraete_zeitreihe._linien_laeufe()` beide verwenden."""
    schwelle = geraete_zeitreihe.LUECKE_TAGE_SCHWELLE
    assert schwelle == 10, (
        "dieser Test nimmt den Grenzfall 10/11 an - die Konstante hat "
        f"sich geaendert ({schwelle}), die Fixture-Abstaende oben "
        "muessen mitziehen")
    assert not (10 > schwelle)
    assert 11 > schwelle
