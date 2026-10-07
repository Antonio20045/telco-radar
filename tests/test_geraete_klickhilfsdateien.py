"""Hilfsdateien im Klick-Tor: Skripte und Stylesheets eines Hosts ohne Regeln.

Entscheidung Antonio 07.10.2026: antwortet robots.txt eines Hosts mit 401 oder 403, gilt
das nach RFC 9309 als „keine Regeln“, und der Klick-Crawler lädt von dort Skripte und
Stylesheets; sie stehen in ``Klicklauf.hilfsdateien`` und im Index der Erkundung, mit
geschwärzten Adressen. Gegenproben: Dokument, xhr und fetch desselben Hosts bleiben
verworfen; eine lesbare robots.txt mit Disallow, ein Status 500 und ein gescheiterter
Abruf der robots.txt sperren weiter; der Abstand je Host gilt auch für die Hilfsdatei.
Liefert eine Skript-Adresse dieses Hosts Daten statt JavaScript oder CSS, auch nach
einer Umleitung, verwirft das Tor die Antwort: kein Preis, kein Mitschnitt, kein Beleg.
Ein lokaler Server liefert BEISPIEL-Seiten auf 127.0.0.1, unter ``localhost`` ist er der
Dateiserver; keine Anfrage verlässt den Rechner.
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from urllib.parse import urlsplit

import pytest
from klickserver import JETZT, Antwort, html, karte, klickserver, umleitung

from telco_radar.collect.geraete.klickerkundung import erkunde_anbieter
from telco_radar.collect.geraete.klickhilfe import KEINE_HILFSDATEI
from telco_radar.collect.geraete.klickziele import Erkundungsziel, Seitenziel
from telco_radar.collect.geraete.robots import RobotsWaechter

DATEIHOST = "localhost"
OFFEN = "User-agent: *\nDisallow:\n"
DATEIEN_GESPERRT = "User-agent: *\nDisallow: /static/\n"
SEITE = """<!doctype html><html><head>KOPF</head><body>
<h1 id="kanarie">Beispielhandy X</h1>
<div id="speicher"><button data-wert="128" aria-pressed="true">128 GB</button></div>
<div id="tarif"><button data-wert="S" aria-pressed="true">Tarif S</button></div>
<div id="laufzeit"><button data-wert="24" aria-pressed="true">24 Monate</button></div>
<section id="preis"></section>
RUMPF
<script>
fetch("/api/preis?speicher=128").then(r => r.json()).then(d => {
  document.getElementById("preis").innerText = "Monatliche Rate " + d.rate + ",00 €";
}).catch(() => {});
</script></body></html>"""
SKRIPTSEITE = """<!doctype html><html><head></head><body>
<h1 id="kanarie">Beispielhandy X</h1>
<div id="speicher"><button data-wert="128" aria-pressed="true">128 GB</button></div>
<div id="tarif"><button data-wert="S" aria-pressed="true">Tarif S</button></div>
<div id="laufzeit"><button data-wert="24" aria-pressed="true">24 Monate</button></div>
<section id="preis">Monatliche Rate 25,00 €</section>
<script src="DATEIEN/api/preis?speicher=128"></script>
<script src="DATEIEN/static/seite.js"></script>
</body></html>"""
HILFSDATEIEN = """<link rel="stylesheet" href="DATEIEN/static/seite.css">
<script src="DATEIEN/static/seite.js"></script>"""
DATEN = """<iframe src="DATEIEN/rahmen"></iframe>
<script>
fetch("DATEIEN/daten/fetch").catch(() => {});
const x = new XMLHttpRequest();
x.open("GET", "DATEIEN/daten/xhr");
x.send();
</script>"""
ANTWORT = {
    "url_muster": r"/api/preis\?",
    "pfade": {"rate": "rate"},
    "parameter": {"speicher": "speicher"},
}


def _seite(server, kopf: str = "", rumpf: str = "", vorlage: str = SEITE) -> str:
    dateien = server.adresse("", host=DATEIHOST)
    seite = vorlage.replace("KOPF", kopf).replace("RUMPF", rumpf)
    return seite.replace("DATEIEN", dateien)


def _antworte(seite: str, **weitere: Antwort) -> Callable[[str], Antwort]:
    def antworte(pfad: str) -> Antwort:
        teil = urlsplit(pfad).path
        if teil in weitere:
            return weitere[teil]
        if teil.startswith("/handy/"):
            return html(seite)
        if teil == "/api/preis":
            return Antwort(200, "application/json", json.dumps({"rate": 25}))
        if teil.endswith(".js"):
            return Antwort(200, "text/javascript", "window.hilfe = 1;")
        if teil.endswith(".css"):
            return Antwort(200, "text/css", "body { margin: 0; }")
        if teil == "/rahmen":
            return html("<p>Rahmen</p>")
        return Antwort(200, "application/json", "{}")

    return antworte


def _robots(dateihost: tuple[int, str] | Exception):
    def hole(url: str) -> tuple[int, str]:
        if urlsplit(url).hostname != DATEIHOST:
            return 200, OFFEN
        if isinstance(dateihost, Exception):
            raise dateihost
        return dateihost

    return hole


def _laufe(chromium, server, robots, abstand: float = 0.0):
    from telco_radar.collect.geraete.klickcrawler import klicke_durch
    from telco_radar.collect.geraete.klicktor import Hostschleuse

    waechter = RobotsWaechter(hole=robots)
    schleuse = Hostschleuse(waechter, lambda: JETZT, abstand)
    adresse = server.adresse("/handy/x")
    k = karte(ANTWORT)
    return klicke_durch(
        chromium, adresse, k, waechter, lambda: JETZT, schleuse=schleuse
    )


def _pfade(eintraege) -> dict[str, str]:
    return {urlsplit(e.url).path: e.grund for e in eintraege}


@pytest.mark.parametrize("status", [401, 403])
def test_skript_und_stylesheet_vom_host_ohne_lesbare_robots_werden_geladen(
    chromium, status
):
    with klickserver(lambda pfad: Antwort()) as server:
        server.antworte = _antworte(_seite(server, HILFSDATEIEN, DATEN))
        lauf = _laufe(chromium, server, _robots((status, "")))

    assert sorted(server.mit("/static/")) == ["/static/seite.css", "/static/seite.js"]
    assert server.mit("/rahmen") == [] and server.mit("/daten/") == []
    grund = f"robots.txt nicht lesbar (HTTP {status})"
    geladen = sorted(
        (urlsplit(h.url).hostname, urlsplit(h.url).path, h.art, h.grund)
        for h in lauf.hilfsdateien
    )
    assert geladen == [
        (DATEIHOST, "/static/seite.css", "stylesheet", grund),
        (DATEIHOST, "/static/seite.js", "script", grund),
    ]
    assert _pfade(lauf.verworfen) == {
        "/rahmen": grund,
        "/daten/fetch": grund,
        "/daten/xhr": grund,
    }
    assert lauf.status == "gelesen"


def test_dokument_xhr_und_fetch_vom_host_ohne_lesbare_robots_bleiben_verworfen(
    chromium,
):
    with klickserver(lambda pfad: Antwort()) as server:
        server.antworte = _antworte(_seite(server, rumpf=DATEN))
        lauf = _laufe(chromium, server, _robots((403, "")))

    assert [p for p in server.abrufe if not p.startswith(("/handy/", "/api/"))] == []
    grund = "robots.txt nicht lesbar (HTTP 403)"
    assert _pfade(lauf.verworfen) == {
        "/rahmen": grund,
        "/daten/fetch": grund,
        "/daten/xhr": grund,
    }
    assert lauf.status == "gelesen"


@pytest.mark.parametrize(
    ("robots", "grund"),
    [
        ((200, DATEIEN_GESPERRT), "per robots.txt gesperrt: /static/seite"),
        ((500, ""), "robots.txt nicht lesbar (HTTP 500)"),
        (TimeoutError("robots.txt zu langsam"), "TimeoutError: robots.txt zu langsam"),
    ],
    ids=["disallow", "http_500", "fehler"],
)
def test_lesbare_sperre_und_gestoerte_robots_sperren_hilfsdateien_weiter(
    chromium, robots, grund
):
    with klickserver(lambda pfad: Antwort()) as server:
        server.antworte = _antworte(_seite(server, HILFSDATEIEN))
        lauf = _laufe(chromium, server, _robots(robots))

    assert server.mit("/static/") == []
    verworfen = _pfade(lauf.verworfen)
    assert sorted(verworfen) == ["/static/seite.css", "/static/seite.js"]
    assert all(g.startswith(grund) for g in verworfen.values())
    assert lauf.status == "gelesen"


def test_abstand_je_host_gilt_auch_fuer_die_hilfsdatei(chromium):
    abstand = 1.0
    kopf = HILFSDATEIEN + '\n<script src="DATEIEN/static/zwei.js"></script>'
    with klickserver(lambda pfad: Antwort()) as server:
        server.antworte = _antworte(_seite(server, kopf))
        lauf = _laufe(chromium, server, _robots((403, "")), abstand)

    assert len(server.mit("/static/")) == 3
    assert len(lauf.hilfsdateien) == 3
    assert min(server.luecken("/static/")) >= abstand
    assert lauf.status == "gelesen"


def test_erkundung_legt_hilfsdateien_geschwaerzt_im_index_ab(chromium, tmp_path):
    kopf = '<script src="DATEIEN/static/seite.js?token=GEHEIM4711&v=2"></script>'
    with klickserver(lambda pfad: Antwort()) as server:
        server.antworte = _antworte(_seite(server, kopf))
        seiten = (Seitenziel("beispielhandy-x", 128, server.adresse("/handy/x")),)
        ziel = Erkundungsziel("beispiel", "Beispielanbieter", seiten, None, 0.0)
        ende = time.monotonic() + 300
        index = erkunde_anbieter(
            chromium, ziel, lambda: JETZT, _robots((403, "")), tmp_path, ende
        )
        dateien = server.adresse("", host=DATEIHOST)

    assert server.mit("/static/seite.js") == ["/static/seite.js?token=GEHEIM4711&v=2"]
    seite = index["seiten"][0]
    assert seite["hilfsdateien"] == [
        {
            "url": f"{dateien}/static/seite.js?token=ENTFERNT&v=2",
            "art": "script",
            "grund": "robots.txt nicht lesbar (HTTP 403)",
        }
    ]
    assert seite["zaehlung"]["hilfsdateien"] == 1
    abgelegt = (
        tmp_path / "beispiel" / JETZT.date().isoformat() / "index.json"
    ).read_text(encoding="utf-8")
    assert "GEHEIM4711" not in abgelegt
    assert json.loads(abgelegt)["seiten"][0]["hilfsdateien"] == seite["hilfsdateien"]


def _raten(lauf) -> list[float | None]:
    return [e.antwortwerte.rate for e in lauf.ergebnisse if e.antwortwerte is not None]


def test_preis_aus_skriptantwort_eines_hosts_ohne_regeln_wird_nicht_gelesen(chromium):
    with klickserver(lambda pfad: Antwort()) as server:
        server.antworte = _antworte(_seite(server, vorlage=SKRIPTSEITE))
        lauf = _laufe(chromium, server, _robots((403, "")))

    assert server.mit("/api/preis") == ["/api/preis?speicher=128"]
    assert _raten(lauf) == []
    grund = _pfade(lauf.verworfen)["/api/preis"]
    assert grund == f"{KEINE_HILFSDATEI} (Content-Type application/json)"
    assert [urlsplit(h.url).path for h in lauf.hilfsdateien] == ["/static/seite.js"]


def test_gegenprobe_mit_offener_robots_wird_der_preis_aus_dem_skript_gelesen(chromium):
    with klickserver(lambda pfad: Antwort()) as server:
        server.antworte = _antworte(_seite(server, vorlage=SKRIPTSEITE))
        lauf = _laufe(chromium, server, _robots((200, OFFEN)))

    assert _raten(lauf) == [25.0]
    assert lauf.verworfen == []


def test_umleitung_auf_dem_ausnahmeweg_laedt_nur_hilfsdateien(chromium):
    kopf = """<script src="DATEIEN/static/um-daten.js"></script>
