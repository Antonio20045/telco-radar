"""GRAPH-1 (BRIEF_GRAPH1, 08.09.2026), Aufgabe 5e: beide Auswahlen -
Gerät und Tarifband - sichtbar und funktional, im echten Browser gemessen
(1440×900, dieselbe Bauform wie `test_geraete_reiter_browser.py` und
`test_geraete_antwortzeile_browser.py`: eigener Server auf 127.0.0.1, kein
`file://`, kein Netz, Chromium an beiden bekannten Orten gesucht).

Die Fixture baut EIN Modell mit zwei echten Bündeln in zwei verschiedenen
Bändern (o2 in Klein, Vodafone in Mittel) - genug, um zu zeigen, dass die
Bandauswahl wirklich umschaltet und nicht nur eine leere Hülle ist.
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
HEUTE = "2026-09-08"

_KATALOG = {"geraete": [
    {"hersteller": "Apple", "modell": "iPhone 17 Pro", "generation": 17,
     "marktstart": "2025-09-19", "speicher": [256], "segment": "premium"}]}
_FARBEN = {"farben": {"schwarz": ["Schwarz"]}}
_QUELLEN = {"anbieter": [
    {"name": "o2", "typ": "netzbetreiber", "rang": 2, "methode": "ldjson",
     "basis_url": "https://www.o2online.de",
     "einstiege": [{"url": "https://www.o2online.de/handys"}]},
    {"name": "Vodafone", "typ": "netzbetreiber", "rang": 1, "eigen": True,
     "methode": "ldjson", "basis_url": "https://www.vodafone.de",
     "einstiege": [{"url": "https://www.vodafone.de/handys"}]},
]}

SKU = "apple-iphone-17-pro-256gb-schwarz"


def _listung(anbieter, preis):
    return {"id": f"{anbieter.lower()}--{SKU}", "sku_id": SKU,
            "device_id": "apple-iphone-17-pro", "anbieter": anbieter,
            "anbieter_typ": "netzbetreiber", "netz": anbieter,
            "speicher_gb": 256, "farbe_roh": "Schwarz",
            "farbe_normalisiert": "schwarz", "zustand": "neu",
            "first_seen": "2026-08-20", "last_verified": HEUTE,
            "status": "aktiv", "missed_checks": 0,
            "preis_ohne_vertrag": preis, "erstpreis": preis,
            "erstpreis_art": "ohne_vertrag", "erstpreis_am": "2026-08-20",
            "quelle_url": f"https://example.de/{anbieter.lower()}/{SKU}",
            "abgerufen_am": HEUTE, "verfuegbarkeit": "lieferbar",
            "confidence": "hoch", "einstiege": ["https://example.de/liste"]}


def _buendel(anbieter, tarif_id, tarif_name, rate):
    return {"id": f"buendel--{anbieter.lower()}--{SKU}--{tarif_id}",
            "sku_id": SKU, "anbieter": anbieter, "tarif_name": tarif_name,
            "tarif_id": tarif_id, "tarif_id_guete": "hoch",
            "tarif_monatlich": 24.99, "geraet_zuzahlung": 1.0,
            "geraet_monatsrate": rate, "laufzeit_monate": 24,
            "anschlusspreis": 0.0, "zustand": "neu", "rabatte": [],
            "quelle_url": f"https://example.de/{anbieter.lower()}/{SKU}",
            "abgerufen_am": HEUTE, "first_seen": HEUTE, "last_verified": HEUTE}


def _tarif(anbieter, tarif_id, tarif_name, gb):
    return {"anbieter": anbieter, "name": tarif_name, "tarif_id": tarif_id,
            "art": "mobilfunk", "grundgebuehr": 24.99, "laufzeit_monate": 24,
            "datenvolumen_gb": gb,
            "preisphasen": [{"von_monat": 1, "bis_monat": None,
                             "betrag": 24.99}],
            "dokument_url": f"https://example.de/pib/{tarif_id}",
            "abgerufen_am": HEUTE, "confidence": {}, "fundstellen": {}}


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
    listungen = [_listung("o2", 999.0), _listung("Vodafone", 1049.0)]
    (state / "geraete_db.json").write_text(json.dumps({
        "updated": HEUTE,
        "anbieter": {"o2": {"laeufe": 4, "funde_gesamt": 1},
                    "Vodafone": {"laeufe": 4, "funde_gesamt": 1}},
        "listungen": listungen}), encoding="utf-8")
    (state / "geraete_preise.jsonl").write_text("", encoding="utf-8")
    buendel = [
        _buendel("o2", "o2:tarif-klein", "O2 Mobile Klein", 18.0),
        _buendel("Vodafone", "vodafone:tarif-mittel", "Vodafone Mittel", 15.0),
    ]
    (state / "geraete_tco.json").write_text(json.dumps({
        "updated": HEUTE, "buendel": buendel, "sim_only": []}),
        encoding="utf-8")
    tarife = [
        _tarif("o2", "o2:tarif-klein", "O2 Mobile Klein", 18.0),
        _tarif("Vodafone", "vodafone:tarif-mittel", "Vodafone Mittel", 40.0),
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
def _seite(tmp_path_factory):
    sync_playwright = pytest.importorskip(
        "playwright.sync_api", reason="playwright fehlt").sync_playwright

    tmp_path = tmp_path_factory.mktemp("tcoband")
    site = _baue(tmp_path)

    exe = _chromium()
    with _server(site) as basis, sync_playwright() as p:
        browser = (p.chromium.launch(executable_path=exe) if exe
                   else p.chromium.launch())
        seite = browser.new_page(viewport={"width": 1440, "height": 900})
        seite.goto(f"{basis}/geraete.html", wait_until="load")
        seite.click('[data-tafel="tafel-tco"]')
        yield seite
        browser.close()


def test_beide_auswahlen_stehen_sichtbar_nebeneinander(_seite):
    modellwahl = _seite.query_selector("#gr-modell")
    bandwahl = _seite.query_selector("#gr-band")
    assert modellwahl is not None, "Geräteauswahl fehlt"
    assert bandwahl is not None, "Tarifband-Auswahl fehlt"
    assert modellwahl.is_visible()
    assert bandwahl.is_visible()

    optionen = _seite.eval_on_selector_all(
        "#gr-band option", "(es) => es.map(e => e.value)")
    assert set(optionen) == {"klein", "mittel", "gross"}
    # "Groß" hat fuer dieses Modell kein Buendel und ist deshalb DEAKTIVIERT
    # (Aufgabe 1: "nur Bänder anbieten, für die Bündel existieren"), aber
    # weiterhin als Option vorhanden.
    disabled = _seite.eval_on_selector_all(
        "#gr-band option", "(es) => es.filter(e => e.disabled).map(e => e.value)")
    assert disabled == ["gross"]


def test_bandwechsel_schaltet_den_richtigen_graphen_sichtbar(_seite):
    # Ausgangslage: das erste verfuegbare Band (Klein, o2) ist sichtbar.
    sichtbares_band = _seite.eval_on_selector(
        "#tafel-tco .gr-tmodell:not([hidden]) .gr-tband:not([hidden])",
        "(e) => e.getAttribute('data-band')")
    assert sichtbares_band == "klein"
    text_klein = _seite.eval_on_selector(
        "#tafel-tco .gr-tmodell:not([hidden]) .gr-tband:not([hidden])",
        "(e) => e.textContent")
    assert "o2" in text_klein

    # Umschalten auf Mittel (Vodafone).
    _seite.select_option("#gr-band", "mittel")
    sichtbares_band = _seite.eval_on_selector(
        "#tafel-tco .gr-tmodell:not([hidden]) .gr-tband:not([hidden])",
        "(e) => e.getAttribute('data-band')")
    assert sichtbares_band == "mittel"
    text_mittel = _seite.eval_on_selector(
        "#tafel-tco .gr-tmodell:not([hidden]) .gr-tband:not([hidden])",
        "(e) => e.textContent")
    assert "Vodafone" in text_mittel
    # Das Klein-Panel ist jetzt versteckt, nicht entfernt.
    versteckt = _seite.eval_on_selector(
        '#tafel-tco .gr-tmodell:not([hidden]) .gr-tband[data-band="klein"]',
        "(e) => e.hidden")
    assert versteckt is True
