"""Einwilligungsabfrage vor jedem Klick: Erkundung, Folgeseite und Klick-Crawler.

Muster aus der Erkundung vom 07.10.2026 (Zweig ``klick-erkundung``, Commit a9b45f5a,
``erkundung/1und1/2026-10-07/``): seit das Tor Skripte von Hosts mit robots.txt 403
lädt, legt 1&1 eine Einwilligungswand über die Seite (``bedienelemente-1.json``
Elemente 205–208: ``#consent-wall``, Knopf „Ablehnen“ mit ``aria-label`` „Cookies
ablehnen“). Der zugängliche Name ist das ``aria-label``; die Ablehnung fand ihn nicht
(``klicks-1.json``: „kein Ablehnen-Knopf sichtbar“), jeder Klick dahinter lief in die
Frist, auch der Weiter-Klick der Folgeseiten 3 und 4 (``index.json``). Die Seiten hier
sind BEISPIELE, von Hand geschrieben, kein echter Anbieter; ein lokaler Server liefert
sie. Gegenprobe: eine Wand ohne Ablehnen-Knopf wird nie bestätigt und nie umgangen.
"""

from __future__ import annotations

import json
import time

import pytest
from klickbeispiel import KARTE, laufe, nach_auswahl, preis, seite
from klickserver import JETZT, Antwort, html, klickserver

from telco_radar.collect.geraete import klickfolgeseite, klickproben
from telco_radar.collect.geraete.klickerkundung import erkunde_anbieter
from telco_radar.collect.geraete.klickkarte import klickkarte_aus_daten
from telco_radar.collect.geraete.klickziele import Erkundungsziel, Seitenziel, Weiter

pytestmark = pytest.mark.browser

OFFEN = "User-agent: *\nDisallow:\n"
TAG = JETZT.date().isoformat()
LINK = Weiter("#angebot a.primaer", "Zur Tarifauswahl")
ABLEHNEN = '<button id="optout" aria-label="Cookies ablehnen">Ablehnen</button>'
WAND = """<div id="consent-wall" style="position:fixed;inset:0;z-index:9;
  background:rgba(0,0,0,.5)"><p>Cookie-Einstellungen</p>ABLEHNEN
  <button id="optin" aria-label="Cookies bestätigen">Bestätigen</button></div>
<script>
for (const k of document.querySelectorAll("#consent-wall button")) {
  k.addEventListener("click", () => document.getElementById("consent-wall").remove());
}
</script>"""
AUSGANG = """<!doctype html><html><body>
<h1>Beispielhandy X</h1>
<div id="speicher" aria-label="Speicher">
 <button data-wert="256" aria-pressed="true">256 GB</button>
 <button data-wert="512" aria-pressed="false">512 GB</button>
</div>
<section id="preis"><p>Monatliche Rate <b>35,00 €</b></p></section>
<section id="angebot"><a class="primaer" href="/tarife/alle.html">Zur Tarifauswahl</a>
</section>
WAND
</body></html>"""
FOLGE = """<!doctype html><html><body><h1>Tarifauswahl</h1>
<div id="tarif" aria-label="Tarif">
 <button data-wert="S" aria-pressed="true">Tarif S</button>
 <button data-wert="M" aria-pressed="false">Tarif M</button>
</div><p>35,99 €</p></body></html>"""
KONFIG = """
<div id="konfig">
  <label class="kachel"><input type="radio" name="hw.storage" value="128" hidden
    checked>128 GB</label>
  <label class="kachel"><input type="radio" name="hw.storage" value="256"
    hidden>256 GB</label>
</div>
<section id="preis"></section>
WAND"""
KONFIG_SKRIPT = """
const auswahl = {speicher: "128", tarif: "S", laufzeit: "36"};
for (const i of document.querySelectorAll("#konfig input")) {
  i.addEventListener("change", () => { auswahl.speicher = i.value; lade(auswahl); });
}
lade(auswahl);"""
KNOEPFE = {
    "speicher": {
        "selektor": "#konfig label.kachel",
        "wert_in": "input",
        "wert": "value",
        "gewaehlt": {"passt": ":has(input:checked)"},
    },
    "tarif": {"fest": "S"},
    "laufzeit": {"fest": 36},
}


def _wand(ablehnen: bool) -> str:
    return WAND.replace("ABLEHNEN", ABLEHNEN if ablehnen else "")


