"""E5 (AUFTRAG_GERAETE_EINE_SEITE_V2 §7): die fünf Test-Leer-Sicherungen.

Der O4-Evaluator-Befund (S3), der diese Datei begründet: Zähler der
Geräteseite hatten keine in-sich-Leere-Sicherung - ein stiller Leerzustand
(toter Adapter, leerer Store, gescheiterter Render) hätte die Suite grün
gelassen und wochenlang live gestanden. JEDE Zahlensektion der Seite
braucht einen BENANNTEN Leerzustand, der gerendert UND getestet wird.
Seit dem Neuentwurf der Geräteseite (29.09.2026, eine Kosten-Rangliste)
sind das zwei:

  1. Kosten-Rangliste ohne Bündel  -> "Keine Gerätepreise."
  2. Export ohne Zeilen            -> der Link im Fuß bleibt, die Dateien
     tragen ihre Kopfspur

Jeder Test prüft das GERENDERTE Markup - ein Dict-Vergleich sähe einen
fehlenden Vorlagen-Zweig nicht (CLAUDE.md §6: der Fehler entstand zwischen
aufbereiten() und der Vorlage).
"""
from __future__ import annotations

import json
import pathlib

import pytest
import yaml
from bs4 import BeautifulSoup

from telco_radar.report.html import render_site

WURZEL = pathlib.Path(__file__).resolve().parents[1]
HEUTE = "2026-09-17"

_KATALOG = {"geraete": [
    {"hersteller": "Apple", "modell": "iPhone 15", "generation": 15,
     "marktstart": "2023-09-22", "speicher": [128], "segment": "premium"},
]}
_FARBEN = {"farben": {"schwarz": ["Schwarz", "Black"]}}
_QUELLEN = {"anbieter": [
    {"name": "o2", "typ": "netzbetreiber", "rang": 1,
     "methode": "json_endpunkt", "basis_url": "https://www.o2online.de",
     "einstiege": [{"url": "https://www.o2online.de/e-shop/",
                    "label": "Katalog", "kind": "static"}]},
    {"name": "Vodafone", "typ": "netzbetreiber", "rang": 2, "eigen": True,
     "methode": "json_endpunkt", "basis_url": "https://www.vodafone.de",
     "einstiege": [{"url": "https://api.vodafone.de/glados/v2/hardware",
                    "label": "Liste", "kind": "static"}]},
    {"name": "Saturn", "typ": "handel", "gruppe": "Ceconomy", "rang": 2,
     "methode": "saturn_brand", "aktiv": True,
     "basis_url": "https://www.saturn.de",
     "einstiege": [{"url": "https://www.saturn.de/handys",
                    "label": "Handys", "kind": "static"}]},
]}

SKU = "apple-iphone-15-128gb-schwarz"
DATEIEN = ("geraete-aktuell.csv", "geraete-historie.csv", "geraete-tco.csv",
           "wettbewerbsradar.csv",
           # P3: die zwei Modell-Exporte des Katalogs (je Ansicht eine
           # Datei, eine Zeile je Modell)
           "geraete-modell-barpreis.csv", "geraete-modell-tco.csv")


def _listung(anbieter, sku, preis):
    speicher = int(sku.split("-")[-2].replace("gb", ""))
    return {"id": f"{anbieter.lower()}--{sku}", "sku_id": sku,
            "device_id": "-".join(sku.split("-")[:-2]),
            "anbieter": anbieter,
            "anbieter_typ": ("handel" if anbieter == "Saturn"
                             else "netzbetreiber"),
            "speicher_gb": speicher, "farbe_roh": "Schwarz",
            "farbe_normalisiert": "schwarz", "zustand": "neu",
            "first_seen": "2026-08-20", "last_verified": HEUTE,
            "status": "aktiv", "missed_checks": 0,
            "preis_ohne_vertrag": preis, "erstpreis": preis,
            "erstpreis_art": "ohne_vertrag", "erstpreis_am": "2026-08-20",
            "quelle_url": f"https://example.de/{anbieter.lower()}/{sku}",
            "abgerufen_am": HEUTE, "verfuegbarkeit": "lieferbar",
            "confidence": "hoch", "einstiege": ["https://example.de/l"]}


def _text(knoten) -> str:
    """Der Text eines Knotens mit zusammengefuehrten Leerzeichen - die
    Vorlage bricht Zeilen um, und ein Substring, der über einen Umbruch
    geht, trifft im rohen get_text() nicht. Wer Leerzustandssaetze
    wortgleich prueft, muss erst falten."""
    return " ".join(knoten.get_text(" ", strip=True).split())


