"""Klick-Erkundung (Schritt 5a): Material für die Klick-Karte über das Crawler-Tor.

Ein lokaler Server auf 127.0.0.1 liefert BEISPIEL-Seiten, von Hand geschrieben:
Speicher- und Laufzeitknöpfe mit ``aria-pressed``, eine Preiszusammenfassung, die ihre
Rate per ``fetch`` nachlädt. Geprüft wird, was die Erkundung festhält (Gruppen, Preise,
Klick-Proben, Mitschnitt, Seite, Screenshot) und die Regeln: robots.txt sperrt eine
Antwort, Bot-Schutz beendet den Anbieter ohne weitere Anfrage, die Größengrenze kürzt
mit Vermerk, Cookies und geheime Parameter stehen in keiner Datei, die Zeitgrenze
heißt „nicht besucht“.
"""

from __future__ import annotations

import gzip
import json
import time
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest
from klickserver import JETZT, Antwort, html, klickserver

from telco_radar.collect.geraete.klickablage import RESERVE_INDEX, VERMERK_KOERPER
from telco_radar.collect.geraete.klickerkundung import (
    GRUND_NACH_BOT,
    erkunde_anbieter,
)
from telco_radar.collect.geraete.klickspur import HOECHSTE_ANTWORT
from telco_radar.collect.geraete.klickziele import Erkundungsziel, Seitenziel

OFFEN = "User-agent: *\nDisallow:\n"
TAG = JETZT.date().isoformat()
SEITE = """<!doctype html><html><body>
<h1 id="kanarie">Beispielhandy X</h1>
<div id="speicher" aria-label="Speicher">
 <button data-wert="128" aria-pressed="false">128 GB</button>
 <button data-wert="256" aria-pressed="true">256 GB</button>
 <button data-wert="512" aria-pressed="false">512 GB</button>
</div>
<div id="laufzeit" aria-label="Laufzeit">
 <button data-wert="24" aria-pressed="true">24 Monate</button>
 <button data-wert="36" aria-pressed="false">36 Monate</button>
</div>
<section id="preis"><p>Monatliche Rate <span id="rate">offen</span></p>
<p>Anzahlung <b>1,00 €</b></p></section>
<p id="c"></p>
<script>
const wahl = {speicher: "256", laufzeit: "24"};
function lade() {
  fetch(`/api/preis?ZUSATZspeicher=${wahl.speicher}&laufzeit=${wahl.laufzeit}`)
    .then(r => r.json()).then(d => {
      document.getElementById("rate").innerText = `${d.rate},00 €`;
    }).catch(() => {});
}
for (const gruppe of ["speicher", "laufzeit"]) {
  for (const k of document.querySelectorAll(`#${gruppe} button`)) {
    k.addEventListener("click", () => {
      wahl[gruppe] = k.dataset.wert;
      for (const j of document.querySelectorAll(`#${gruppe} button`)) {
        j.setAttribute("aria-pressed", String(j === k));
      }
      lade();
    });
  }
}
lade();
NACHLADEN
</script></body></html>"""
RATE = {"128": 30, "256": 35, "512": 45}
PRUEFSEITE = "<!doctype html><html><body>Einen Moment bitte …</body></html>"
RADWARE = "<html><head><title>Radware Bot Manager Captcha</title></head></html>"


def _seite(zusatz: str = "", nachladen: str = "") -> str:
    return SEITE.replace("ZUSATZ", zusatz).replace("NACHLADEN", nachladen)


def _preis(pfad: str) -> Antwort:
    frage = parse_qs(urlsplit(pfad).query)
    rate = RATE[frage["speicher"][0]] - (5 if frage["laufzeit"][0] == "36" else 0)
    return Antwort(200, "application/json", json.dumps({"rate": rate}))


def _beispiel(seite: str, **weitere: Antwort):
    def antworte(pfad: str) -> Antwort:
        teil = urlsplit(pfad).path
        if teil.startswith("/handy/"):
            return html(seite)
        if teil == "/api/preis":
            return _preis(pfad)
        return weitere.get(teil, Antwort(200, "application/json", "{}"))

    return antworte