<script src="DATEIEN/static/um-skript.js"></script>"""
    weitere = {
        "/static/um-daten.js": umleitung("/daten/preis.json"),
        "/static/um-skript.js": umleitung("/static/ziel.js"),
    }
    with klickserver(lambda pfad: Antwort()) as server:
        server.antworte = _antworte(_seite(server, kopf), **weitere)
        lauf = _laufe(chromium, server, _robots((403, "")))

    assert server.mit("/daten/") == ["/daten/preis.json"]
    assert server.mit("/static/ziel.js") == ["/static/ziel.js"]
    assert _pfade(lauf.verworfen) == {
        "/daten/preis.json": f"{KEINE_HILFSDATEI} (Content-Type application/json)"
    }
    geladen = [
        (urlsplit(h.url).path, urlsplit(h.anfrage).path) for h in lauf.hilfsdateien
    ]
    assert geladen == [("/static/ziel.js", "/static/um-skript.js")]
    assert lauf.status == "gelesen"


def test_erkundung_legt_daten_eines_hosts_ohne_regeln_nicht_im_mitschnitt_ab(
    chromium, tmp_path
):
    with klickserver(lambda pfad: Antwort()) as server:
        server.antworte = _antworte(_seite(server, vorlage=SKRIPTSEITE))
        seiten = (Seitenziel("beispielhandy-x", 128, server.adresse("/handy/x")),)
        ziel = Erkundungsziel("beispiel", "Beispielanbieter", seiten, None, 0.0)
        ende = time.monotonic() + 300
        index = erkunde_anbieter(
            chromium, ziel, lambda: JETZT, _robots((403, "")), tmp_path, ende
        )

    ordner = tmp_path / "beispiel" / JETZT.date().isoformat()
    saetze = []
    for datei in sorted(ordner.glob("mitschnitt-*.json")):
        saetze += json.loads(datei.read_text(encoding="utf-8"))["antworten"]
    vom_dateihost = [
        s
        for s in saetze
        if urlsplit(s.get("url") or "").hostname == DATEIHOST and s.get("koerper")
    ]
    assert vom_dateihost == []
    seite = index["seiten"][0]
    assert [urlsplit(v["url"]).path for v in seite["verworfen"]] == ["/api/preis"]
    assert seite["verworfen"][0]["grund"].startswith(KEINE_HILFSDATEI)
    assert [urlsplit(h["url"]).path for h in seite["hilfsdateien"]] == [
        "/static/seite.js"
    ]
