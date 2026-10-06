"""Nebenwege einer Produktseite: robots.txt und Crawl-delay gelten für jede Anfrage.

Fälle aus der zweiten und dritten Prüfrunde zu Schritt 4: WebSocket, EventSource,
Beacon, Worker, Prefetch, Prerender (``<link>`` im Dokument, nachgeladen, als
Kopfzeile), Speculation Rules (im Dokument, nachgeladen, im Shadow Root und als
Kopfzeile), iframe und Stylesheet erreichen keinen gesperrten Pfad; Vorabladen geht
auch zu erlaubten Pfaden nie hinaus; Skripte und Stylesheets warten den Crawl-delay ab
wie Seite und Preisantwort, und dieses Warten zählt nicht gegen die Frist des
Kanarienwerts; Datenkanäle gehen gar nicht hinaus; eine gescheiterte Preisanfrage
stört den Lauf. Ein lokaler Server auf 127.0.0.1 liefert BEISPIEL-Seiten, von Hand
geschrieben; keine Anfrage verlässt den Rechner.
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
PRERENDER = """const l = document.createElement("link");
l.rel = "prerender";
l.href = "/privat/js";
document.head.appendChild(l);
const bis = Date.now() + 300;
while (Date.now() < bis) {}"""
SCHATTEN = """const s = document.createElement("script");
s.type = "speculationrules";
s.textContent = JSON.stringify({prefetch: [{source: "list", urls: ["/privat/sr"]}]});
const h = document.createElement("div");
document.body.appendChild(h);
h.attachShadow({mode: "open"}).appendChild(s);"""
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
    "spekulation_schatten": ("", SCHATTEN),
    "prerender": ('<link rel="prerender" href="/privat/vorab">', ""),
    "prerender_nachgeladen": ("", PRERENDER),
    "prerender_kopf": ("", ""),
    "prefetch_kopf": ("", ""),
    "iframe": ("", IFRAME),
    "stylesheet": ('<link rel="stylesheet" href="/privat/css">', ""),
}
KOPFZEILEN = {
    "spekulation_kopf": {"Speculation-Rules": '"/privat/regeln.json"'},
    "prerender_kopf": {"Link": "</privat/kopf>; rel=prerender"},
    "prefetch_kopf": {"Link": "</privat/kopf>; rel=prefetch"},
}
KANARIE_SPAET = """<!doctype html><html><body>
<div id="app"></div>
<div id="speicher"><button data-wert="128" aria-pressed="true">128 GB</button></div>
<div id="tarif"><button data-wert="S" aria-pressed="true">Tarif S</button></div>
<div id="laufzeit"><button data-wert="24" aria-pressed="true">24 Monate</button></div>
<section id="preis"></section>
<script>
(async () => {
  await fetch("/api/konfig");
  await fetch("/api/produkt");
  const d = await (await fetch("/api/preis?speicher=128")).json();
  document.getElementById("app").innerHTML = '<h1 id="kanarie">Beispielhandy X</h1>';
  document.getElementById("preis").innerText = "Monatliche Rate " + d.rate + ",00 €";
})();
</script></body></html>"""


def _seite(kopf="", zusatz="", preis="/api/preis"):
    return SEITE.replace("KOPF", kopf).replace("ZUSATZ", zusatz).replace("PREIS", preis)


@pytest.mark.parametrize("weg", list(NEBENWEGE))
def test_nebenweg_erreicht_keinen_gesperrten_pfad(chromium, weg):
    kopf, zusatz = NEBENWEGE[weg]
    seite = _seite(kopf, zusatz)
    regeln = KOPFZEILEN.get(weg, {})

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
        time.sleep(1.0)
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


@pytest.mark.parametrize("weg", ["prerender", "prerender_nachgeladen"])
def test_vorabladen_geht_auch_zu_erlaubten_pfaden_nie_hinaus(chromium, weg):
    verzug = 1.0
    kopf, zusatz = NEBENWEGE[weg]
    seite = _seite(kopf, zusatz).replace("/privat/", "/frei/")

    def antworte(pfad: str) -> Antwort:
        if pfad == "/handy/x":
            return html(seite)
        if pfad.startswith("/api/preis"):
            return Antwort(200, "application/json", json.dumps({"rate": 25}))
        return html("<p>frei</p>")

    robots = f"User-agent: *\nCrawl-delay: {verzug:g}\n"
    with klickserver(antworte) as server:
        lauf = laufe(chromium, server.adresse("/handy/x"), karte(ANTWORT), robots)
        time.sleep(1.0)

    assert server.mit("/frei/") == []
    assert server.abrufe == ["/handy/x", "/api/preis?speicher=128"]
    assert min(server.luecken("/")) >= verzug
    assert lauf.status == "gelesen"


def test_crawl_delay_zaehlt_nicht_gegen_die_frist_des_kanarienwerts(chromium):
    verzug = 1.0

    def antworte(pfad: str) -> Antwort:
        if pfad == "/handy/x":
            return html(KANARIE_SPAET)
        if pfad.startswith("/api/preis"):
            return Antwort(200, "application/json", json.dumps({"rate": 25}))
        return Antwort(200, "application/json", "{}")

    robots = f"User-agent: *\nCrawl-delay: {verzug:g}\n"
    with klickserver(antworte) as server:
        lauf = laufe(
            chromium, server.adresse("/handy/x"), karte(ANTWORT), robots, frist_ms=2000
        )

    assert len(server.abrufe) == 4
    assert min(server.luecken("/")) >= verzug
    assert lauf.status == "gelesen", lauf.grund
    assert [e.werte.rate for e in lauf.ergebnisse] == [25.0]


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
