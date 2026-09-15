"""O4 im echten Chromium: G0 im Verlaufs-Reiter folgt dem Modell-Umschalter.

Dieselbe Bauform wie `tests/test_geraete_o3_rollen_browser.py`: eigener
Server auf 127.0.0.1 (das Fragment wird per fetch geladen), eigene Fixture
mit PREISHISTORIE - denn G0 zeichnet nur, wo Listungen mit Barpreis und
Messpunkte existieren:

  * apple-iphone-17-pro 256 (VORGABE): zwei Anbieter mit je zwei
    Messpunkten -> SVG mit Linien,
  * samsung-galaxy-s26 256: ein Anbieter mit einem Messpunkt -> SVG mit
    einem Punkt, Wertetabelle sagt 'ein Messpunkt',
  * google-pixel-11 128: Bündel, aber KEINE Listung -> ehrlicher
    Leerzustand ohne SVG.
"""
from __future__ import annotations

import contextlib
import json

import pytest
import yaml

from telco_radar.report.html import render_site

from test_geraete_o1_hauptgraph_browser import (
    HEUTE, _chromium, _KATALOG, _FARBEN, _listung, _QUELLEN, _server, _sku)

# (device_id, speicher, anbieter, tarif_id, tarif, gb, rate)
_BUENDEL = [
    ("apple-iphone-17-pro", 256, "o2", "o2:klein", "O2 Mobile Klein",
     10, 18.0),
    ("apple-iphone-17-pro", 256, "Vodafone", "vf:klein", "Vodafone Mobil XS",
     18, 26.0),
    ("samsung-galaxy-s26", 256, "1&1", "11:klein", "All-Net-Flat S",
     10, 15.0),
    ("google-pixel-11", 128, "o2", "o2:ohne", "O2 Mobile Flex", None, 18.0),
]

# Messpunkte VOR dem heutigen Bestätigungsstand (last_verified=HEUTE):
# das Vorgabemodell bekommt zwei Anbieter mit je einer Änderung, das
# S26-Modell einen einzigen Bestätigungspunkt.
_PUNKTE = [
    # (listung_id, datum, preis)
    ("o2--apple-iphone-17-pro-256gb-schwarz", "2026-08-20", 1149.00),
    ("o2--apple-iphone-17-pro-256gb-schwarz", "2026-09-01", 1099.00),
    ("vodafone--apple-iphone-17-pro-256gb-schwarz", "2026-08-20", 1199.90),
    ("vodafone--apple-iphone-17-pro-256gb-schwarz", "2026-08-28", 1249.90),
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
        "updated": HEUTE,
        "anbieter": {n: {"laeufe": 4, "funde_gesamt": 1}
                     for n in ("Vodafone", "o2", "1&1")},
        "listungen": listungen}), encoding="utf-8")
    (state / "geraete_preise.jsonl").write_text(
        "\n".join(json.dumps({"listung_id": lid, "datum": tag,
                              "preis_ohne_vertrag": preis,
                              "preisart": "ohne_vertrag",
                              "quelle_url": "https://example.de/beleg"})
                  for lid, tag, preis in _PUNKTE) + "\n",
        encoding="utf-8")
    buendel = []
    for device_id, speicher, anbieter, tarif_id, tarif, gb, rate in _BUENDEL:
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
         "preisphasen": [{"von_monat": 1, "bis_monat": None,
                          "betrag": 24.99}],
         "dokument_url": f"https://example.de/pib/{tarif_id}",
         "abgerufen_am": HEUTE, "confidence": {}, "fundstellen": {}}
        for _d, _s, anbieter, tarif_id, tarif, gb, _r in _BUENDEL
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
    site = _baue(tmp_path_factory.mktemp("o4verlauf"))
    exe = _chromium()
    with _server(site) as wurzel, sync_playwright() as p:
        browser = (p.chromium.launch(executable_path=exe) if exe
                   else p.chromium.launch())
        try:
            yield site, wurzel, browser
        finally:
            browser.close()


@pytest.fixture(scope="module")
def lage(tmp_path_factory):
    with _browser_ctx(tmp_path_factory) as (site, wurzel, browser):
        yield wurzel, browser.new_page()


def _oeffne_verlauf(wurzel, seite, modell=None):
    """Geräteseite öffnen und den Reiter 'Preisverlauf' einschalten.

    Der Modell-Umschalter steht im Reiter 'Vergleich' - die Wahl wird
    dort getroffen und DANN gewechselt, genau der Weg eines Lesers
    (der Selektor ist im Verlaufs-Reiter nicht sichtbar)."""
    seite.goto(f"{wurzel}/geraete.html", wait_until="networkidle")
    if modell:
        seite.select_option("#gr-modell", modell)
        seite.wait_for_timeout(500)
    seite.click('.gr-reiter [data-tafel="tafel-verlauf"]')
    seite.wait_for_timeout(120)
    return seite


