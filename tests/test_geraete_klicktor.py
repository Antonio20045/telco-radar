"""Das Tor des Klick-Crawlers: robots.txt und Crawl-delay für jede Anfrage der Seite.

Fälle aus dem Prüferbefund zu Schritt 4: Umleitungen auf gesperrte Pfade, ein Service
Worker, der an ``route`` vorbei lädt, eine Preisantwort auf einem zweiten Host mit
eigenem Crawl-delay, eine Seite, die nach dem Lauf weiterfragt, und zwei Produktseiten
desselben Hosts nacheinander. Ein lokaler Server auf 127.0.0.1 liefert BEISPIEL-Seiten,
von Hand geschrieben; keine Anfrage verlässt den Rechner.
"""

from __future__ import annotations

import json
import time
from datetime import UTC, datetime
from urllib.parse import parse_qs, urlsplit

from klickserver import Antwort, html, klickserver, umleitung

from telco_radar.collect.geraete.robots import RobotsWaechter

JETZT = datetime(2026, 10, 3, 5, 0, tzinfo=UTC)
FRIST_MS = 3000
OFFEN = "User-agent: *\nDisallow:\n"
PRIVAT_GESPERRT = "User-agent: *\nDisallow: /privat/\n"
KNOEPFE = """<h1 id="kanarie">Beispielhandy X</h1>
<div id="speicher">
 <button data-wert="128" aria-pressed="true">128 GB</button>SPEICHER
</div>
<div id="tarif"><button data-wert="S" aria-pressed="true">Tarif S</button></div>
<div id="laufzeit"><button data-wert="24" aria-pressed="true">24 Monate</button></div>
<section id="preis"></section>"""
LADE = """<script>
let speicher = "128";
function lade() {
  fetch(`PREIS?speicher=${speicher}`).then(r => r.json()).then(d => {
    document.getElementById("preis").innerText = `Monatliche Rate ${d.rate},00 €`;
  });
}
for (const k of document.querySelectorAll("#speicher button")) {
  k.addEventListener("click", () => {
    speicher = k.dataset.wert;
    for (const j of document.querySelectorAll("#speicher button")) {
      j.setAttribute("aria-pressed", String(j === k));
    }
    lade();
  });
}
lade();
ZUSATZ
</script>"""


def _seite(preis="/api/preis", zusatz="", zweiter_speicher=False):
    knopf = '<button data-wert="256" aria-pressed="false">256 GB</button>'
    knoepfe = KNOEPFE.replace("SPEICHER", knopf if zweiter_speicher else "")
    skript = LADE.replace("PREIS", preis).replace("ZUSATZ", zusatz)
    return f"<!doctype html><html><body>{knoepfe}{skript}</body></html>"


def _preis(pfad: str) -> Antwort:
    speicher = parse_qs(urlsplit(pfad).query).get("speicher", ["128"])[0]
    rate = 30 if speicher == "256" else 25
    kopf = {"Access-Control-Allow-Origin": "*"}
    return Antwort(200, "application/json", json.dumps({"rate": rate}), kopf)


def _karte(url_muster=r"/api/preis\?"):
    from telco_radar.collect.geraete.klickkarte import klickkarte_aus_daten

    daten = {
        "anbieter": "Beispielanbieter",
        "knoepfe": {
            "speicher": {"selektor": "#speicher button", "wert": "data-wert"},
            "tarif": {"selektor": "#tarif button", "wert": "data-wert"},
            "laufzeit": {"selektor": "#laufzeit button", "wert": "data-wert"},
            "gewaehlt": {"attribut": "aria-pressed", "wert": "true"},
        },
        "zusammenfassung": {"selektor": "#preis"},
        "antwort": {
            "url_muster": url_muster,
            "pfade": {"rate": "rate"},
            "parameter": {"speicher": "speicher"},
        },
        "kanarie": {"selektor": "#kanarie", "enthaelt": "Beispielhandy X"},
    }
    return klickkarte_aus_daten(daten, "Prüfkarte")


