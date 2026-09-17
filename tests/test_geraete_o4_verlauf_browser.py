"""O4 im echten Chromium → E3-Fix (QA 17.09.2026): der Verlaufs-Reiter
OHNE G0 - die eigene Auswahl steuert das EINZIGE Barpreis-Bild.

Bis zum Fix trug der Reiter ZWEI Barpreis-Grafiken: der G0-Block oben
folgte der Modellwahl des VERGLEICHS-Reiters, der große Graph unten der
eigenen Suche (gr-vsuche). Der QA-Lauf vom 17.09. maß an genau dieser
Fixture: Wahl von „Galaxy S26" im Verlaufs-Reiter wechselte den großen
Graph, der G0-Titel blieb „APPLE IPHONE 17 PRO 256 GB" - zwei Bilder,
widersprüchlicher Gerätezustand. Der Test hier hält beides fest: kein
zweites Barpreis-Bild, und die eigene Wahl bleibt von der Modellwahl des
anderen Reiters unberührt.

Dieselbe Bauform wie `tests/test_geraete_o3_rollen_browser.py`: eigener
Server auf 127.0.0.1 (das Fragment wird per fetch geladen), eigene
Fixture mit PREISHISTORIE:

  * apple-iphone-17-pro 256 (VORGABE): zwei Anbieter mit je zwei
    Messpunkten -> SVG mit Linien in der eigenen Auswahl,
  * samsung-galaxy-s26 256: ein Anbieter mit einem Messpunkt,
  * google-pixel-11 128: Bündel, aber KEINE Listung.
"""
from __future__ import annotations

import contextlib
import json

import pytest
import yaml

from telco_radar.report.html import render_site

from test_geraete_browser_fixture import (
    HEUTE, _chromium, _KATALOG, _FARBEN, _listung, _QUELLEN, _server, _sku)
from test_geraete_zeitreihe_browser import waehle_modell

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
        waehle_modell(seite, modell)
        seite.wait_for_timeout(500)
    seite.click('.gr-reiter [data-tafel="tafel-verlauf"]')
    seite.wait_for_timeout(120)
    return seite


def test_kein_zweites_barpreisbild_und_die_eigene_wahl_zaehlt(lage):
    """E3-Fix (QA 17.09.2026, B2): Der Reiter trug ZWEI Barpreis-Grafiken
    desselben Geräts - G0 oben (folgte der Modellwahl des VERGLEICHS-
    Reiters) und die eigene Auswahl unten. Gemessen hatte der QA-Lauf:
    Wahl von Galaxy S26 hier ließ den G0-Titel oben auf APPLE IPHONE 17
    PRO 256 GB stehen. Jetzt gibt es GENAU EIN Barpreis-Bild-System, und
    die eigene Suche steuert es; die Modellwahl des anderen Reiters
    lässt es unberührt."""
    wurzel, seite = lage
    _oeffne_verlauf(wurzel, seite)
    # 1. Kein G0-Block mehr - auf der ganzen Seite, nicht nur unsichtbar.
    assert seite.evaluate(
        "() => document.querySelector('#gr-g0-lager')") is None, (
        "der G0-Block steht noch im Verlaufs-Reiter (Doppel-Darstellung)")
    # 2. Die eigene Auswahl wählt das VORGABEMODELL (iPhone 17 Pro 256):
    #    zwei Anbieter, vier Messtage - der Graph entsteht.
    seite.fill("#gr-vsuche", "iPhone 17 Pro")
    seite.wait_for_timeout(150)
    seite.click("#gr-vtreffer li:first-child")
    seite.wait_for_timeout(250)
    zustand = seite.evaluate("""() => ({
      feld: document.getElementById('gr-vsuche').value,
      svg: !!document.querySelector('#gr-vbild svg'),
      g0: !!document.querySelector('#gr-g0-lager'),
      kacheln: !document.getElementById('gr-vkacheln').hidden,
    })""")
    assert "iPhone 17 Pro" in zustand["feld"], zustand
    assert zustand["svg"], "die eigene Auswahl zeichnet keinen Graphen"
    assert not zustand["g0"], zustand
    assert zustand["kacheln"], zustand
    # 3. DER QA-FALL: Modellwechsel im VERGLEICHs-Reiter darf das Bild
    #    dieses Reiters nicht mehr verstellen. Vor dem Fix zeigte G0
    #    danach das Fremdmodell, während die Auswahl unten blieb, wo sie
    #    war - zwei Bilder, widersprüchlicher Zustand.
    seite.click('.gr-reiter [data-tafel="tafel-tco"]')
    seite.wait_for_timeout(120)
    waehle_modell(seite, "samsung-galaxy-s26-256")
    seite.wait_for_timeout(400)
    seite.click('.gr-reiter [data-tafel="tafel-verlauf"]')
    seite.wait_for_timeout(150)
    nachher = seite.evaluate("""() => ({
      feld: document.getElementById('gr-vsuche').value,
      svg: !!document.querySelector('#gr-vbild svg'),
      g0: !!document.querySelector('#gr-g0-lager'),
      g0_titel: (document.querySelector('#gr-g0-lager .gr-g0-titel')
                 || {}).textContent || null,
    })""")
    assert nachher["g0"] is False and nachher["g0_titel"] is None, nachher
    assert "iPhone 17 Pro" in nachher["feld"], (
        "die Verlaufs-Auswahl wurde von der Modellwahl des Vergleichs-"
        f"Reiters verstellt: {nachher}")
    assert nachher["svg"], (
        "der Graph der eigenen Auswahl ist nach dem Reiterwechsel weg")
