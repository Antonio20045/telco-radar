"""Die gemeinsame BROWSER-FIXTURE der Geraeteseite (seit O1, E2 umgezogen).

Baut einen kleinen Geraetebestand (Modelle mit Buendeln in zwei Baendern,
eine band-lose Zeile), rendert site/ in tmp und stellt Server- und
Chromium-Pfad-Helfer bereit. Bis E2 lebten diese Bausteine in
`test_geraete_o1_hauptgraph_browser.py`; deren Tests sind mit der
Balkenansicht gefallen (ersetzt durch `test_geraete_zeitreihe_browser`),
die Fixture behalten die o2-/o3-/o4-Browsertests.
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
