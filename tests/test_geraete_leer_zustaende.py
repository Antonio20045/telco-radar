"""E5 (AUFTRAG_GERAETE_EINE_SEITE_V2 §7): die fünf Test-Leer-Sicherungen.

Der O4-Evaluator-Befund (S3), der diese Datei begründet: fünf Zähler der
Geräteseite hatten keine in-sich-Leere-Sicherung - ein stiller Leerzustand
(toter Adapter, leerer Store, gescheiterter Render) hätte die Suite grün
gelassen und wochenlang live gestanden. Die Zuordnung folgt dem Muster des
Auftrags: JEDE Zahlensektion der EINEN Seite braucht einen BENANNTEN
Leerzustand, der gerendert UND getestet wird -

  1. Zeitreihe/TCO-Vergleich ohne Bündel      -> "Es gibt heute kein
     einziges Bündel aus Gerät und Tarif im Bestand" (template)
  2. Radar ohne Alarme                         -> "Zu dieser Auswahl ist
     bei keiner Modell-Speicher-Kombination ein Wettbewerber günstiger"
     (OFFEN sichtbar, nicht hidden)
  3. Radar ohne Abweichungszeilen              -> "Noch keine Modelle mit
     Bündeldaten erhoben" (seit E5: die Sektion rendert ohne Bündel, bis
     dahin fehlte sie still)
  4. Katalog leer                              -> "Noch keine Geräte
     erfasst" (Seitenzustand; die Tafel-Kacheln fehlen dann komplett)
  5. Export ohne Zeilen                        -> die vier Dateien mit
     Kopfspur und der Null AUF DER SEITE neben jedem Link

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


# ---- 1. Zeitreihe/TCO-Vergleich ohne Bündel -------------------------------

def test_zeitreihe_ohne_buendel_nennt_den_leerzustand(ohne_alarm):
    """Der Vergleichs-Reiter sagt BENANNT, dass es nichts zu rechnen
    gibt - kein still leeres Wahl-Schuld-Feld, keine leere Gruppe.
    Der Fall: Bestand DA (hat_daten wahr), aber kein Bündel - nur dann
    steht die Tafel überhaupt; am Ganz-Leer-Bestand antwortet die Seite
    als Ganzes (Sicherung 4)."""
    tafel = ohne_alarm.select_one("#tafel-tco")
    assert tafel is not None, "#tafel-tco fehlt - der Test prüft nichts"
    text = _text(tafel)
    assert "kein einziges Bündel aus Gerät und Tarif" in text, (
        "der benannte Leerzustand des Vergleichs-Reiters fehlt")
    assert not ohne_alarm.select("#gr-zr-gruppe svg"), (
        "ohne Bündel steht ein Graph da - gezeichnet aus nichts")
    assert not ohne_alarm.select("#gr-zr-gruppe .gr-zr-antwort"), (
        "ohne Bündel steht ein Antwort-Satz da - gerechnet aus nichts")


# ---- 2. Radar ohne Alarme ---------------------------------------------------

def test_radar_ohne_alarme_nennt_den_leerzustand(ohne_alarm):
    """Die drei WARN-Kacheln zeigen Null, und der Leer-Satz steht OFFEN
    da (kein hidden-Attribut): 'kein Wettbewerber günstiger' ist die
    Aussage des Leerzustands, kein Filterrest. Die Kachel 'Bestpreis'
    darf dabei zählen - sie ist die ehrliche Gegenseite derselben
    Menge, nicht ein Alarm."""
    sektion = ohne_alarm.select_one("#wr-alarme")
    assert sektion is not None, (
        "die Alarm-Sektion fehlt komplett - stiller Leerzustand")
    chips = {c.select_one("span").get_text(strip=True):
             c.select_one("b").get_text(strip=True)
             for c in sektion.select(".gr-chip")}
    assert set(chips) == {"Kritisch", "Mittel", "Gering", "Bestpreis"}, chips
    assert chips["Kritisch"] == chips["Mittel"] == chips["Gering"] == "0", (
        chips)
    assert chips["Bestpreis"] != "0", (
        "die Gegenprobe fehlt: Vodafone ist am günstigsten, die Kachel "
        "muss es zählen - sonst prüft der Test einen Bestand ohne jede "
        "Vergleichung")
    leer_satz = sektion.select_one(".gr-a-leer")
    assert leer_satz is not None, "der Leer-Satz der Alarmtabelle fehlt"
    assert not leer_satz.has_attr("hidden"), (
        "der Leer-Satz steht versteckt da - bei null Alarmen ist er die "
        "Aussage, kein Filterfall")
    assert "ein Wettbewerber günstiger" in _text(leer_satz), (
        "der Leer-Satz nennt nicht den Grund (kein Wettbewerber günstiger)")
    # Der Satz NENNT die Vergleichsmenge - die Tafel ist nicht leer,
    # weil nichts gemessen wurde.
    assert "stehen einem Wettbewerber gegenüber" in _text(sektion)


# ---- 3. Radar ohne Abweichungszeilen ---------------------------------------

def test_radar_ohne_abweichung_nennt_den_leerzustand(ohne_alarm):
    """Ohne Bündel rendert die Abweichungs-Sektion ihren benannten
    Leerzustand. Bis E5 fehlte die ganze Sektion still, sobald
    `hat_daten` falsch war - der O4-Evaluator-Fall: der tote Adapter,
    der wochenlang als grüne Leer-Tafel steht."""
    sektion = ohne_alarm.select_one("#wr-abweichung")
    assert sektion is not None, (
        "die Abweichungs-Sektion fehlt ohne Bündel - genau der stille "
        "Leerzustand, den die E5-Sicherung verbietet")
    text = _text(sektion)
    assert "Noch keine Modelle mit Bündeldaten erhoben" in text, (
        "der benannte Leerzustand der Abweichungs-Liste fehlt")
    assert not sektion.select("tr.gr-a-zeile"), (
        "ohne Bündel stehen Zeilen in der Abweichungs-Liste")


# ---- 4. Katalog leer -------------------------------------------------------

def test_katalog_leer_nennt_den_leerzustand(leer, ohne_alarm):
    """Ohne jeden Bestand sagt die SEITE benannt, dass nichts erfasst
    ist (die Reiter-Tafeln fehlen dann alle - der Leerzustand ist der
    ganze Seitenkörper). Und der Tabellen-Leersatz des Katalogs ist ein
    FILTER-Satz: MIT Zeilen steht er versteckt, damit app.js ihn bei
    Filterung steuert - beides wird hier zusammen geprüft."""
    text = _text(leer)
    assert "Noch keine Geräte erfasst" in text, (
        "der Seiten-Leerzustand fehlt - die Seite steht still leer")
    assert not leer.select("#gr-katalogtabelle .gr-k-zeile"), (
        "der Katalog trägt Zeilen, obwohl kein Bestand da ist")

    # Gegenprobe am Bestand MIT Zeilen: der Leer-Satz der Tafel ist
    # versteckt (Filter-Satz), die Tabelle trägt ihre Zeile.
    satz = ohne_alarm.select_one("#tafel-katalog .gr-a-leer")
    assert satz is not None, "der Filter-Leersatz fehlt am vollen Katalog"
    assert satz.has_attr("hidden"), (
        "am vollen Katalog steht der Leer-Satz offen - er gehört der "
        "Filterung, nicht dem Vorgabestand")
    assert ohne_alarm.select("#gr-katalogtabelle .gr-k-zeile"), (
        "der Katalog trägt keine Zeile, obwohl der Bestand eine hat - "
        "Lookup ins Leere, der Test würde sonst nichts prüfen")


# ---- 5. Export ohne Zeilen -------------------------------------------------

def test_export_ohne_zeilen_nennt_die_null(leer):
    """Alle Export-Dateien mit Kopfspur und null Zeilen - und die SEITE
    nennt die Null neben jedem Link, statt den Export still verschwinden
    zu lassen (Modulkopf geraete_export: ein fehlender Download wäre die
    schlechtere Auskunft als ein leerer). Bis P3 waren es vier Dateien,
    der Katalog auf Modellebene hat zwei weitere gebracht (eine je
    Ansicht)."""
    links = leer.select("section.page-hero a[href^='exporte/']")
    assert len(links) == len(DATEIEN), (
        f"{len(links)} Export-Links im Leerzustand - {len(DATEIEN)} Dateien "
        "gehören da hin")
    for a in links:
        assert "0" in a.get_text(), (
            f"Link ohne Null neben der Zeilenzahl: {a.get_text(strip=True)}")
    # Vier Links, vier verschiedene Dateien - keine fehlt, keine doppelt.
    ziele = {a.get("href") for a in links}
    assert ziele == {f"exporte/{n}" for n in DATEIEN}, ziele


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