def _ziel(server, *pfade: str) -> Erkundungsziel:
    seiten = tuple(Seitenziel("beispielhandy-x", 256, server.adresse(p)) for p in pfade)
    return Erkundungsziel("beispiel", "Beispielanbieter", seiten, None, 0.0)


def _erkunde(chromium, ziel, ausgabe: Path, robots=OFFEN, **weiter) -> dict:
    ende = weiter.pop("ende", time.monotonic() + 600)

    def hole(url: str) -> tuple[int, str]:
        return 200, robots

    return erkunde_anbieter(
        chromium, ziel, lambda: JETZT, hole, ausgabe, ende, **weiter
    )


def _lies(ordner: Path, name: str):
    return json.loads((ordner / name).read_text(encoding="utf-8"))


def _alle_texte(ordner: Path) -> str:
    texte = []
    for datei in sorted(ordner.iterdir()):
        roh = datei.read_bytes()
        if datei.name.endswith(".gz"):
            roh = gzip.decompress(roh)
        texte.append(roh.decode("utf-8", errors="replace"))
    return "\n".join(texte)


def test_erkundung_haelt_gruppen_preise_klicks_und_mitschnitt_fest(chromium, tmp_path):
    with klickserver(_beispiel(_seite())) as server:
        index = _erkunde(chromium, _ziel(server, "/handy/x"), tmp_path)
        preis = server.adresse("/api/preis")

    ordner = tmp_path / "beispiel" / TAG
    assert index["status"] == "gelesen" and index["grund"] is None
    seite = index["seiten"][0]
    assert (seite["status"], seite["bot_schutz"], seite["http_status"]) == (
        "gelesen",
        False,
        200,
    )
    dateien = seite["dateien"]
    inventar = _lies(ordner, dateien["bedienelemente"])
    arten = {g["art"]: g for g in inventar["gruppen"]}
    speicher = [inventar["elemente"][i] for i in arten["speicher"]["elemente"]]
    laufzeit = [inventar["elemente"][i] for i in arten["laufzeit"]["elemente"]]
    assert [e["text"] for e in speicher] == ["128 GB", "256 GB", "512 GB"]
    assert [e["text"] for e in laufzeit] == ["24 Monate", "36 Monate"]
    assert arten["speicher"]["pfad"] == "#speicher"
    assert speicher[0]["pfad"] == "#speicher > button:nth-of-type(1)"
    assert [e["gewaehlt"] for e in speicher] == [None, "aria-pressed", None]
    assert speicher[1]["daten"] == {"data-wert": "256"}
    assert speicher[1]["aria"] == {"aria-pressed": "true"}
    preise = _lies(ordner, dateien["preise"])["preise"]
    assert {(p["pfad"], p["text"]) for p in preise} == {
        ("#rate", "35,00 €"),
        ("#preis > p:nth-of-type(2) > b:nth-of-type(1)", "1,00 €"),
    }
    proben = _lies(ordner, dateien["klicks"])["proben"]
    assert [(p["art"], p["text"], p["uebernommen"]) for p in proben] == [
        ("speicher", "128 GB", "ja"),
        ("speicher", "512 GB", "ja"),
        ("laufzeit", "36 Monate", "ja"),
    ]
    assert [a["url"] for a in proben[0]["anfragen"]] == [
        f"{preis}?speicher=128&laufzeit=24"
    ]
    assert [p["preise_geaendert"] for p in proben] == [
        [{"pfad": "#rate", "vorher": "35,00 €", "nachher": "30,00 €"}],
        [{"pfad": "#rate", "vorher": "30,00 €", "nachher": "45,00 €"}],
        [{"pfad": "#rate", "vorher": "45,00 €", "nachher": "40,00 €"}],
    ]
    mitschnitt = _lies(ordner, dateien["mitschnitt"])
    koerper = {a["url"]: a["koerper"] for a in mitschnitt["antworten"]}
    assert json.loads(koerper[f"{preis}?speicher=256&laufzeit=24"]) == {"rate": 35}
    assert json.loads(koerper[f"{preis}?speicher=512&laufzeit=36"]) == {"rate": 40}
    seite_html = gzip.decompress((ordner / dateien["html"]).read_bytes()).decode()
    assert "Beispielhandy X" in seite_html and "35,00 €" in seite_html
    assert (ordner / dateien["screenshot"]).read_bytes().startswith(b"\x89PNG")
    assert _lies(ordner, "index.json") == index


