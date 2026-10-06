"""Nebenwege einer Produktseite: robots.txt und Crawl-delay gelten für jede Anfrage.

Fälle aus der zweiten Prüfrunde zu Schritt 4: WebSocket, EventSource, Beacon, Worker,
Prefetch, Speculation Rules (im Dokument, nachgeladen und als Kopfzeile), iframe und
Stylesheet erreichen keinen gesperrten Pfad; Skripte und Stylesheets warten den
Crawl-delay ab wie Seite und Preisantwort; Datenkanäle gehen gar nicht hinaus; eine
gescheiterte Preisanfrage stört den Lauf. Ein lokaler Server auf 127.0.0.1 liefert
BEISPIEL-Seiten, von Hand geschrieben; keine Anfrage verlässt den Rechner.
"""

from __future__ import annotations

import json
import time

import pytest
from klickserver import Antwort, html, karte, klickserver, laufe

OFFEN = "User-agent: *\nDisallow:\n"
GESPERRT = "User-agent: *\nDisallow: /privat/\n"
SEITE = """<!doctype html><html><head>KOPF</head><body>
<h1 id="kanarie">Beispielhandy X</h1>
<div id="speicher"><button data-wert="128" aria-pressed="true">128 GB</button></div>
<div id="tarif"><button data-wert="S" aria-pressed="true">Tarif S</button></div>
<div id="laufzeit"><button data-wert="24" aria-pressed="true">24 Monate</button></div>
<section id="preis"></section>
<script>
fetch("PREIS?speicher=128").then(r => r.json()).then(d => {
  document.getElementById("preis").innerText = "Monatliche Rate " + d.rate + ",00 €";
}).catch(() => {});
ZUSATZ
</script></body></html>"""
ANTWORT = {
    "url_muster": r"/api/preis\?",
    "pfade": {"rate": "rate"},
    "parameter": {"speicher": "speicher"},
}
SPEKULATION = '{"prefetch": [{"source": "list", "urls": ["/privat/spekulation"]}]}'
NACHGELADEN = """const s = document.createElement("script");
s.type = "speculationrules";
s.textContent = JSON.stringify({prefetch: [{source: "list", urls: ["/privat/nach"]}]});
document.head.appendChild(s);"""
IFRAME = """const f = document.createElement("iframe");
f.src = "/privat/iframe";
document.body.appendChild(f);"""
WEBSOCKET = "try { new WebSocket(`ws://${location.host}/privat/ws`); } catch (e) {}"
NEBENWEGE = {
    "websocket": ("", WEBSOCKET),
    "eventsource": ("", 'new EventSource("/privat/sse");'),
    "beacon": ("", 'navigator.sendBeacon("/privat/beacon", "x");'),
    "worker": ("", 'new Worker("/w.js");'),
    "shared_worker": ("", 'new SharedWorker("/s.js").port.start();'),
    "prefetch": ('<link rel="prefetch" href="/privat/prefetch">', ""),
    "spekulation": (f'<script type="speculationrules">{SPEKULATION}</script>', ""),
    "spekulation_nachgeladen": ("", NACHGELADEN),
    "spekulation_kopf": ("", ""),
    "iframe": ("", IFRAME),
    "stylesheet": ('<link rel="stylesheet" href="/privat/css">', ""),
}


def _seite(kopf="", zusatz="", preis="/api/preis"):
    return SEITE.replace("KOPF", kopf).replace("ZUSATZ", zusatz).replace("PREIS", preis)


