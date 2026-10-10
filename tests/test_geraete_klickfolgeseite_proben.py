"""Proben auf der Folgeseite der Klick-Erkundung (Schnitt 8a, Vodafone-Tarifauswahl).

Ein lokaler Server auf 127.0.0.1 liefert BEISPIEL-Seiten, von Hand geschrieben, kein
echter Anbieter: die Produktseite mit dem Link „Zur Tarifauswahl“ und eine Tarifauswahl
mit Radio-Optionen wie bei Vodafone (Eingabe plus Label, ``option-picker``). Ein Wechsel
des Tarifs lädt dessen Preis per GET; eine Option versucht dazu ein POST. Geprüft wird:
nur die Optionen von ``weiter.proben`` werden geklickt, die gewählte und eine mit
Kaufwort nicht, je Probe stehen Anfragen, geänderte €-Texte und die Übernahme im
Protokoll, kein POST erreicht den Server. Ohne ``proben`` bleibt es bei keiner Probe.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from klickserver import JETZT, Antwort, html, klickserver, umleitung

from telco_radar.collect.geraete import klickfolgeseite
from telco_radar.collect.geraete.klickerkundung import erkunde_anbieter
from telco_radar.collect.geraete.klickziele import Erkundungsziel, Seitenziel, Weiter

OFFEN = "User-agent: *\nDisallow:\n"
TAG = JETZT.date().isoformat()
TARIFE = '#tarife div:has(> input[name="tarif"]) > label'
MIT = Weiter("#angebot a.primaer", "Zur Tarifauswahl", TARIFE)
OHNE = Weiter("#angebot a.primaer", "Zur Tarifauswahl")
PREISE = {"267": "34,95", "268": "44,95", "269": "54,95", "270": "64,95"}
AUSGANG = """<!doctype html><html><body><h1>Beispielhandy X</h1>
<section id="preis"><p>Monatliche Rate <b>35,00 €</b></p></section>
<section id="angebot"><a class="primaer" href="/tarife/start">Zur Tarifauswahl</a>
</section></body></html>"""
FOLGE = """<!doctype html><html><body><h1>Tarifauswahl</h1>
<div id="tarife">
 <div><input type="radio" name="tarif" id="t267" value="267" checked>
  <label for="t267">10 GB</label></div>
 <div><input type="radio" name="tarif" id="t268" value="268">
  <label for="t268">25 GB</label></div>
 <div><input type="radio" name="tarif" id="t269" value="269">
  <label for="t269">50 GB</label></div>
 <div><input type="radio" name="tarif" id="t270" value="270">
  <label for="t270">Jetzt kaufen</label></div>
</div>
<section id="preis"><p>Tarif monatlich <span id="tp">34,95 €</span></p></section>
<script>
for (const r of document.querySelectorAll('input[name="tarif"]')) {
  r.addEventListener("change", () => {
    fetch(`/api/tarif?id=${r.value}`).then((a) => a.json()).then((d) => {
      document.getElementById("tp").innerText = `${d.preis} €`;
    });
    if (r.value === "269") {
      fetch("/api/korb", {method: "POST", body: "{}"}).catch(() => {});
    }
  });
}
</script></body></html>"""


def _antworte(pfad: str) -> Antwort:
    teile = urlsplit(pfad)
    if teile.path.startswith("/handy/"):
        return html(AUSGANG)
    if teile.path == "/tarife/start":
        return umleitung("/tarife/alle.html")
    if teile.path == "/tarife/alle.html":
        return html(FOLGE)
    if teile.path == "/api/tarif":
        tarif = parse_qs(teile.query)["id"][0]
        return Antwort(200, "application/json", json.dumps({"preis": PREISE[tarif]}))
    return Antwort(404)


def _erkunde(chromium, server, weiter: Weiter, ausgabe: Path) -> dict:
    seite = Seitenziel("beispielhandy-x", 256, server.adresse("/handy/x"), weiter)
    ziel = Erkundungsziel("beispiel", "Beispielanbieter", (seite,), None, 0.0)
    ende = time.monotonic() + 600
    return erkunde_anbieter(
        chromium, ziel, lambda: JETZT, lambda url: (200, OFFEN), ausgabe, ende
    )


def _klicks(ausgabe: Path, folge: dict) -> dict:
    ordner = ausgabe / "beispiel" / TAG
    return json.loads((ordner / folge["dateien"]["klicks"]).read_text("utf-8"))


def test_proben_klicken_nur_die_nicht_gewaehlten_tarife(chromium, tmp_path):
    with klickserver(_antworte) as server:
        index = _erkunde(chromium, server, MIT, tmp_path)

    folge = index["seiten"][1]
    assert (folge["status"], folge["grund"]) == ("gelesen", None)
    assert folge["weiter"]["proben"] == TARIFE
    klicks = _klicks(tmp_path, folge)
    assert klicks["vermerk"] == f"{klickfolgeseite.MIT_PROBEN} {TARIFE}"
    proben = klicks["proben"]
    assert [(p["text"], p["wert"]) for p in proben] == [
        ("25 GB", "268"),
        ("50 GB", "269"),
    ]
    for probe in proben:
        assert probe["fehler"] is None and probe["navigiert"] is None
        assert probe["uebernommen"] == "ja"
        adressen = [a["url"] for a in probe["anfragen"]]
        assert server.adresse(f"/api/tarif?id={probe['wert']}") in adressen
        nachher = [a["nachher"] for a in probe["preise_geaendert"]]
        assert any(PREISE[probe["wert"]] in (n or "") for n in nachher)
    assert server.mit("/api/tarif") == ["/api/tarif?id=268", "/api/tarif?id=269"]
    assert server.posts == []


def test_ohne_proben_keine_probe_auf_der_folgeseite(chromium, tmp_path):
    with klickserver(_antworte) as server:
        index = _erkunde(chromium, server, OHNE, tmp_path)

    folge = index["seiten"][1]
    klicks = _klicks(tmp_path, folge)
    assert (klicks["proben"], klicks["vermerk"]) == ([], klickfolgeseite.OHNE_PROBEN)
    assert "proben" not in folge["weiter"]
    assert server.mit("/api/tarif") == []