def test_robots_gesperrte_antwort_geht_nicht_hinaus_und_fehlt_im_mitschnitt(
    chromium, tmp_path
):
    geheim = '<img hidden><script>fetch("/api/geheim?x=1").catch(() => {});</script>'
    seite = _seite().replace("</body>", f"{geheim}</body>")
    robots = "User-agent: *\nDisallow: /api/geheim\n"
    with klickserver(_beispiel(seite)) as server:
        index = _erkunde(chromium, _ziel(server, "/handy/x"), tmp_path, robots)
        gesperrt = server.adresse("/api/geheim?x=1")

    assert server.mit("/api/geheim") == []
    seite_index = index["seiten"][0]
    assert seite_index["status"] == "gelesen"
    assert [v["url"] for v in seite_index["verworfen"]] == [gesperrt]
    assert "per robots.txt gesperrt" in seite_index["verworfen"][0]["grund"]
    ordner = tmp_path / "beispiel" / TAG
    mitschnitt = _lies(ordner, seite_index["dateien"]["mitschnitt"])
    assert gesperrt not in {a["url"] for a in mitschnitt["antworten"]}
    angefragt = {a["url"]: a for a in mitschnitt["anfragen"]}
    assert angefragt[gesperrt]["status"] is None
    assert angefragt[gesperrt]["abbruch"]


@pytest.mark.parametrize(
    "pruefung",
    [html(PRUEFSEITE, 403), html(RADWARE, 200), html(PRUEFSEITE, 202)],
    ids=["403", "radware_200", "202"],
)
def test_bot_schutz_der_seite_beendet_den_anbieter_ohne_weitere_anfrage(
    chromium, tmp_path, pruefung
):
    with klickserver(lambda pfad: pruefung) as server:
        ziel = _ziel(server, "/handy/x", "/handy/y")
        index = _erkunde(chromium, ziel, tmp_path)

    assert server.abrufe == ["/handy/x"]
    erste, zweite = index["seiten"]
    assert (erste["status"], erste["bot_schutz"]) == ("gestoert", True)
    assert erste["http_status"] == pruefung.status
    assert "Abruf gestört" in erste["grund"]
    assert set(erste["dateien"]) == {"mitschnitt"}
    assert (zweite["status"], zweite["grund"]) == ("nicht_besucht", GRUND_NACH_BOT)
    assert index["status"] == "gestoert"
    assert index["grund"].startswith("Seite 1: Abruf gestört")


def test_bot_schutz_einer_antwort_beendet_den_anbieter(chromium, tmp_path):
    spaeter = 'setTimeout(() => fetch("/api/nachher").catch(() => {}), 2000);'
    sperre = Antwort(403, "application/json", '{"fehler": "verboten"}')
    antworte = _beispiel(_seite(nachladen=spaeter))

    def mit_sperre(pfad: str) -> Antwort:
        return sperre if pfad.startswith("/api/preis") else antworte(pfad)

    with klickserver(mit_sperre) as server:
        index = _erkunde(chromium, _ziel(server, "/handy/x", "/handy/y"), tmp_path)

    assert server.mit("/api/nachher") == [] and server.mit("/handy/y") == []
    erste, zweite = index["seiten"]
    assert (erste["status"], erste["bot_schutz"]) == ("gestoert", True)
    assert "HTTP 403" in erste["grund"]
    assert zweite["status"] == "nicht_besucht"
    assert {"html", "screenshot", "bedienelemente"} <= set(erste["dateien"])


