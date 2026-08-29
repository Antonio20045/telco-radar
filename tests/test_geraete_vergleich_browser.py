"""Der Anbieterfilter des Preisvergleichs - im echten Browser gemessen.

WARUM IM BROWSER
----------------
Der Filter ist die einzige Stelle der Sektion, die im HTML nicht zu sehen
ist: er blendet Zeilen per `hidden` um und schaltet dabei zwischen Tabelle
und Hinweistext. Ein statischer Test saehe nur, dass alle Zeilen dastehen -
und genau der Fall, der am 29.08.2026 beim Ansehen auffiel, waere ihm
entgangen: "nur Fachhandel" leerte die Tabelle KOMMENTARLOS, weil an diesem
Tag nur Netzbetreiber Daten lieferten. Eine leere Flaeche ohne Satz liest
sich als kaputte Seite.

Dieselbe Bauform wie `tests/test_falz_browser.py`: eigener Server auf
127.0.0.1 (kein file://, kein Netz), Chromium an beiden bekannten Orten
gesucht, ein Browserstart je Testlauf.
"""
from __future__ import annotations

import contextlib
import functools
import glob
import http.server
import json
import socket
import threading
from pathlib import Path

import pytest
import yaml

from telco_radar.report.html import render_site

REPO = Path(__file__).resolve().parents[1]

_KATALOG = {"geraete": [
    {"hersteller": "Apple", "modell": "iPhone 17 Pro Max", "generation": 17,
     "speicher": [256, 512], "segment": "flagship"},
    {"hersteller": "Samsung", "modell": "Galaxy S25 Ultra", "generation": 25,
     "speicher": [256], "segment": "flagship"},
]}
_FARBEN = {"farben": {"titan-natur": ["Titannatur"], "schwarz": ["Schwarz"]}}
_QUELLEN = {"anbieter": [
    {"name": "Vodafone", "typ": "netzbetreiber", "rang": 1, "eigen": True,
     "methode": "ldjson", "basis_url": "https://www.vodafone.de",
     "einstiege": [{"url": "https://www.vodafone.de/handys"}]},
    {"name": "o2", "typ": "netzbetreiber", "rang": 2, "methode": "ldjson",
     "basis_url": "https://www.o2online.de",
     "einstiege": [{"url": "https://www.o2online.de/handys"}]},
    {"name": "Medimax", "typ": "handel", "rang": 3, "methode": "ldjson",
     "basis_url": "https://www.medimax.de",
     "einstiege": [{"url": "https://www.medimax.de/c/116"}]},
]}


def _listung(anbieter, typ, sku, preis, gid="apple-iphone-17-pro-max",
             speicher=256):
    return {
        "id": f"{anbieter.lower()}--{sku}", "sku_id": sku, "device_id": gid,
        "anbieter": anbieter, "anbieter_typ": typ, "netz": "",
        "speicher_gb": speicher, "farbe_roh": "Titannatur",
        "farbe_normalisiert": "titan-natur", "zustand": "neu",
        "first_seen": "2026-08-01", "last_verified": "2026-08-11",
        "status": "aktiv", "missed_checks": 0, "preis_ohne_vertrag": preis,
        "erstpreis": preis, "erstpreis_art": "ohne_vertrag",
        "erstpreis_am": "2026-08-01",
        "quelle_url": f"https://example.de/p/{sku}",
        "abgerufen_am": "2026-08-11", "verfuegbarkeit": "lieferbar",
        "confidence": "hoch", "einstiege": ["https://example.de/liste"],
    }


# Zwei Geraete: beim ersten ist NUR ein Fachhaendler guenstiger, beim
# zweiten NUR ein Netzbetreiber. Damit trennt jeder Filterknopf wirklich -
# ein Fixture, in dem beide Typen ueberall vorkommen, koennte gruen sein,
# ohne dass der Filter etwas tut.
_DB = {"updated": "2026-08-11", "anbieter": {
    "Vodafone": {"laeufe": 4, "funde_gesamt": 4},
    "o2": {"laeufe": 4, "funde_gesamt": 4},
    "Medimax": {"laeufe": 4, "funde_gesamt": 4},
}, "listungen": [
    _listung("Vodafone", "netzbetreiber", "vf-17pm", 1349.0),
    _listung("Medimax", "handel", "mx-17pm", 1199.0),
    _listung("o2", "netzbetreiber", "o2-17pm", 1399.0),
    _listung("Vodafone", "netzbetreiber", "vf-s25u", 1249.0,
             gid="samsung-galaxy-s25-ultra"),
    _listung("o2", "netzbetreiber", "o2-s25u", 1149.0,
             gid="samsung-galaxy-s25-ultra"),
    _listung("Medimax", "handel", "mx-s25u", 1299.0,
             gid="samsung-galaxy-s25-ultra"),
]}


