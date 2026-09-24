"""QA-Fix 24.09.2026, Punkt 7: MOBILE Bündelzeilen der Vergleichstafel
(Reiter „Vergleich"). Zwei Befunde am selben Screenshot:

  a) der Preis stand bei Vodafone ("unser Angebot") und Telekom ("kein
     aktueller Stand seit …") uneinheitlich zu den anderen Zeilen - Ziel
     ist dieselbe rechte Kante und dieselbe Lage zum Anbieternamen in
     JEDER Zeile.
  b) das Abzeichen (`.gr-kk-marke`) war `inline-block` mit `max-content`-
     Breite - eine schmale Box (~90 px), in der "kein aktueller Stand
     seit 09.09.2026" auf drei enge Zeilen umbrach und die Telekom-Zeile
     insgesamt vierfach. Fix: `display:block;width:100%` am Telefon.

Fixture: vier Anbieter desselben Bündels - Vodafone (eigen, "unser
Angebot"), Telekom (Abruf 9 Tage alt, "kein aktueller Stand seit …",
ueber `geraete_tco_karten.ALT_AB_TAGEN`), o2 und 1&1 ohne Abzeichen."""
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

from telco_radar.report import geraete_tco_karten
from telco_radar.report.html import render_site

HEUTE = "2026-09-24"
ALT_ABGERUFEN = "2026-09-15"  # 9 Tage vor HEUTE, > ALT_AB_TAGEN (3)

_KATALOG = {"geraete": [
    {"hersteller": "Apple", "modell": "iPhone 17 Pro", "generation": 17,
     "marktstart": "2025-09-19", "speicher": [256], "segment": "premium"},
]}
_FARBEN = {"farben": {"schwarz": ["Schwarz"]}}
_QUELLEN = {"anbieter": [
    {"name": "Vodafone", "typ": "netzbetreiber", "rang": 1, "eigen": True,
     "methode": "ldjson", "basis_url": "https://www.vodafone.de",
     "einstiege": [{"url": "https://www.vodafone.de/handys"}]},
    {"name": "Telekom", "typ": "netzbetreiber", "rang": 2,
     "methode": "ldjson", "basis_url": "https://www.telekom.de",
     "einstiege": [{"url": "https://www.telekom.de/handys"}]},
    {"name": "o2", "typ": "netzbetreiber", "rang": 3, "methode": "ldjson",
     "basis_url": "https://www.o2online.de",
     "einstiege": [{"url": "https://www.o2online.de/handys"}]},
    {"name": "congstar", "typ": "netzbetreiber", "rang": 4,
     "methode": "ldjson", "basis_url": "https://www.congstar.de",
     "einstiege": [{"url": "https://www.congstar.de/handys"}]},
]}

DEVICE = "apple-iphone-17-pro"
SPEICHER = 256

# (anbieter, tarif_id, tarif, rate, abgerufen_am) - Vodafone/Telekom
# WORTGETREU aus der Lead-Meldung (24.09.2026, iPhone 17 Pro 256 GB, Band
# Klein), congstar/1&1 ebenso (Tarifname "Allnet Flat XS Flex" dort real
# gemessen) - dieselben Zeilen, an denen die Preiszelle vor dem Grid-Fix
# je nach Zeile neben dem Namen ODER eine Zeile tiefer stand.
_BUENDEL = [
    ("Vodafone", "vf:klein", "Vodafone Mobil XS", 26.0, HEUTE),
    ("Telekom", "tk:klein", "MagentaMobil XS", 24.0, ALT_ABGERUFEN),
    ("congstar", "cs:klein", "Allnet Flat XS Flex", 18.0, HEUTE),
    ("1&1", "11:klein", "All-Net-Flat S", 15.0, HEUTE),
]


def _sku(device_id, speicher):
    return f"{device_id}-{speicher}gb-schwarz"