def _laufe(chromium, adresse, robots, *, waechter=None, schleuse=None, **weiter):
    from telco_radar.collect.geraete.klickcrawler import klicke_durch
    from telco_radar.collect.geraete.klicktor import Hostschleuse

    hole = robots if callable(robots) else (lambda url: (200, robots))
    waechter = waechter or RobotsWaechter(hole=hole)
    weiter.setdefault("frist_ms", FRIST_MS)
    return klicke_durch(
        chromium,
        adresse,
        weiter.pop("karte", None) or _karte(),
        waechter,
        lambda: JETZT,
        schleuse=schleuse or Hostschleuse(waechter, lambda: JETZT),
        **weiter,
    )


def _beispiel(seite):
    def antworte(pfad: str) -> Antwort:
        teile = urlsplit(pfad)
        if teile.path.startswith("/handy/"):
            return html(seite)
        if teile.path.startswith("/api/"):
            return _preis(pfad)
        return Antwort(200, "application/json", "{}")

    return antworte


def test_umgeleitete_preisantwort_auf_gesperrten_pfad_geht_nicht_hinaus(chromium):
    def antworte(pfad: str) -> Antwort:
        if pfad.startswith("/api/preis"):
            return umleitung("/privat/json/preis")
        return _beispiel(_seite())(pfad)

    with klickserver(antworte) as server:
        lauf = _laufe(chromium, server.adresse("/handy/x"), PRIVAT_GESPERRT)

    assert server.mit("/privat/") == []
    assert lauf.status == "gesperrt"
    assert [urlsplit(v.url).path for v in lauf.verworfen] == ["/privat/json/preis"]
    assert all("/api/preis?speicher=128" in v.anfrage for v in lauf.verworfen)
    assert "per robots.txt gesperrt" in lauf.grund


def test_erlaubte_umleitung_der_preisantwort_wird_gelesen(chromium):
    def antworte(pfad: str) -> Antwort:
        if pfad.startswith("/api/preis"):
            return umleitung(pfad.replace("/api/preis", "/api/neu"))
        return _beispiel(_seite())(pfad)

    with klickserver(antworte) as server:
        lauf = _laufe(chromium, server.adresse("/handy/x"), PRIVAT_GESPERRT)

    assert lauf.status == "gelesen"
    assert server.mit("/api/") == ["/api/preis?speicher=128", "/api/neu?speicher=128"]
    assert [(e.status, e.werte.rate) for e in lauf.ergebnisse] == [("erfasst", 25.0)]


def test_umgeleitete_produktseite_auf_gesperrten_pfad_geht_nicht_hinaus(chromium):
    def antworte(pfad: str) -> Antwort:
        if pfad == "/handy/x":
            return umleitung("/privat/handy-x")
        return _beispiel(_seite())(pfad)

    with klickserver(antworte) as server:
        lauf = _laufe(chromium, server.adresse("/handy/x"), PRIVAT_GESPERRT)

    assert server.abrufe == ["/handy/x"]
    assert lauf.status == "gesperrt"
    assert "/privat/handy-x" in lauf.grund
    assert lauf.ergebnisse == []


def test_erlaubte_umleitung_der_produktseite_wird_gelesen(chromium):
    def antworte(pfad: str) -> Antwort:
        if pfad == "/handy/alt":
            return umleitung("/handy/x")
        return _beispiel(_seite())(pfad)

    with klickserver(antworte) as server:
        lauf = _laufe(chromium, server.adresse("/handy/alt"), PRIVAT_GESPERRT)

    assert lauf.status == "gelesen"
    assert server.abrufe[:2] == ["/handy/alt", "/handy/x"]
    assert lauf.http_status == 200
    assert [e.status for e in lauf.ergebnisse] == ["erfasst"]


