"""O2 (STRATEGIE_GERAETE_OPTIK §3, 11.09.2026): die Bündel-Zeilen im echten
Chromium - dieselbe Bauform wie `tests/test_geraete_o1_hauptgraph_browser.py`:
eigener Server auf 127.0.0.1, kein `file://`, kein Netz, Chromium an beiden
bekannten Orten gesucht (diese Helfer werden von dort importiert).

Die Abnahmekriterien des O2-Auftrags, hier als Messung:
  A1  <details> über der Falz (1440x900 UND 390x844) höchstens EINER -
      O1 erreichte 0/1, O2 hält das (die Zeilen-Aufklapper stehen unter
      dem Graphen, also unter der Falz).
  A2  <details> gesamt im Hauptpfad deutlich unter 100 - am VORGABEMODELL
      der Fixture nachgezählt (eine Zeile je Bündel).
  Mobil 390: Zeilen stapeln (Entwurf `.bnd summary` grid-areas), kein
      Querscroll.

Die EIGENE Fixture erweitert die O1-Lage um eine Zeile OHNE Band am
Vorgabemodell (unbegrenzter Tarif, §7): die Gruppe unter der Bandliste
braucht ihren eigenen Fall, und die O1-Fixture durfte nicht geändert
werden - ihre Zahlen stehen in O1-Tests.
"""
from __future__ import annotations

import contextlib
import json
import math

import pytest
import yaml

from telco_radar.report.html import render_site

from test_geraete_browser_fixture import (
    HEUTE, _chromium, _KATALOG, _FARBEN, _listung, _QUELLEN, _server, _sku)
from test_geraete_zeitreihe_browser import waehle_band, waehle_modell