def _listung(anbieter, preis, abgerufen_am):
    return {"id": f"{anbieter.lower()}--{_sku(DEVICE, SPEICHER)}",
            "sku_id": _sku(DEVICE, SPEICHER), "device_id": DEVICE,
            "anbieter": anbieter, "anbieter_typ": "netzbetreiber",
            "netz": anbieter, "speicher_gb": SPEICHER, "farbe_roh": "Schwarz",
            "farbe_normalisiert": "schwarz", "zustand": "neu",
            "first_seen": "2026-08-01", "last_verified": abgerufen_am,
            "status": "aktiv", "missed_checks": 0,
            "preis_ohne_vertrag": preis, "erstpreis": preis,
            "erstpreis_art": "ohne_vertrag", "erstpreis_am": "2026-08-01",
            "quelle_url": f"https://example.de/{anbieter.lower()}/{DEVICE}",
            "abgerufen_am": abgerufen_am, "verfuegbarkeit": "lieferbar",
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
    listungen = [_listung(a, 1099.00 + i, ab)
                 for i, (a, _t, _n, _r, ab) in enumerate(_BUENDEL)]
    (state / "geraete_db.json").write_text(json.dumps({
        "updated": HEUTE,
        "anbieter": {a: {"laeufe": 4, "funde_gesamt": 1}
                     for a, *_r in _BUENDEL},
        "listungen": listungen}), encoding="utf-8")
    (state / "geraete_preise.jsonl").write_text("", encoding="utf-8")
    buendel = []
    for anbieter, tarif_id, tarif, rate, abgerufen_am in _BUENDEL:
        buendel.append({
            "id": f"buendel--{anbieter.lower()}--{_sku(DEVICE, SPEICHER)}"
                  f"--{tarif_id}",
            "sku_id": _sku(DEVICE, SPEICHER), "anbieter": anbieter,
            "tarif_name": tarif, "tarif_id": tarif_id,
            "tarif_id_guete": "hoch", "tarif_monatlich": 24.99,
            "geraet_zuzahlung": 1.0, "geraet_monatsrate": rate,
            "laufzeit_monate": 24, "anschlusspreis": 0.0,
            "zustand": "neu", "rabatte": [],
            "quelle_url": f"https://example.de/{anbieter.lower()}/{DEVICE}",
            "abgerufen_am": abgerufen_am, "first_seen": HEUTE,
            "last_verified": abgerufen_am})
    (state / "geraete_tco.json").write_text(json.dumps({
        "updated": HEUTE, "buendel": buendel, "sim_only": []}),
        encoding="utf-8")
    tarife = [
        {"anbieter": anbieter, "name": tarif, "tarif_id": tarif_id,
         "art": "mobilfunk", "grundgebuehr": 24.99, "laufzeit_monate": 24,
         "datenvolumen_gb": 10,
         "preisphasen": [{"von_monat": 1, "bis_monat": None,
                          "betrag": 24.99}],
         "dokument_url": f"https://example.de/pib/{tarif_id}",
         "abgerufen_am": HEUTE, "confidence": {}, "fundstellen": {}}
        for anbieter, tarif_id, tarif, _r, _ab in _BUENDEL
    ]
    (state / "tarife.jsonl").write_text(
        "\n".join(json.dumps(t) for t in tarife) + "\n", encoding="utf-8")
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


def _chromium():
    for m in ("/opt/pw-browsers/chromium-*/chrome-linux/chrome",
              str(pathlib.Path.home() / ".cache/ms-playwright"
                  / "chromium*/chrome-linux*/chrome")):
        t = sorted(glob.glob(m))
        if t:
            return t[-1]
    return None


@contextlib.contextmanager
def _server(site):
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
def zeilen(tmp_path_factory):
    sync_playwright = pytest.importorskip(
        "playwright.sync_api", reason="playwright fehlt").sync_playwright
    site = _baue(tmp_path_factory.mktemp("bnd390"))
    exe = _chromium()
    with _server(site) as wurzel, sync_playwright() as p:
        browser = (p.chromium.launch(executable_path=exe) if exe
                   else p.chromium.launch())
        try:
            ctx = browser.new_context(viewport={"width": 390, "height": 1400})
            s = ctx.new_page()
            s.goto(f"{wurzel}/geraete.html", wait_until="networkidle")
            s.wait_for_timeout(300)
            daten = s.evaluate("""() => {
              const rows = [...document.querySelectorAll('#gr-buendel .gr-bnd')];
              return rows.map(row => {
                const name = row.querySelector('.gr-bnd-name');
                const tco = row.querySelector('.gr-bnd-tco');
                const an = row.querySelector('.gr-bnd-an');
                const marke = row.querySelector('.gr-kk-marke');
                if (!name || !tco || !name.getBoundingClientRect().width) {
                  return null;
                }
                const nr = name.getBoundingClientRect();
                const tr = tco.getBoundingClientRect();
                const ar = an.getBoundingClientRect();
                const mr = marke ? marke.getBoundingClientRect() : null;
                const cs = mr ? getComputedStyle(marke) : null;
                return {
                  name: name.textContent, marke: marke ? marke.textContent : null,
                  nameTop: nr.top, tcoTop: tr.top, tcoRight: tr.right,
                  anWidth: ar.width, markeWidth: mr ? mr.width : null,
                  markeHoehe: mr ? mr.height : null,
                  zeilenhoehe: cs ? parseFloat(cs.fontSize) * 1.6 : null,
                };
              }).filter(Boolean);
            }""")
            yield daten
        finally:
            browser.close()


def test_alle_preise_haben_dieselbe_rechte_kante(zeilen):
    assert len(zeilen) == 4, zeilen
    kanten = [round(z["tcoRight"]) for z in zeilen]
    assert max(kanten) - min(kanten) <= 1, (
        f"die Preiszellen haben unterschiedliche rechte Kanten: {zeilen}")


def test_der_preis_liegt_in_jeder_zeile_gleich_zum_namen(zeilen):
    """Nachtrag (Lead-Befund 24.09.2026): NICHT die absolute Hoehe zaehlt
    (an/tco stehen seit dem Grid-Fix je auf einer eigenen vollen Zeile),
    sondern dass der ABSTAND zwischen Namens- und Preiszeile bei GLEICHEM
    Bauplan (mit/ohne Abzeichen) GLEICH ist - vorher bestimmte der Inhalt
    der Preiszelle (Ziffern- und Textlaenge) eine eigene Spaltenaufteilung
    je Zeile, und zwei Zeilen mit identischem Bauplan sahen verschieden
    aus (Preis neben dem Namen vs. eine Zeile tiefer). Ein Abzeichen
    fuegt selbst legitim eine Zeile Hoehe hinzu - verglichen wird darum
    je Gruppe (mit/ohne Abzeichen), nicht ueber beide hinweg."""
    assert len(zeilen) == 4, zeilen
    for hat_marke in (True, False):
        gruppe = [z for z in zeilen if bool(z["marke"]) == hat_marke]
        if len(gruppe) < 2:
            continue
        abstaende = [round(z["tcoTop"] - z["nameTop"]) for z in gruppe]
        assert max(abstaende) - min(abstaende) <= 2, (
            f"Abstand Name->Preis unterscheidet sich innerhalb derselben "
            f"Bauform (Abzeichen={hat_marke}): {gruppe}")


def test_das_abzeichen_steht_auf_einer_zeile(zeilen):
    """Nachtrag (Lead-Befund 24.09.2026): der fruehere Test verglich die
    Abzeichenbreite mit der Breite SEINER EIGENEN Zelle - tautologisch,
    sobald das Abzeichen `width:100%` dieser Zelle traegt, auch wenn die
    Zelle selbst nur ~75 px breit ist. Die eigentliche Regel: der Text
    passt auf EINE Zeile (Rechteckhoehe ~ eine Zeilenhoehe), nicht auf
    zwei bis vier enge Zeilen gestapelt."""
    mit_marke = [z for z in zeilen if z["marke"]]
    assert len(mit_marke) == 2, zeilen  # Vodafone + Telekom
    for z in mit_marke:
        assert z["markeHoehe"] <= z["zeilenhoehe"] * 1.5, (
            f"das Abzeichen steht nicht auf einer Zeile: {z}")


def test_die_alte_telekom_zeile_traegt_wirklich_die_alte_marke(zeilen):
    """Gegenprobe: die Fixture trifft wirklich `ALT_AB_TAGEN` - sonst
    testet `test_das_abzeichen_hat_die_volle_breite_der_an_zelle` an
    einer Zeile ohne Marke vorbei."""
    telekom = [z for z in zeilen if z["name"] == "Telekom"]
    assert telekom, zeilen
    assert telekom[0]["marke"] == geraete_tco_karten.alt_marke_fuer(
        ALT_ABGERUFEN), telekom
    assert geraete_tco_karten.alter_in_tagen(
        ALT_ABGERUFEN, HEUTE) > geraete_tco_karten.ALT_AB_TAGEN