def _chromium():
    for muster in ("/opt/pw-browsers/chromium-*/chrome-linux/chrome",
                   str(Path.home() / ".cache/ms-playwright"
                       / "chromium*/chrome-linux*/chrome")):
        treffer = sorted(glob.glob(muster))
        if treffer:
            return treffer[-1]
    return None


@contextlib.contextmanager
def _server(site: Path):
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
def _gemessen(tmp_path_factory):
    sync_playwright = pytest.importorskip(
        "playwright.sync_api", reason="playwright fehlt").sync_playwright

    root = tmp_path_factory.mktemp("vergleich")
    (root / "config").mkdir()
    for name, daten in (("geraete_katalog.yaml", _KATALOG),
                        ("farben.yaml", _FARBEN),
                        ("geraete_quellen.yaml", _QUELLEN)):
        (root / "config" / name).write_text(
            yaml.safe_dump(daten, allow_unicode=True, sort_keys=False),
            encoding="utf-8")
    state = root / "data" / "state"
    state.mkdir(parents=True)
    (state / "geraete_db.json").write_text(json.dumps(_DB), encoding="utf-8")
    (state / "geraete_preise.jsonl").write_text("", encoding="utf-8")
    reports = root / "data" / "reports"
    reports.mkdir(parents=True)
    site = root / "site"
    render_site(site, reports, cfg=None)

    exe = _chromium()
    ergebnis = {}
    with _server(site) as basis, sync_playwright() as p:
        browser = (p.chromium.launch(executable_path=exe) if exe
                   else p.chromium.launch())
        seite = browser.new_page(viewport={"width": 1440, "height": 900})
        seite.goto(f"{basis}/geraete.html", wait_until="load")
        for typ in ("alle", "netzbetreiber", "handel"):
            seite.click(f".gr-vergleich .gr-filter-knopf[data-typ='{typ}']")
            seite.wait_for_timeout(80)
            ergebnis[typ] = {
                "zeilen": seite.eval_on_selector_all(
                    ".gr-vergleich .gr-v-zeile:not([hidden])", "e => e.length"),
                "modelle": seite.eval_on_selector_all(
                    ".gr-vergleich .gr-v-zeile:not([hidden]) .szl",
                    "e => e.map(x => x.textContent.trim())"),
                "hinweis": seite.eval_on_selector(
                    ".gr-vergleich .gr-v-leer", "e => !e.hidden"),
                "tabelle": seite.eval_on_selector(
                    ".gr-vergleich .gr-vergleich-scroll", "e => !e.hidden"),
                "aktiv": seite.eval_on_selector_all(
                    ".gr-vergleich .gr-filter-knopf.is-aktiv",
                    "e => e.map(x => x.getAttribute('data-typ'))"),
            }
        browser.close()
    return ergebnis


def test_ohne_filter_stehen_alle_zeilen(_gemessen):
    assert _gemessen["alle"]["zeilen"] == 2
    assert _gemessen["alle"]["hinweis"] is False


def test_der_netzbetreiber_filter_laesst_nur_die_passende_zeile(_gemessen):
    """Beim Galaxy S25 Ultra ist o2 guenstiger, beim iPhone nur Medimax."""
    n = _gemessen["netzbetreiber"]
    assert n["zeilen"] == 1
    assert n["modelle"] == ["Galaxy S25 Ultra"]


def test_der_fachhandels_filter_laesst_nur_die_andere_zeile(_gemessen):
    h = _gemessen["handel"]
    assert h["zeilen"] == 1
    assert h["modelle"] == ["iPhone 17 Pro Max"]


def test_genau_ein_knopf_ist_aktiv(_gemessen):
    for typ, werte in _gemessen.items():
        assert werte["aktiv"] == [typ], typ


def test_eine_leere_auswahl_zeigt_einen_satz_statt_einer_leeren_flaeche(_gemessen):
    """Der Befund vom 29.08.2026, im Browser gesehen und nicht im HTML:
    eine leere Tabelle ohne Erklaerung liest sich als kaputte Seite."""
    for werte in _gemessen.values():
        if werte["zeilen"] == 0:
            assert werte["hinweis"] is True
            assert werte["tabelle"] is False
        else:
            assert werte["hinweis"] is False
            assert werte["tabelle"] is True