def _seite(tmp_path: pathlib.Path, listungen: list) -> dict:
    """Eine komplette Site aus gestelltem Bestand. `listungen == []` ist
    der Leer-Fall (kein Gerät erfasst, kein Bündel); die Vorlage-Listung
    ist der Ohne-Alarm-Fall (Vodafone ist am günstigsten)."""
    root = tmp_path / "leer-seite"
    (root / "config").mkdir(parents=True)
    for name, daten in (("geraete_katalog.yaml", _KATALOG),
                        ("farben.yaml", _FARBEN),
                        ("geraete_quellen.yaml", _QUELLEN)):
        (root / "config" / name).write_text(
            yaml.safe_dump(daten, allow_unicode=True, sort_keys=False),
            encoding="utf-8")
    state = root / "data" / "state"
    state.mkdir(parents=True)
    (state / "geraete_db.json").write_text(json.dumps({
        "updated": HEUTE,
        "anbieter": {n: {"laeufe": 4, "funde_gesamt": 1}
                     for n in ("Vodafone", "Saturn")} if listungen else {},
        "listungen": listungen}), encoding="utf-8")
    (state / "geraete_preise.jsonl").write_text(
        "".join(json.dumps({"listung_id": e["id"], "datum": HEUTE,
                            "preis_ohne_vertrag": e["preis_ohne_vertrag"],
                            "quelle_url": e["quelle_url"]}) + "\n"
                for e in listungen), encoding="utf-8")
    (state / "geraete_tco.json").write_text(
        json.dumps({"updated": HEUTE, "buendel": [], "sim_only": []}),
        encoding="utf-8")
    (state / "tarife.jsonl").write_text("", encoding="utf-8")
    reports = root / "data" / "reports"
    reports.mkdir(parents=True)
    (reports / f"{HEUTE}.json").write_text(json.dumps({
        "date": HEUTE, "language": "de",
        "briefing_md": "## Auf einen Blick\n\n- Nichts.\n",
        "stats": {}, "regions": []}), encoding="utf-8")
    (reports / f"{HEUTE}.md").write_text("# B\n", encoding="utf-8")
    site = root / "site"
    render_site(site, reports)
    return {"html": (site / "geraete.html").read_text(encoding="utf-8"),
            "site": site}


@pytest.fixture(scope="module")
def leer(tmp_path_factory) -> BeautifulSoup:
    """Der Ganz-Leer-Fall: kein Gerät, kein Bündel, kein Preis - die
    Seite muss BENANNT leer stehen, nicht still."""
    seite = _seite(tmp_path_factory.mktemp("leer-leer"), [])
    return BeautifulSoup(seite["html"], "html.parser")


@pytest.fixture(scope="module")
def ohne_alarm(tmp_path_factory) -> BeautifulSoup:
    """Bestand MIT Daten, aber Vodafone ist überall am günstigsten: die
    Alarm-Sektion steht mit Nullern und ihrem Leer-Satz da - 'kein
    Wettbewerber günstiger' ist eine Aussage, keine kaputte Tafel."""
    seite = _seite(tmp_path_factory.mktemp("leer-alarm"), [
        _listung("Vodafone", SKU, 679.90),
        _listung("Saturn", SKU, 709.90),
    ])
    return BeautifulSoup(seite["html"], "html.parser")


# ---- 1. Kosten-Rangliste ohne Bündel ---------------------------------------

@pytest.mark.parametrize("fall", ["leer", "ohne_alarm"])
def test_kosten_ohne_buendel_nennt_den_leerzustand(fall, request):
    """Seit dem Neuentwurf (29.09.2026) ist die Kosten-Rangliste die EINE
    Zahlensektion der Seite. Ohne Bündel sagt sie BENANNT, dass es keine
    Gerätepreise gibt - am Ganz-Leer-Bestand und am Bestand mit Listungen,
    aber ohne Bündel. Kein Datenblock, keine Zeile, keine Wahl-Leiste:
    nichts, das aus nichts gerechnet wäre."""
    seite = request.getfixturevalue(fall)
    sektion = seite.select_one("#kosten")
    assert sektion is not None, "#kosten fehlt - der Test prüft nichts"
    leer_satz = sektion.select_one(".kv-nichts")
    assert leer_satz is not None, "der benannte Leerzustand fehlt"
    assert _text(leer_satz) == "Keine Gerätepreise.", _text(leer_satz)
    assert seite.select_one("#kv-daten") is None, (
        "ohne Bündel steht ein Datenblock da - gerechnet aus nichts")
    assert not seite.select(".kv-zeile"), (
        "ohne Bündel stehen Zeilen in der Rangliste")
    assert seite.select_one("#kv-wahl") is None, (
        "ohne Bündel steht eine Auswahl ohne Auswahlmenge da")


# ---- 2. Export ohne Zeilen -------------------------------------------------

def test_export_link_steht_auch_im_leerzustand(leer, leer_site):
    """Der Export-Link im Fuß der Seite verschwindet im Leerzustand nicht
    still (Modulkopf geraete_export: ein fehlender Download wäre die
    schlechtere Auskunft als ein leerer) - und er zeigt auf eine Datei,
    die es gibt."""
    links = leer.select(".kv-fuss a[download]")
    assert len(links) == 1, f"{len(links)} Export-Links im Leerzustand"
    ziel = links[0].get("href")
    assert ziel == "exporte/geraete-tco.csv", ziel
    assert (leer_site / ziel).exists(), f"{ziel} fehlt im Leerzustand"


@pytest.fixture(scope="module")
def leer_site(tmp_path_factory) -> pathlib.Path:
    return _seite(tmp_path_factory.mktemp("leer-dateien"), [])["site"]


def test_export_dateien_haben_im_leerzustand_nur_die_kopfspur(leer_site):
    """Jede der vier Dateien existiert, trägt das BOM (Excel) und GENAU
    die Kopfzeile - keine Zeile, keine kaputte Datei, keine fehlende."""
    for name in DATEIEN:
        pfad = leer_site / "exporte" / name
        assert pfad.exists(), f"exporte/{name} fehlt im Leerzustand"
        roh = pfad.read_bytes()
        assert roh[:3] == b"\xef\xbb\xbf", f"kein BOM: {name}"
        zeilen = roh.decode("utf-8-sig").splitlines()
        assert len(zeilen) == 1 and zeilen[0].count(";") >= 5, (
            f"{name}: {len(zeilen)} Zeilen statt einer Kopfspur")