@pytest.mark.parametrize("weg", list(NEBENWEGE))
def test_nebenweg_erreicht_keinen_gesperrten_pfad(chromium, weg):
    kopf, zusatz = NEBENWEGE[weg]
    seite = _seite(kopf, zusatz)
    kopfzeile = {"Speculation-Rules": '"/privat/regeln.json"'}
    regeln = kopfzeile if weg.endswith("kopf") else {}

    def antworte(pfad: str) -> Antwort:
        if pfad == "/handy/x":
            return Antwort(200, "text/html; charset=utf-8", seite, regeln)
        if pfad == "/w.js":
            return Antwort(200, "text/javascript", "fetch('/privat/worker');")
        if pfad == "/s.js":
            skript = "onconnect = () => fetch('/privat/s');"
            return Antwort(200, "text/javascript", skript)
        if pfad.startswith("/api/preis"):
            return Antwort(200, "application/json", json.dumps({"rate": 25}))
        return Antwort(200, "text/plain", "")

    with klickserver(antworte) as server:
        lauf = laufe(chromium, server.adresse("/handy/x"), karte(ANTWORT), GESPERRT)
        time.sleep(0.5)
        gesperrt = server.mit("/privat/")

    assert gesperrt == []
    assert lauf.status == "gelesen"
    assert [e.status for e in lauf.ergebnisse] == ["erfasst"]


def test_speculation_rules_werden_entfernt_erlaubte_seite_bleibt_gleich(chromium):
    frei = SPEKULATION.replace("privat", "frei")
    kopf = f'<script type="speculationrules">{frei}</script>'
    seite = _seite(kopf, NACHGELADEN.replace("privat", "frei"))

    def antworte(pfad: str) -> Antwort:
        if pfad == "/handy/x":
            return Antwort(200, "text/html; charset=utf-8", seite, {"X-Bleibt": "ja"})
        if pfad.startswith("/api/preis"):
            return Antwort(200, "application/json", json.dumps({"rate": 25}))
        return Antwort(200, "text/plain", "")

    with klickserver(antworte) as server:
        lauf = laufe(chromium, server.adresse("/handy/x"), karte(ANTWORT), OFFEN)
        time.sleep(0.5)

    assert server.mit("/frei/") == []
    assert [(e.status, e.werte.rate) for e in lauf.ergebnisse] == [("erfasst", 25.0)]


@pytest.mark.parametrize("weg", ["skripte", "eventsource"])
def test_crawl_delay_gilt_fuer_jede_anfrage_an_den_host(chromium, weg):
    verzug = 1.0
    kopf = (
        '<script src="/a.js"></script><script src="/b.js"></script>'
        '<link rel="stylesheet" href="/c.css">'
        if weg == "skripte"
        else ""
    )
    zusatz = 'new EventSource("/strom");' if weg == "eventsource" else ""
    seite = _seite(kopf, zusatz)

    def antworte(pfad: str) -> Antwort:
        if pfad == "/handy/x":
            return html(seite)
        if pfad.startswith("/api/preis"):
            return Antwort(200, "application/json", json.dumps({"rate": 25}))
        if pfad == "/strom":
            return Antwort(200, "text/event-stream", "retry: 50\ndata: x\n\n")
        typ = "text/css" if pfad.endswith(".css") else "text/javascript"
        return Antwort(200, typ, "")

    robots = f"User-agent: *\nCrawl-delay: {verzug:g}\n"
    with klickserver(antworte) as server:
        lauf = laufe(chromium, server.adresse("/handy/x"), karte(ANTWORT), robots)

    assert lauf.status == "gelesen"
    assert server.mit("/strom") == []
    assert len(server.abrufe) == (5 if weg == "skripte" else 2)
    assert min(server.luecken("/")) >= verzug


@pytest.mark.parametrize("fall", ["http_503", "verbindung_abgelehnt"])
def test_ausfall_der_preisantwort_ist_kein_gelesener_lauf(chromium, fall):
    preis = "/api/preis" if fall == "http_503" else "http://localhost:9/api/preis"
    seite = _seite(preis=preis)

    def antworte(pfad: str) -> Antwort:
        if pfad == "/handy/x":
            return html(seite)
        return Antwort(503, "application/json", "{}")

    with klickserver(antworte) as server:
        lauf = laufe(
            chromium, server.adresse("/handy/x"), karte(ANTWORT), OFFEN, frist_ms=2000
        )

    assert lauf.status == "gestoert"
    assert "Preisantwort" in lauf.grund
    if fall == "verbindung_abgelehnt":
        assert [g.url for g in lauf.gescheitert] == [
            "http://localhost:9/api/preis?speicher=128"
        ]
        assert lauf.gescheitert[0].grund