def _antworte(ablehnen: bool):
    produkt = AUSGANG.replace("WAND", _wand(ablehnen))

    def antworte(pfad: str) -> Antwort:
        if pfad.startswith("/handy/"):
            return html(produkt)
        if pfad.startswith("/tarife/"):
            return html(FOLGE)
        return Antwort(404)

    return antworte


def _erkunde(chromium, server, ausgabe) -> dict:
    seiten = (Seitenziel("beispielhandy-x", 256, server.adresse("/handy/x"), LINK),)
    ziel = Erkundungsziel("beispiel", "Beispielanbieter", seiten, None, 0.0)
    ende = time.monotonic() + 600
    return erkunde_anbieter(
        chromium, ziel, lambda: JETZT, lambda url: (200, OFFEN), ausgabe, ende
    )


def _klicks(ausgabe, nummer: int) -> dict:
    datei = ausgabe / "beispiel" / TAG / f"klicks-{nummer}.json"
    return json.loads(datei.read_text(encoding="utf-8"))


@pytest.fixture
def kurze_klicks(monkeypatch):
    monkeypatch.setattr(klickproben, "KLICK_FRIST_MS", 1000)
    monkeypatch.setattr(klickfolgeseite, "KLICK_FRIST_MS", 1000)


def test_ablehnen_mit_aria_label_gibt_den_weiter_klick_frei(
    chromium, tmp_path, kurze_klicks
):
    with klickserver(_antworte(ablehnen=True)) as server:
        index = _erkunde(chromium, server, tmp_path)

    erste, folge = index["seiten"]
    assert (folge["status"], folge["grund"]) == ("gelesen", None)
    assert folge["weiter"]["nach"] == server.adresse("/tarife/alle.html")
    for nummer in (1, 2):
        assert _klicks(tmp_path, nummer)["einwilligung"]["geklickt"] == "Ablehnen"
    assert [p["fehler"] for p in _klicks(tmp_path, 1)["proben"]] == [None]
    assert erste["status"] == "gelesen"


def test_wand_ohne_ablehnen_wird_weder_bestaetigt_noch_umgangen(
    chromium, tmp_path, kurze_klicks
):
    with klickserver(_antworte(ablehnen=False)) as server:
        index = _erkunde(chromium, server, tmp_path)

    folge = index["seiten"][1]
    assert folge["status"] == "befund"
    assert folge["grund"].startswith("Weiter-Knopf nicht klickbar")
    assert server.mit("/tarife/") == []
    einwilligung = _klicks(tmp_path, 2)["einwilligung"]
    assert einwilligung == {"geklickt": None, "grund": "kein Ablehnen-Knopf sichtbar"}


def _preise(frage: dict) -> dict:
    return {
        "auswahl": {"speicher": frage["speicher"], "tarif": "S", "laufzeit": 36},
        "preis": preis(frage["speicher"], "S", 36),
    }


def _karte():
    daten = {**KARTE, "knoepfe": KNOEPFE}
    return klickkarte_aus_daten(daten, "B")


def test_klick_crawler_lehnt_die_einwilligung_ab_und_klickt_dann(chromium):
    html_seite = seite(KONFIG.replace("WAND", _wand(True)), KONFIG_SKRIPT)

    lauf, _ = laufe(chromium, html_seite, _preise, _karte())

    ergebnisse = nach_auswahl(lauf)
    assert lauf.status == "gelesen", lauf.grund
    assert {k: e.status for k, e in ergebnisse.items()} == {
        ("128", "S", 36): "erfasst",
        ("256", "S", 36): "erfasst",
    }
    assert ergebnisse[("256", "S", 36)].werte.rate == 35.0


def test_klick_crawler_umgeht_eine_wand_ohne_ablehnen_nicht(chromium):
    html_seite = seite(KONFIG.replace("WAND", _wand(False)), KONFIG_SKRIPT)

    lauf, server = laufe(chromium, html_seite, _preise, _karte(), frist_ms=1000)

    ergebnisse = nach_auswahl(lauf)
    assert ergebnisse[("128", "S", 36)].status == "erfasst"
    zweite = ergebnisse[("256", "S", 36)]
    assert zweite.status == "nicht_erfasst"
    assert zweite.grund.startswith("Knopf für speicher nicht klickbar")
    assert all("speicher=256" not in a for a in server.mit("/api/preis"))