def test_service_worker_laedt_nichts_an_robots_vorbei(chromium):
    zusatz = 'navigator.serviceWorker && navigator.serviceWorker.register("/sw.js");'
    arbeiter = (
        "self.addEventListener('install', (e) =>"
        " e.waitUntil(fetch('/privat/json/zaehler')));"
    )

    def antworte(pfad: str) -> Antwort:
        if pfad == "/sw.js":
            return Antwort(200, "text/javascript", arbeiter)
        return _beispiel(_seite(zusatz=zusatz))(pfad)

    with klickserver(antworte) as server:
        lauf = _laufe(chromium, server.adresse("/handy/x"), PRIVAT_GESPERRT)
        time.sleep(0.5)

    assert lauf.status == "gelesen"
    assert server.mit("/privat/") == []
    assert server.mit("/sw.js") == []


def test_favicon_geht_nicht_am_tor_vorbei(chromium):
    seite = _seite().replace(
        "<body>", '<head><link rel="icon" href="/icon.png"></head><body>'
    )

    with klickserver(_beispiel(seite)) as server:
        lauf = _laufe(chromium, server.adresse("/handy/x"), OFFEN)
        time.sleep(0.5)

    assert lauf.status == "gelesen"
    assert server.mit("/icon.png") == []
    assert server.mit("/favicon.ico") == []
    assert server.mit("/api/preis") == ["/api/preis?speicher=128"]


def test_crawl_delay_gilt_fuer_den_host_der_preisantwort(chromium):
    verzug = 1.5

    def robots(url: str) -> tuple[int, str]:
        if urlsplit(url).hostname == "localhost":
            return 200, f"User-agent: *\nCrawl-delay: {verzug:g}\n"
        return 200, OFFEN

    with klickserver(lambda pfad: Antwort()) as server:
        preis = server.adresse("/api/preis", host="localhost")
        server.antworte = _beispiel(_seite(preis=preis, zweiter_speicher=True))
        lauf = _laufe(chromium, server.adresse("/handy/x"), robots)

    assert lauf.status == "gelesen"
    assert [e.werte.rate for e in lauf.ergebnisse] == [25.0, 30.0]
    assert len(server.mit("/api/preis")) == 2
    assert min(server.luecken("/api/preis")) >= verzug


def test_seite_laedt_nach_dem_lauf_nichts_mehr(chromium):
    zusatz = 'setInterval(() => fetch("/privat/json/zaehler").catch(() => {}), 100);'

    with klickserver(_beispiel(_seite(zusatz=zusatz))) as server:
        lauf = _laufe(chromium, server.adresse("/handy/x"), PRIVAT_GESPERRT)
        nach_dem_lauf = len(server.abrufe)
        time.sleep(1.0)

    assert lauf.status == "gelesen"
    assert server.mit("/privat/") == []
    assert len(lauf.verworfen) >= 1
    assert len(server.abrufe) == nach_dem_lauf


def test_crawl_delay_gilt_zwischen_zwei_produktseiten(chromium):
    from telco_radar.collect.geraete.klicktor import Hostschleuse

    verzug = 1.0
    waechter = RobotsWaechter(
        hole=lambda url: (200, f"User-agent: *\nCrawl-delay: {verzug:g}\n")
    )
    schleuse = Hostschleuse(waechter, lambda: JETZT)

    with klickserver(_beispiel(_seite())) as server:
        erster = _laufe(
            chromium,
            server.adresse("/handy/x"),
            "",
            waechter=waechter,
            schleuse=schleuse,
        )
        ende_erster = max(t for t, _ in server.fertig)
        zweiter = _laufe(
            chromium,
            server.adresse("/handy/y"),
            "",
            waechter=waechter,
            schleuse=schleuse,
        )

    start_zweiter = next(t for t, pfad in server.zeiten if pfad == "/handy/y")
    assert (erster.status, zweiter.status) == ("gelesen", "gelesen")
    assert start_zweiter - ende_erster >= verzug
    assert len(server.mit("/handy/") + server.mit("/api/")) == 4
    assert min(server.luecken(("/handy/", "/api/"))) >= verzug