def test_groessengrenze_kuerzt_mit_vermerk(chromium, tmp_path):
    gross = Antwort(200, "application/json", json.dumps({"x": "y" * 150_000}))
    laden = 'fetch("/api/gross").catch(() => {});'
    grenze = RESERVE_INDEX + 60_000
    with klickserver(_beispiel(_seite(nachladen=laden), **{"/api/gross": gross})) as s:
        index = _erkunde(chromium, _ziel(s, "/handy/x"), tmp_path, grenze=grenze)

    ordner = tmp_path / "beispiel" / TAG
    belegt = sum(d.stat().st_size for d in ordner.iterdir())
    assert belegt <= grenze
    assert index["groesse_bytes"] == belegt
    assert index["gekuerzt"]
    dateien = index["seiten"][0]["dateien"]
    if dateien["mitschnitt"] is not None:
        antworten = _lies(ordner, dateien["mitschnitt"])["antworten"]
        gekuerzt = [a for a in antworten if a["url"].endswith("/api/gross")]
        assert gekuerzt[0]["koerper"] is None
        assert gekuerzt[0]["grund"] == VERMERK_KOERPER


def test_antwort_ueber_200_kb_wird_mit_vermerk_gekuerzt(chromium, tmp_path):
    riesig = Antwort(200, "application/json", "9" * (HOECHSTE_ANTWORT + 50_000))
    laden = 'fetch("/api/riesig").catch(() => {});'
    with klickserver(
        _beispiel(_seite(nachladen=laden), **{"/api/riesig": riesig})
    ) as s:
        index = _erkunde(chromium, _ziel(s, "/handy/x"), tmp_path)

    ordner = tmp_path / "beispiel" / TAG
    antworten = _lies(ordner, index["seiten"][0]["dateien"]["mitschnitt"])["antworten"]
    eintrag = next(a for a in antworten if a["url"].endswith("/api/riesig"))
    assert eintrag["gekuerzt"] is True
    assert eintrag["groesse"] == HOECHSTE_ANTWORT + 50_000
    assert len(eintrag["koerper"]) == HOECHSTE_ANTWORT


def test_keine_cookies_und_keine_geheimen_parameter_in_der_ausgabe(chromium, tmp_path):
    zeige = 'document.getElementById("c").innerText = "Sitzung " + document.cookie;'
    laden = 'fetch("/api/echo").catch(() => {});'
    seite = _seite(zusatz='token=${"ABCGEH" + "EIM42"}&', nachladen=zeige + laden)
    keks = {"Set-Cookie": "sitzung=KEKSWERT987654; Path=/"}
    echo = Antwort(200, "application/json", '{"sitzung": "KEKSWERT987654"}')

    def antworte(pfad: str) -> Antwort:
        if urlsplit(pfad).path == "/handy/x":
            return Antwort(200, "text/html; charset=utf-8", seite, keks)
        return _beispiel(seite, **{"/api/echo": echo})(pfad)

    with klickserver(antworte) as server:
        index = _erkunde(chromium, _ziel(server, "/handy/x"), tmp_path)

    assert index["status"] == "gelesen"
    alles = _alle_texte(tmp_path / "beispiel" / TAG)
    assert "KEKSWERT987654" not in alles
    assert "ABCGEHEIM42" not in alles
    assert "Sitzung sitzung=[Cookie entfernt]" in alles
    ordner = tmp_path / "beispiel" / TAG
    mitschnitt = _lies(ordner, index["seiten"][0]["dateien"]["mitschnitt"])
    koerper = {urlsplit(a["url"]).path: a["koerper"] for a in mitschnitt["antworten"]}
    assert koerper["/api/echo"] == '{"sitzung": "[Cookie entfernt]"}'
    assert "token=ENTFERNT&speicher=256" in alles


def test_zeitgrenze_heisst_nicht_besucht_ohne_anfrage(chromium, tmp_path):
    with klickserver(_beispiel(_seite())) as server:
        ziel = _ziel(server, "/handy/x", "/handy/y")
        index = _erkunde(chromium, ziel, tmp_path, ende=time.monotonic() - 1)

    assert server.abrufe == []
    assert [s["status"] for s in index["seiten"]] == ["nicht_besucht"] * 2
    assert index["status"] == "gestoert"
    assert "Zeitgrenze" in index["grund"]
