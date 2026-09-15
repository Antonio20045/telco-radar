"""O1 (STRATEGIE_GERAETE_OPTIK, 11.09.2026): die Eine-Graph-Hauptansicht,
im echten Chromium gemessen - dieselbe Bauform wie
`tests/test_geraete_tco_band_browser.py`: eigener Server auf 127.0.0.1,
kein `file://`, kein Netz, Chromium an beiden bekannten Orten gesucht.

Die Abnahmekriterien des O1-Auftrags, hier als Messung:
  A1  Leitantwort über der Falz OHNE Klick, Hover oder Querscroll -
      auf 1440x900 UND 390x844: die beste Balkenzeile mit Anbietername,
      TCO-24-Wert und Δ vollständig sichtbar.
  A2  GENAU EIN Graph-Modul in #tafel-tco - kein zweites Chart, keine
      Zeitreihe (G0 wandert in O4 in den Verlaufs-Reiter).
  A3  Fehlende Anbieter als EINE Legendenzeile, keine Einzelsätze.
  A4  EINE Fußnote statt fünf paralleler Zählsysteme.
  A5  Höchstens EIN <details> über der Falz.

Die Fixture stellt DREI Modelle: das Vorgabemodell mit zwei Bändern (Klein
mit Vodafone-Referenz, Mittel ohne - für die Δ-Regel), ein Modell mit nur
einer Zeile (Selektor-Wechsel) und eines OHNE Band (Leerzustand des
Graphen, Band-Auswahl ohne erlaubte Option).
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
import yaml

from telco_radar.report.html import render_site

WURZEL = pathlib.Path(__file__).resolve().parents[1]
HEUTE = "2026-09-11"

# Drei Modelle, drei Lagen. Das Vorgabemodell ist das Leitfrage-Gerät
# (`geraete_tco_karten.LEITFRAGE_MODELL`), sobald es zwei Anbieter hat.
_KATALOG = {"geraete": [
    {"hersteller": "Apple", "modell": "iPhone 17 Pro", "generation": 17,
     "marktstart": "2025-09-19", "speicher": [256], "segment": "premium"},
    {"hersteller": "Samsung", "modell": "Galaxy S26", "generation": 26,
     "marktstart": "2026-01-30", "speicher": [256], "segment": "premium"},
    {"hersteller": "Google", "modell": "Pixel 11", "generation": 11,
     "marktstart": "2026-08-20", "speicher": [128], "segment": "premium"},
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

# (device_id, speicher, anbieter, tarif_id, tarif, gb, rate)
_BAENDER_BUENDEL = [
    # Modell A, Band Klein: drei Anbieter, Vodafone ist das teuerste und
    # damit die Referenz UNTER den Zeilen (o2/congstar tragen negatives Δ).
    ("apple-iphone-17-pro", 256, "o2", "o2:klein", "O2 Mobile Klein", 10, 18.0),
    ("apple-iphone-17-pro", 256, "congstar", "cs:klein", "Allnet Flat XS", 15, 22.0),
    ("apple-iphone-17-pro", 256, "Vodafone", "vf:klein", "Vodafone Mobil XS", 18, 26.0),
    # Modell A, Band Mittel: nur congstar - Vodafone fehlt, keine Δ-Angabe.
    ("apple-iphone-17-pro", 256, "congstar", "cs:mittel", "Allnet Flat S", 50, 20.0),
    # Modell B, Band Klein: nur 1&1.
    ("samsung-galaxy-s26", 256, "1&1", "11:klein", "All-Net-Flat S", 10, 15.0),
    # Modell C: Bündel in einem Tarif OHNE Datenvolumen - kein Band.
    ("google-pixel-11", 128, "o2", "o2:ohne", "O2 Mobile Flex", None, 18.0),
]


def _sku(device_id, speicher):
    return f"{device_id}-{speicher}gb-schwarz"


def _listung(anbieter, device_id, speicher, preis):
    return {"id": f"{anbieter.lower()}--{_sku(device_id, speicher)}",
            "sku_id": _sku(device_id, speicher), "device_id": device_id,
            "anbieter": anbieter, "anbieter_typ": "netzbetreiber",
            "netz": anbieter, "speicher_gb": speicher, "farbe_roh": "Schwarz",
            "farbe_normalisiert": "schwarz", "zustand": "neu",
            "first_seen": "2026-08-20", "last_verified": HEUTE,
            "status": "aktiv", "missed_checks": 0,
            "preis_ohne_vertrag": preis, "erstpreis": preis,
            "erstpreis_art": "ohne_vertrag", "erstpreis_am": "2026-08-20",
            "quelle_url": f"https://example.de/{anbieter.lower()}/{device_id}",
            "abgerufen_am": HEUTE, "verfuegbarkeit": "lieferbar",
            "confidence": "hoch", "einstiege": ["https://example.de/liste"]}


def _baue(tmp_path: pathlib.Path):
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
    # Barpreise fuer die Antwortzeile - nur bei zweien, damit der Test auch
    # den Leerzustand einer Zahl sieht (Modell C ohne jeden Barpreis).
    listungen = [
        _listung("Vodafone", "apple-iphone-17-pro", 256, 1199.90),
        _listung("o2", "apple-iphone-17-pro", 256, 1099.00),
        _listung("1&1", "samsung-galaxy-s26", 256, 1049.00),
        _listung("o2", "google-pixel-11", 128, 799.00),
    ]
    (state / "geraete_db.json").write_text(json.dumps({
        "updated": HEUTE,
        "anbieter": {"Vodafone": {"laeufe": 4, "funde_gesamt": 1},
                     "o2": {"laeufe": 4, "funde_gesamt": 2},
                     "1&1": {"laeufe": 4, "funde_gesamt": 1}},
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
        {"anbieter": anbieter, "name": tarif,
         "tarif_id": tarif_id, "art": "mobilfunk",
         "grundgebuehr": 24.99, "laufzeit_monate": 24,
         "datenvolumen_gb": gb,
         "preisphasen": [{"von_monat": 1, "bis_monat": None, "betrag": 24.99}],
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


def _chromium():
    for muster in ("/opt/pw-browsers/chromium-*/chrome-linux/chrome",
                   str(pathlib.Path.home() / ".cache/ms-playwright"
                       / "chromium*/chrome-linux*/chrome")):
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
    """Browser und gerenderte Seite; Tests öffnen sich eigene Ansichten."""
    sync_playwright = pytest.importorskip(
        "playwright.sync_api", reason="playwright fehlt").sync_playwright
    site = _baue(tmp_path_factory.mktemp("o1graph"))
    exe = _chromium()
    with _server(site) as basis, sync_playwright() as p:
        browser = (p.chromium.launch(executable_path=exe) if exe
                   else p.chromium.launch())
        yield browser, basis
        browser.close()


@pytest.fixture
def seite(_browser_seite):
    """1440x900 - das Mass der Falzmessung auf dem Schreibtisch."""
    browser, basis = _browser_seite
    s = browser.new_page(viewport={"width": 1440, "height": 900})
    s.goto(f"{basis}/geraete.html", wait_until="load")
    try:
        yield s
    finally:
        s.close()


@pytest.fixture
def telefon(_browser_seite):
    browser, basis = _browser_seite
    s = browser.new_page(viewport={"width": 390, "height": 844})
    s.goto(f"{basis}/geraete.html", wait_until="load")
    try:
        yield s
    finally:
        s.close()


def _erste_zeile(s):
    return s.query_selector("#tafel-tco .gr-bz")


# --------------------------------------------------------------------------
# A1 - die Leitantwort über der Falz
# --------------------------------------------------------------------------

@pytest.mark.parametrize("fixture_name", ["seite", "telefon"])
def test_die_beste_zeile_steht_ohne_scrollen_im_bild(fixture_name, request):
    """A1: Anbietername, TCO-24-Wert und Δ der besten Zeile vollständig
    über der Falz - ein halb abgeschnittener Balken ist genau der Zustand,
    den man sofort wegscrollen will (derselbe Massstab wie
    `test_falz_browser.py`)."""
    s = request.getfixturevalue(fixture_name)
    falz = s.viewport_size["height"]
    zeile = _erste_zeile(s)
    assert zeile is not None, "der Graph hat keine Zeile gerendert"
    box = zeile.bounding_box()
    assert box is not None and box["y"] >= 0
    assert box["y"] + box["height"] <= falz, (
        f"{fixture_name}: die beste Zeile endet bei "
        f"{box['y'] + box['height']:.0f} px, Falz {falz} px")
    text = " ".join(zeile.inner_text().split())
    assert "€" in text, f"kein TCO-Wert gedruckt: {text!r}"
    assert "€ · " in text or "Referenz" in text, f"kein Δ: {text!r}"


@pytest.mark.parametrize("fixture_name", ["seite", "telefon"])
def test_kein_querscroll_auf_der_vergleichsansicht(fixture_name, request):
    """A1: kein Querscroll - der Graph ist HTML/CSS-Balken, genau deshalb
    (Auftrag: "es gibt kein Querscroll auf 390 px und Werte stehen immer
    im Textfluss, kein Hover")."""
    s = request.getfixturevalue(fixture_name)
    breite = s.evaluate(
        "Math.max(document.documentElement.scrollWidth,"
        "document.body.scrollWidth)")
    assert breite <= s.viewport_size["width"] + 1, \
        f"die Seite ist {breite} px breit bei {s.viewport_size['width']} px"


def test_die_werte_stehen_als_text_nicht_im_hover(seite):
    """A1: kein Hover nötig - jede Zeile druckt Anbieter, Tarif, Wert und
    Δ als Text (die alte SVG-Lösung trug sie nur im Tooltip, den es am
    Telefon nicht gibt)."""
    zeilen = seite.query_selector_all("#tafel-tco .gr-bz")
    assert len(zeilen) >= 3, \
        f"nur {len(zeilen)} Zeilen - der Test misst sonst einen Leerzustand"
    for zeile in zeilen:
        text = " ".join(zeile.inner_text().split())
        assert "€" in text
        assert zeile.query_selector(".gr-bz-anbieter").inner_text().strip()
        assert zeile.query_selector(".gr-bz-tarif").inner_text().strip()


# --------------------------------------------------------------------------
# A2 - genau ein Graph-Modul
# --------------------------------------------------------------------------

def test_genau_ein_graphmodul_und_keine_zeitreihe(seite):
    """A2: EIN Graph-Modul, keine zweite Grafik, keine Zeitreihe mehr in
    der Vergleichsansicht - G0 wandert in O4 in den Verlaufs-Reiter."""
    assert seite.eval_on_selector_all(
        "#tafel-tco .gr-hgraph", "e => e.length") == 1
    # Der Graph ist HTML/CSS - kein SVG in der ganzen Tafel mehr (die
    # Band-SVGs und G0 sind mit O1 aus dieser Ansicht entfernt).
    assert seite.eval_on_selector_all("#tafel-tco svg", "e => e.length") == 0, \
        "in der Vergleichsansicht steht noch ein SVG"
    for tot in (".gr-grafik--zeitreihe", ".gr-grafik--tcoband", ".gr-g0-chrome",
                ".gr-g0-haendler", ".gr-tband-werte"):
        assert seite.eval_on_selector_all(f"#tafel-tco {tot}",
                                          "e => e.length") == 0, tot


def test_die_vodafone_zeile_ist_die_emphasis_und_traegt_referenz(seite):
    """Der Auftrag: Vodafone-Zeile als Emphasis („unser Angebot", statt Δ
    das Wort „Referenz"), alle anderen mit Δ gegen genau diese Zeile."""
    zeilen = seite.query_selector_all("#tafel-tco .gr-bz")
    eigen = [z for z in zeilen if "gr-bz--eigen" in (z.get_attribute("class")
                                                     or "")]
    assert len(eigen) == 1, "genau eine Vodafone-Zeile"
    text = " ".join(eigen[0].inner_text().split())
    assert "unser Angebot" in text
    assert "Referenz" in text
    assert "€ ·" not in text, "die Referenzzeile trägt kein Δ gegen sich"
    assert "günstiger" not in text and "teurer" not in text
    # Jede NICHT-eigene Zeile trägt ein Δ mit Vorzeichen und Prozent.
    for z in zeilen:
        if z in eigen:
            continue
        text = " ".join(z.inner_text().split())
        assert "€ · " in text and "%" in text, text
        assert "unser Angebot" not in text


def test_die_zeilen_stehen_guenstigster_zuerst(seite):
    """Der günstigste Anbieter steht oben (O1: "sortierte horizontale
    Balken (günstigster zuerst)") - gelesen aus den data-Attributen, nicht
    aus dem formatierten Text."""
    betraege = seite.eval_on_selector_all(
        "#tafel-tco .gr-bz", "es => es.map(e => parseFloat("
        "e.getAttribute('data-tco')))")
    assert len(betraege) >= 3, "ein Leerzustand hat keine Ordnung zu prüfen"
    assert betraege == sorted(betraege), betraege


# --------------------------------------------------------------------------
# A3 - EINE Legendenzeile für Fehlende
# --------------------------------------------------------------------------

def test_fehlende_anbieter_stehen_in_einer_zeile(seite):
    """A3: EINE Legendenzeile statt Einzelsätzen je Anbieter - die 145
    "führt kein Bündel in diesem Band"-Zeilen der alten Band-Panels sind
    mit dem Graph entfallen."""
    assert seite.eval_on_selector_all(
        "#tafel-tco .gr-lueckenzeile", "e => e.length") == 1
    text = seite.query_selector("#tafel-tco .gr-lueckenzeile").inner_text()
    assert "1&1" in text, "der fehlende Anbieter 1&1 fehlt in der Legende"
    assert "führt für dieses Gerät kein Bündel" not in \
        seite.query_selector("#tafel-tco").inner_text()
    assert "Telekom" in text, "auch ein nie beobachteter Anbieter fehlt"


def test_band_ohne_vodafone_sagt_keine_delta_angabe(seite):
    """Ohne echtes Vodafone-Bündel im Band gibt es kein Δ - die
    Unterzeile sagt es (Entwurf, Band Groß), statt stillschweigend gegen
    die Näherung der Karten zu rechnen."""
    seite.select_option("#gr-band", "mittel")
    unter = seite.query_selector("#gr-hgraph-unter").inner_text()
    assert "keine Δ-Angabe" in unter
    for z in seite.query_selector_all("#tafel-tco .gr-bz"):
        assert "€ · " not in z.inner_text(), \
            "Zeile trägt Δ, obwohl das Band keine Vodafone-Referenz hat"


# --------------------------------------------------------------------------
# A4 - EINE Fußnote statt fünf Zählsysteme
# --------------------------------------------------------------------------

def test_eine_fussnote_und_keine_alten_zaehler(seite):
    """A4: die EINE Fußnote (Stand · Geräte · Bänder-Herkunft mit Link auf
    tarife.html) ersetzt die Zählsysteme der Vergleichsansicht."""
    fussnoten = seite.query_selector_all("#tafel-tco .gr-tco-fussnote")
    assert len(fussnoten) == 1
    text = " ".join(fussnoten[0].inner_text().split())
    assert "Geräte mit mindestens einem erhebbaren Bündel" in text
    assert "Stand" in text
    link = fussnoten[0].query_selector("a")
    assert link is not None and link.get_attribute("href").endswith(
        "tarife.html")
    # Die alten Zähler sind weg: kein "- N Anbieter" an der Auswahl, keine
    # Angebots-Zeile unter dem Graphen, kein Geräte-Zähler am Selektor.
    for option in seite.eval_on_selector_all(
            "#gr-modell option", "es => es.map(e => e.textContent)"):
        assert "Anbieter" not in option, option
    tafel = seite.query_selector("#tafel-tco").inner_text()
    assert "Angebote" not in tafel.split("Anbieterkarten")[0], \
        "die gr-mband-Angebotszeile steht noch im Lesefluss"
    assert seite.eval_on_selector_all(
        "#tafel-tco .gr-mband", "e => e.length") == 0


# --------------------------------------------------------------------------
# A5 - Aufklapper über der Falz
# --------------------------------------------------------------------------

@pytest.mark.parametrize("fixture_name", ["seite", "telefon"])
def test_hoechstens_ein_aufklapper_ueber_der_falz(fixture_name, request):
    """A5: über der Falz steht höchstens der EINE "Wie gerechnet?"-
    Aufklapper des Graphen - die Kartenklappe und die Details-Aufklappung
    rücken darunter."""
    s = request.getfixturevalue(fixture_name)
    falz = s.viewport_size["height"]
    ueber = s.evaluate("""(falz) => Array.from(
        document.querySelectorAll('#tafel-tco details'))
        .filter(d => {
          const b = d.getBoundingClientRect();
          return b.height > 0 && b.top < falz;
        }).map(d => d.className)""", falz)
    assert len(ueber) <= 1, \
        f"{len(ueber)} Aufklapper über der Falz ({falz} px): {ueber}"


# --------------------------------------------------------------------------
# Der Selektor: funktional für ALLE Geräte
# --------------------------------------------------------------------------

def test_der_selector_traegt_alle_modelle_ohne_suffix(seite):
    optionen = seite.eval_on_selector_all(
        "#gr-modell option", "es => es.map(e => [e.value, e.textContent])")
    assert len(optionen) == 3, optionen
    assert "iPhone 17 Pro 256 GB" in optionen[0][1]
    # Der JSON-Knoten trägt dieselben Modelle - der Selektor schaltet
    # nichts, was nicht auch Daten hat.
    ids = seite.evaluate(
        "JSON.parse(document.getElementById('gr-graph-daten').textContent)"
        ".modelle.map(m => m.id)")
    assert sorted(ids) == sorted(v for v, _t in optionen)


def test_modellwechsel_zeigt_das_gewaehlte_geraet(seite):
    """Der Selektor ist für ALLE Geräte funktional: Auswahl zeigt genau
    dieses Modell im Graph - Titel und Zeilen wechseln mit."""
    server_text = " ".join(
        (_erste_zeile(seite) or type("X", (), {"inner_text": lambda s: ""})()
         ).inner_text().split()) if _erste_zeile(seite) else ""
    assert "o2" in server_text, "Ausgangslage: das Vorgabemodell, Band Klein"

    seite.select_option("#gr-modell", "samsung-galaxy-s26-256")
    seite.wait_for_timeout(120)
    # `.gr-tueber` setzt uppercase - gelesen wird kleingeschrieben.
    titel = seite.query_selector("#gr-tco-titel").inner_text().lower()
    assert "galaxy s26" in titel
    zeilen = seite.query_selector_all("#tafel-tco .gr-bz")
    assert len(zeilen) == 1
    assert "1&1" in zeilen[0].inner_text()
    # Die Antwortzeile wechselt mit - ihre Zahlen gehören zum Modell.
    antwort = seite.query_selector(".gr-antwort").inner_text()
    assert "1.049" in antwort, \
        "die Antwortzeile zeigt noch die Zahlen des Vorgabemodells"


def test_modellwechsel_auf_band_loses_geraet_zeigt_den_leerzustand(seite):
    seite.select_option("#gr-modell", "google-pixel-11-128")
    seite.wait_for_timeout(250)
    assert seite.eval_on_selector_all(
        "#tafel-tco .gr-bz", "e => e.length") == 0
    unter = seite.query_selector(".gr-hgraph").inner_text()
    assert "keinem Tarifband" in unter, unter


def test_bandwechsel_baut_die_zeilen_aus_dem_json(seite):
    """KEINE ZWEITE RECHNUNG, auch nicht im Browser: nach dem Bandwechsel
    stehen dieselben Zeilen, die der Server für das Vorgabemodell
    gerendert hat - app.js liest sie aus dem JSON-Knoten."""
    vorher = [" ".join(z.inner_text().split())
              for z in seite.query_selector_all("#tafel-tco .gr-bz")]
    seite.select_option("#gr-band", "mittel")
    seite.wait_for_timeout(120)
    mittel = [" ".join(z.inner_text().split())
              for z in seite.query_selector_all("#tafel-tco .gr-bz")]
    assert mittel != vorher, "der Bandwechsel baut die Zeilen nicht um"
    assert any("congstar" in z for z in mittel)
    chip = seite.query_selector("#gr-bandchip").inner_text()
    assert "Mittel" in chip
    # Und zurueck: derselbe Zustand wie der Server-Render.
    seite.select_option("#gr-band", "klein")
    seite.wait_for_timeout(120)
    zurueck = [" ".join(z.inner_text().split())
               for z in seite.query_selector_all("#tafel-tco .gr-bz")]
    assert zurueck == vorher


def test_modellwechsel_zeigt_die_zeilen_des_geraets(seite):
    """O3 (S3, Auflage des O2-Evaluators): die Bündel-Tabelle gehört zum
    GEWÄHLTEN Modell - der Wechsel setzt die Zeilen des anderen Geräts
    ein (aus dem Fragment), und der Weg zurück stellt die Server-Ausgabe
    wieder her. Bis O3 versteckte sich die Tabelle bei fremdem Modell
    (19 von 423 Zeilen am echten Bestand erreichbar); der alte Test hier
    nagelte genau dieses Verstecken fest."""
    tabelle = seite.query_selector("#gr-buendel")
    assert tabelle.is_visible(), "beim Vorgabemodell steht die Tabelle offen"
    seite.select_option("#gr-modell", "samsung-galaxy-s26-256")
    seite.wait_for_timeout(300)
    assert tabelle.is_visible(), \
        "die Tabelle gehört inzwischen zum gewählten Modell (O3/S3)"
    anbieter = seite.eval_on_selector_all(
        "#gr-buendel .gr-bnd", "e => e.map(z => z.dataset.anbieter)")
    assert set(anbieter) == {"1&1"}, anbieter
    assert seite.query_selector("#gr-karten-hinweis") is None, \
        "der Vorgabegerät-Hinweis ist mit S3 ersatzlos entfallen"
    # Der Graph des gewählten Geräts steht weiterhin (aus dem JSON-Knoten).
    zeilen = seite.eval_on_selector_all(
        "#tafel-tco .gr-bz", "e => e.length")
    assert zeilen, "der Graph des gewählten Modells hat keine Zeilen"
    # Zurueck auf die Vorgabe: dieselben Anbieter wie der Server-Render.
    seite.select_option("#gr-modell", "apple-iphone-17-pro-256")
    seite.wait_for_timeout(300)
    anbieter = seite.eval_on_selector_all(
        "#gr-buendel .gr-bnd", "e => e.map(z => z.dataset.anbieter)")
    assert set(anbieter) == {"o2", "Vodafone", "congstar"}, anbieter


def test_keine_schrift_unter_zwoelf_pixel_im_graph(seite):
    """Hausregel der Vorlage (keine Schrift unter 12 px) - auch der neue
    Graph hält sie, obwohl der Entwurf 10,5-px-Chips zeigt."""
    klein = seite.evaluate("""() => {
      const graph = document.querySelector('#tafel-tco .gr-hgraph');
      let kleinst = 99;
      for (const el of graph.querySelectorAll('*')) {
        const fs = parseFloat(getComputedStyle(el).fontSize);
        if (getComputedStyle(el).display !== 'none' && fs) {
          kleinst = Math.min(kleinst, fs);
        }
      }
      return kleinst;
    }""")
    assert klein >= 12, f"{klein} px"


def test_der_leerzustand_ohne_modelle_bleibt_ehrlich(tmp_path):
    """Ohne ein einziges Bündel rendert die Tafel ihre benannte Lücke -
    der Graph-Knoten existiert dann nicht, und app.js darf nicht auf ihn
    zugreifen (Guard gegen einen TypeError auf der leeren Seite)."""
    site = _baue(tmp_path)
    # Dieselbe Welt, aber OHNE Bündel - nur der Tarif- und Listungsbestand
    # bleibt stehen (er beweist, dass die Lücke am Bündel liegt, nicht an
    # kaputten Daten).
    tco = json.loads((tmp_path / "site_baum" / "data" / "state"
                      / "geraete_tco.json").read_text())
    tco["buendel"] = []
    reports = tmp_path / "site_baum" / "data" / "reports"
    (tmp_path / "site_baum" / "data" / "state" / "geraete_tco.json") \
        .write_text(json.dumps(tco))
    render_site(tmp_path / "leer", reports)
    html = (tmp_path / "leer" / "geraete.html").read_text()
    assert "Es gibt heute kein einziges Bündel" in html
    assert "gr-graph-daten" not in html