# Die O1-Lage PLUS einer unbegrenzten Zeile am Vorgabemodell (o2) und
# einer zweiten Zeile im Band Klein (Telekom) - genug Zeilen, um Stapel,
# Bandwechsel und Deckelung zu messen.
_BAENDER_BUENDEL = [
    ("apple-iphone-17-pro", 256, "o2", "o2:klein", "O2 Mobile Klein", 10, 18.0),
    ("apple-iphone-17-pro", 256, "Vodafone", "vf:klein", "Vodafone Mobil XS",
     18, 26.0),
    ("apple-iphone-17-pro", 256, "congstar", "cs:mittel", "Allnet Flat S",
     50, 20.0),
    # Unbegrenzt: außerhalb der Bänder - Zeile der Gruppe "Ohne Tarifband".
    ("apple-iphone-17-pro", 256, "o2", "o2:unlimited", "O2 Unlimited",
     math.inf, 30.0),
    # Modell B für den Modellwechsel-Test.
    ("samsung-galaxy-s26", 256, "1&1", "11:klein", "All-Net-Flat S", 10, 15.0),
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
    listungen = [
        _listung("Vodafone", "apple-iphone-17-pro", 256, 1199.90),
        _listung("o2", "apple-iphone-17-pro", 256, 1099.00),
        _listung("1&1", "samsung-galaxy-s26", 256, 1049.00),
    ]
    (state / "geraete_db.json").write_text(json.dumps({
        "updated": HEUTE, "anbieter": {
            n: {"laeufe": 4, "funde_gesamt": 1}
            for n in ("Vodafone", "o2", "1&1")},
        "listungen": listungen}), encoding="utf-8")
    (state / "geraete_preise.jsonl").write_text("", encoding="utf-8")
    buendel = []
    for device_id, speicher, anbieter, tarif_id, tarif, gb, rate \
            in _BAENDER_BUENDEL:
        buendel.append({
            "id": f"buendel--{anbieter.lower()}--{_sku(device_id, speicher)}"
                  f"--{tarif_id}",
            "sku_id": _sku(device_id, speicher), "anbieter": anbieter,
            "tarif_name": tarif, "tarif_id": tarif_id,
            "tarif_id_guete": "hoch", "tarif_monatlich": 24.99,
            "geraet_zuzahlung": 1.0, "geraet_monatsrate": rate,
            "laufzeit_monate": 24, "anschlusspreis": 0.0,
            "zustand": "neu", "rabatte": [],
            "quelle_url": f"https://example.de/{anbieter.lower()}/{device_id}",
            "abgerufen_am": HEUTE, "first_seen": HEUTE,
            "last_verified": HEUTE})
    (state / "geraete_tco.json").write_text(json.dumps({
        "updated": HEUTE, "buendel": buendel, "sim_only": []}),
        encoding="utf-8")
    tarife = [
        {"anbieter": anbieter, "name": tarif, "tarif_id": tarif_id,
         "art": "mobilfunk", "grundgebuehr": 24.99, "laufzeit_monate": 24,
         "datenvolumen_gb": gb,
         "preisphasen": [{"von_monat": 1, "bis_monat": None,
                          "betrag": 24.99}],
         "dokument_url": f"https://example.de/pib/{tarif_id}",
         "abgerufen_am": HEUTE, "confidence": {}, "fundstellen": {}}
        for _d, _s, anbieter, tarif_id, tarif, gb, _r in _BAENDER_BUENDEL
    ]
    (state / "tarife.jsonl").write_text(
        "\n".join(json.dumps(t) for t in tarife) + "\n", encoding="utf-8")
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
    site = _baue(tmp_path_factory.mktemp("o2zeilen"))
    exe = _chromium()
    with _server(site) as basis, sync_playwright() as p:
        browser = (p.chromium.launch(executable_path=exe) if exe
                   else p.chromium.launch())
        try:
            yield browser, basis
        finally:
            browser.close()


@pytest.fixture(scope="module")
def _browser_seite(tmp_path_factory):
    with _browser_ctx(tmp_path_factory) as paar:
        yield paar


@pytest.fixture
def seite(_browser_seite):
    browser, basis = _browser_seite
    s = browser.new_page(viewport={"width": 1440, "height": 900})
    s.goto(f"{basis}/geraete.html", wait_until="load")
    s.click(".gr-reiter button[data-tafel='tafel-tco']")
    try:
        yield s
    finally:
        s.close()


@pytest.fixture
def telefon(_browser_seite):
    browser, basis = _browser_seite
    s = browser.new_page(viewport={"width": 390, "height": 844})
    s.goto(f"{basis}/geraete.html", wait_until="load")
    s.click(".gr-reiter button[data-tafel='tafel-tco']")
    try:
        yield s
    finally:
        s.close()


# --------------------------------------------------------------------------
# A1 - Aufklapper über der Falz
# --------------------------------------------------------------------------

@pytest.mark.parametrize("fixture_name", ["seite", "telefon"])
def test_hoechstens_ein_aufklapper_ueber_der_falz(fixture_name, request):
    """O2 hielt A1 von O1; E2 verschiebt die Grenze um eine Kategorie: die
    Bündel-ZEILEN sind Aufklapper des INHALTS (§3.1b) und dürfen über die
    Falz ragen - Erklärlast darf es nicht. Über der Falz bleibt höchstens
    der EINE Rechenschafts-Aufklapper 'So gerechnet'."""
    s = request.getfixturevalue(fixture_name)
    falz = s.viewport_size["height"]
    ueber = s.evaluate("""(falz) => Array.from(
        document.querySelectorAll('#tafel-tco details'))
        .filter(d => {
          if (d.classList.contains('gr-bnd')) return false;
          const b = d.getBoundingClientRect();
          return b.height > 0 && b.top < falz;
        }).map(d => d.className)""", falz)
    assert len(ueber) <= 1, \
        f"{len(ueber)} Erklär-Aufklapper über der Falz ({falz} px): {ueber}"


@pytest.mark.parametrize("fixture_name", ["seite", "telefon"])
def test_die_erste_buendelzeile_ist_ohne_scroll_erreichbar(fixture_name,
                                                           request):
    """Der Entwurf will die Tabelle UNTER dem Graphen - aber die ERSTE
    Zeile gehört noch ins erste Bild, sonst ist der Weg zur Tabelle eine
    Blindheit. (1440: die erste Zeile endet im ersten Bildschirm;
    390: sie endet im zweiten - der Graph hat Vorrang an der Falz.)"""
    s = request.getfixturevalue(fixture_name)
    grenze = 2 * s.viewport_size["height"]
    box = s.eval_on_selector(
        "#gr-bndliste .gr-bnd",
        "e => { const r = e.getBoundingClientRect();"
        "      return {top: Math.round(r.top), endet: Math.round(r.bottom)}; }")
    assert box is not None, "keine Bündelzeile im Dokument"
    assert box["endet"] <= grenze, (
        f"die erste Zeile endet bei {box['endet']} px - tiefer als zwei "
        f"Bildschirme ({grenze} px)")


# --------------------------------------------------------------------------
# A2 - die Zahl der Aufklapper am Vorgabemodell
# --------------------------------------------------------------------------

def test_deutlich_unter_hundert_aufklapper(seite):
    """A2 am Vorgabemodell: eine Zeile je Bündel, je Zeile EIN Rechenweg-
    Aufklapper - zusammen mit 'Wie gerechnet?', Maßstab und Datenlage
    deutlich unter 100."""
    anzahl = seite.eval_on_selector_all(
        "#tafel-tco details", "e => e.length")
    zeilen = seite.eval_on_selector_all(
        "#tafel-tco .gr-bnd", "e => e.length")
    assert zeilen >= 3, f"die Fixture trägt nur {zeilen} Zeilen"
    assert anzahl < 100, f"{anzahl} <details> in der Vergleichsansicht"
    # Der Zuwachs gegen O1 (27) sind die Zeilen-Aufklapper selbst: keine
    # Karte trägt noch ihren EIGENEN zusätzlichen Rechenweg-Aufklapper.
    rw = seite.eval_on_selector_all(
        "#tafel-tco .gr-bnd-rw ~ details, #tafel-tco details details",
        "e => e.length")
    assert rw == 0, f"{rw} verschachtelte Aufklapper in den Zeilen"


# --------------------------------------------------------------------------
# Die Bandwahl steuert die Zeilen mit
# --------------------------------------------------------------------------

def test_der_bandwechsel_versteckt_zeilen_anderer_baender(seite):
    """Dieselbe Auswahl, dieselbe Tabelle: der Wechsel auf ein anderes
    Band versteckt die Zeilen des alten - die Liste ist danach eine
    ANDERE (P1/UX-1 für die Zeilenform)."""
    klein = seite.eval_on_selector_all(
        "#gr-bndliste .gr-bnd[data-band='klein']:not([hidden])",
        "e => e.map(z => z.dataset.anbieter)")
    waehle_band(seite, "mittel")
    seite.wait_for_timeout(120)
    verdeckt = seite.eval_on_selector(
        "#gr-bndliste .gr-bnd[data-band='klein']",
        "e => ({versteckt: e.hidden,"
        "       sichtbar: getComputedStyle(e).display !== 'none'})")
    mittel = seite.eval_on_selector_all(
        "#gr-bndliste .gr-bnd[data-band='mittel']:not([hidden])",
        "e => e.map(z => z.dataset.anbieter)")
    assert "o2" in klein, klein
    assert verdeckt["versteckt"] is True, "Klein-Zeile trägt kein hidden"
    assert verdeckt["sichtbar"] is False
    assert mittel and mittel != klein, (
        f"die Zeilenliste folgt der Bandwahl nicht: {klein} == {mittel}")
    # Der Titel nennt das neue Band.
    titel = seite.eval_on_selector("#gr-bnd-titel", "e => e.textContent")
    assert "Mittel" in titel, titel


def test_die_ohne_tarifband_zeilen_bleiben_stehen(seite):
    """§7: die Zeilen ohne Band gehören zu KEINEM Band - sie bleiben bei
    jedem Bandwechsel stehen (sie hängen nicht an der Auswahl an)."""
    ohne = seite.eval_on_selector_all(
        "#gr-ohneband .gr-bnd", "e => e.map(z => z.dataset.anbieter)")
    assert ohne, "die Fixture trägt keine Zeile ohne Band"
    waehle_band(seite, "mittel")
    seite.wait_for_timeout(120)
    danach = seite.eval_on_selector_all(
        "#gr-ohneband .gr-bnd:not([hidden])",
        "e => e.map(z => z.dataset.anbieter)")
    assert danach == ohne, danach


def test_der_modellwechsel_setzt_die_eigenen_zeilen_ein(seite):
    """O3 (S3): die Tabelle mit Rechenwegen gehört zum GEWÄHLTEN Modell -
    der Wechsel setzt die Zeilen des anderen Geräts ein (aus dem Fragment,
    `data/geraete-buendel.html`), statt sich zu verstecken. Bis O3 tat sie
    genau das; die O2-Fassung dieses Tests nagelte das Verstecken fest."""
    sichtbar = seite.eval_on_selector("#gr-buendel", "e => !e.hidden")
    assert sichtbar, "beim Vorgabemodell steht die Tabelle offen da"
    # E2: die waehlbaren Modelle stehen im Zeitreihen-Knoten (erlaubt).
    auswahl = seite.eval_on_selector(
        "#gr-zeitreihe-daten",
        "k => Object.keys(JSON.parse(k.textContent).erlaubt)")
    vorgabe = seite.eval_on_selector(
        "#gr-zeitreihe-daten", "k => JSON.parse(k.textContent).vorgabe")
    fremd = [o for o in auswahl if o != vorgabe]
    assert fremd, "die Fixture braucht ein zweites Modell"
    waehle_modell(seite, fremd[0])
    seite.wait_for_timeout(300)
    assert seite.eval_on_selector("#gr-buendel", "e => !e.hidden")
    anbieter = seite.eval_on_selector_all(
        "#gr-buendel .gr-bnd", "e => e.map(z => z.dataset.anbieter)")
    assert set(anbieter) == {"1&1"}, anbieter
    assert seite.evaluate(
        "() => !document.getElementById('gr-karten-hinweis')"), \
        "der Vorgabegerät-Hinweis ist mit S3 entfallen"


def test_der_zeilen_aufklapper_oeffnet_ohne_netzwerk(seite):
    """E1: alles bleibt im Dokument erreichbar - das Öffnen einer Zeile ist
    reines UI (derselbe Maßstab wie der OPTIK-6-Klapptest, nur an der
    Zeile)."""
    ursprung = seite.url.rsplit("/", 1)[0]
    anfragen: list[str] = []

    def _zaehle(anfrage) -> None:
        if anfrage.url.startswith(ursprung):
            anfragen.append(anfrage.url)

    seite.on("request", _zaehle)
    try:
        ergebnis = seite.evaluate("""() => {
          const z = document.querySelector('#gr-bndliste .gr-bnd');
          if (!z) return null;
          z.open = true;
          const rw = z.querySelector('.gr-bnd-rw');
          return {sichtbar: !!rw.offsetParent,
                  hoehe: Math.round(rw.getBoundingClientRect().height)};
        }""")
        seite.wait_for_timeout(200)
    finally:
        seite.remove_listener("request", _zaehle)
        seite.evaluate(
            "() => document.querySelectorAll('.gr-bnd')"
            ".forEach(z => { z.open = false; })")
    assert ergebnis is not None, "keine Zeile im Dokument"
    assert ergebnis["sichtbar"], "der Rechenweg bleibt unsichtbar"
    assert ergebnis["hoehe"] > 60, \
        f"der Rechenweg hat nur {ergebnis['hoehe']} px Höhe"
    assert anfragen == [], \
        f"das Öffnen hat Netzwerkanfragen ausgelöst: {anfragen}"


# --------------------------------------------------------------------------
# Mobil 390: Zeilen-Stapel statt Querscroll
# --------------------------------------------------------------------------

def test_zeilen_stapeln_sich_auf_dem_telefon_ohne_querscroll(telefon):
    """Auftrag 1: 'Mobile 390: Tabelle darf quer laufen IN einem
    Scroll-Container NUR wenn unvermeidbar - bevorzugt Zeilen-Stapel wie
    im Entwurf.' Gemessen: keine Zeile läuft aus dem 390-px-Rahmen, und
    die Seite rollt nicht waagerecht."""
    quer = telefon.evaluate(
        "() => Math.max(document.documentElement.scrollWidth,"
        "               document.body.scrollWidth)")
    assert quer <= 391, f"die Seite ist {quer} px breit"
    zu_breit = telefon.evaluate("""() => Array.from(
        document.querySelectorAll('#gr-bndliste .gr-bnd summary'))
        .filter(s => s.scrollWidth > s.clientWidth + 1).length""")
    assert zu_breit == 0, f"{zu_breit} summary-Elemente laufen quer aus"
    # Der Stapel: die Tarif-Zelle liegt UNTER der Anbieter-Zelle, nicht
    # daneben (grid-areas des Entwurfs) - gemessen als Reihenfolge im
    # Layout, nicht im DOM.
    lage = telefon.evaluate("""() => {
      const s = document.querySelector('#gr-bndliste .gr-bnd summary');
      const an = s.querySelector('.gr-bnd-an').getBoundingClientRect();
      const tar = s.querySelector('.gr-bnd-tarif').getBoundingClientRect();
      const tco = s.querySelector('.gr-bnd-tco').getBoundingClientRect();
      return {tarifUnterAnbieter: tar.top >= an.bottom - 2,
              tcoRechtsOderUeber: tco.left > an.left};
    }""")
    assert lage["tarifUnterAnbieter"] is True, (
        "die Zellen stehen nebeneinander statt gestapelt")
    assert lage["tcoRechtsOderUeber"] is True