def test_der_verlaufs_reiter_zeigt_g0_des_vorgabemodells(lage):
    wurzel, seite = lage
    _oeffne_verlauf(wurzel, seite)
    box = seite.evaluate("""() => {
      const lager = document.querySelector('#gr-g0-lager');
      if (!lager) return null;
      return {
        svg: !!lager.querySelector('svg.gr-g0'),
        titel: (lager.querySelector('.gr-g0-titel') || {}).textContent,
        zeilen: document.querySelectorAll('#gr-g0-lager .gr-g0-werte tbody tr').length,
        sichtbar: !!(lager.offsetParent || lager.getClientRects().length),
      };
    }""")
    assert box, "#gr-g0-lager fehlt im Verlaufs-Reiter"
    assert box["svg"], "G0-SVG fehlt für das Vorgabemodell"
    assert "iPhone 17 Pro" in box["titel"], box["titel"]
    assert box["zeilen"] == 2, (
        f"zwei Anbieter mit Messpunkten erwartet, {box['zeilen']} Zeilen")


def test_der_modellwechsel_tauscht_g0_aus(lage):
    """S3-Regel, jetzt für G0: der Block zeigt das GEWÄHLTE Modell - aus
    demselben Fragment wie die Bündel-Zeilen, ohne zweite Anfrage."""
    wurzel, seite = lage
    _oeffne_verlauf(wurzel, seite, modell="samsung-galaxy-s26-256")
    box = seite.evaluate("""() => {
      const lager = document.querySelector('#gr-g0-lager');
      return {
        titel: (lager.querySelector('.gr-g0-titel') || {}).textContent,
        svg: !!lager.querySelector('svg.gr-g0'),
        zeilen: document.querySelectorAll('#gr-g0-lager .gr-g0-werte tbody tr').length,
        punkte: document.querySelectorAll('#gr-g0-lager svg.gr-g0 circle').length,
      };
    }""")
    assert "Galaxy S26" in box["titel"], box["titel"]
    assert box["svg"], "G0-SVG fehlt nach dem Modellwechsel"
    assert box["zeilen"] == 1, box
    assert box["punkte"] >= 1, "ein Messpunkt muss als Punkt da sein"


def test_der_rueckwechsel_zeigt_das_vorgabemodell_wieder(lage):
    """Die S2-Lektion von O3, angewandt auf G0: nach einem Wechsel zu einem
    Fremdmodell zeigt der Rückweg die VORGABE-Zeilen, nicht die zuletzt
    injizierten."""
    wurzel, seite = lage
    _oeffne_verlauf(wurzel, seite, modell="google-pixel-11-128")
    seite.click('.gr-reiter [data-tafel="tafel-tco"]')
    seite.wait_for_timeout(120)
    seite.select_option("#gr-modell", "apple-iphone-17-pro-256")
    seite.wait_for_timeout(400)
    seite.click('.gr-reiter [data-tafel="tafel-verlauf"]')
    seite.wait_for_timeout(120)
    titel = seite.evaluate(
        "() => document.querySelector('#gr-g0-lager .gr-g0-titel')"
        ".textContent")
    zeilen = seite.evaluate(
        "() => document.querySelectorAll('#gr-g0-lager .gr-g0-werte tbody tr')"
        ".length")
    assert "iPhone 17 Pro" in titel, titel
    assert zeilen == 2, f"Rückweg zeigt {zeilen} Zeilen statt 2"


def test_ein_modell_ohne_messreihe_hat_den_ehrlichen_leerzustand(lage):
    """Kein Diagramm unter der Messtag-Schwelle, kein herbeigelogener
    Punkt: ein Modell ohne jeden Barpreis-Messpunkt zeigt den Satz, kein
    SVG."""
    wurzel, seite = lage
    _oeffne_verlauf(wurzel, seite, modell="google-pixel-11-128")
    box = seite.evaluate("""() => {
      const lager = document.querySelector('#gr-g0-lager');
      return {
        svg: !!lager.querySelector('svg.gr-g0'),
        /* Whitespace normalisieren: der Satz steht im HTML auf
         * mehreren Zeilen, und 'keine\n  Preishistorie' ist kein
         * Substring. */
        text: lager.textContent.replace(/\s+/g, ' '),
      };
    }""")
    assert not box["svg"], "SVG für ein Modell ohne Messpunkte"
    assert "keine Preishistorie" in box["text"], box["text"][:200]
