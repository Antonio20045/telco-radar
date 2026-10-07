"""Folgeseite der Klick-Erkundung: ein benannter Klick in die Bestellstrecke, ohne Netz.

Ein lokaler Server auf 127.0.0.1 liefert BEISPIEL-Seiten, von Hand geschrieben, kein
echter Anbieter: eine Produktseite mit Speicherknöpfen und einem Weiter-Element, das je
Test ein Knopf ist (sein Skript legt per POST einen Warenkorb an und lädt dann die
Folgeseite, wie „Weiter zur Tarifauswahl“) oder ein Link (über eine Umleitung, wie
„Zur Tarifauswahl“); die Folgeseite zeigt Laufzeitknöpfe und lädt ihre Rate per
``fetch``. Geprüft wird: die Folgeseite steht mit eigener Nummer, eigenen Dateien und
``folge_von`` im Index, Inventar, Preise, Klick-Proben und Mitschnitt samt POST,
geschwärzt, Crawl-delay auch für das POST; Anmeldung, Checkout oder Zahlung als
Folgeseite, ein fehlender, mehrdeutiger, untauglicher oder wirkungsloser Knopf sind
benannte Befunde ohne weiteren Klick; sperrt robots.txt Ziel oder POST, ist die
Folgeseite ``gesperrt`` und die Anfrage verworfen; Bot-Schutz beendet den Anbieter.
"""

from __future__ import annotations

import gzip
import json
import time
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest
from klickserver import JETZT, Antwort, html, klickserver, umleitung

from scripts import erkundung_ablegen as ea
from telco_radar.collect.geraete import klickfolgeseite
from telco_radar.collect.geraete.klickerkundung import (
    GRUND_NACH_BOT,
    erkunde_anbieter,
)
from telco_radar.collect.geraete.klickziele import Erkundungsziel, Seitenziel, Weiter

OFFEN = "User-agent: *\nDisallow:\n"
TAG = JETZT.date().isoformat()
KORB = "korbQm4Lp9Zr2Tv7Hx"
KORB_PFAD = "/frontend/cart-facade/add"
FOLGEADRESSE = "/tarife?flow=f2&laufzeiten=24-36"
KNOPF = Weiter(".weiter-knopf", "Weiter zur Tarifauswahl")
LINK = Weiter("#angebot a.primaer", "Zur Tarifauswahl")
AUSGANG = """<!doctype html><html><body>
<h1>Beispielhandy X</h1>
<div id="speicher" aria-label="Speicher">
 <button data-wert="256" aria-pressed="true">256 GB</button>
 <button data-wert="512" aria-pressed="false">512 GB</button>
</div>
<section id="preis"><p>Monatliche Rate <b>35,00 €</b></p></section>
<section id="angebot">WEITER</section>
<script>
for (const k of document.querySelectorAll("#speicher button")) {
  k.addEventListener("click", () => {
    for (const j of document.querySelectorAll("#speicher button")) {
      j.setAttribute("aria-pressed", String(j === k));
    }
  });
}
for (const k of document.querySelectorAll(".weiter-knopf.korb")) {
  k.addEventListener("click", () => {
    fetch("/frontend/cart-facade/add", {method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({geraet: "beispielhandy-x", speicher: "256"})})
      .then((r) => r.json()).then((d) => { location.href = d.ziel; });
  });
}
</script></body></html>"""
KNOEPFE = """<div style="display:none"><add-to-cart-button>
<button class="weiter-knopf korb">Weiter zur Tarifauswahl</button></add-to-cart-button>
</div>
<add-to-cart-button>
<button class="weiter-knopf korb">Weiter zur Tarifauswahl</button>
</add-to-cart-button>"""
LINKS = """<a class="primaer" href="/tarife/start">Zur Tarifauswahl</a>
<a class="text" href="/shop/authentifizierung.html">Vertrag verlängern</a>"""
FOLGE = """<!doctype html><html><body>
<h1>Tarifauswahl</h1>
<div id="laufzeit" aria-label="Laufzeit des Geräts">
 <button data-wert="24" aria-pressed="false">24 Monate</button>
 <button data-wert="36" aria-pressed="true">36 Monate</button>
</div>
<section id="preis"><p>Monatlich <span id="rate">offen</span></p></section>
<script>
function lade(monate) {
  fetch(`/api/rate?laufzeit=${monate}`).then((r) => r.json()).then((d) => {
    document.getElementById("rate").innerText = `${d.rate},99 €`;
  });
}
for (const k of document.querySelectorAll("#laufzeit button")) {
  k.addEventListener("click", () => {
    for (const j of document.querySelectorAll("#laufzeit button")) {
      j.setAttribute("aria-pressed", String(j === k));
    }
    lade(k.dataset.wert);
  });
}
lade("36");
</script></body></html>"""
ANMELDUNG = """<!doctype html><html><body><h1>Anmelden</h1>
<form><input name="nutzer"><input type="password" name="kennwort">
<button type="submit">Anmelden</button></form></body></html>"""
ZAHLUNG = """<!doctype html><html><body><h1>Schritt 3</h1>
<form><label>IBAN <input name="iban"></label></form></body></html>"""
NEUTRAL = "<!doctype html><html><body><h1>Weiter</h1><p>9,99 €</p></body></html>"
PRUEFSEITE = "<!doctype html><html><body>Einen Moment bitte …</body></html>"


def _antworte(weiter: str = KNOEPFE, **seiten: Antwort):
    def antworte(pfad: str) -> Antwort:
        teile = urlsplit(pfad)
        if teile.path in seiten:
            return seiten[teile.path]
        if teile.path.startswith("/handy/"):
            return html(AUSGANG.replace("WEITER", weiter))
        if teile.path == KORB_PFAD:
            kopf = {"Set-Cookie": f"warenkorb={KORB}; Path=/"}
            ziel = json.dumps({"ziel": FOLGEADRESSE, "korb": KORB})
            return Antwort(200, "application/json", ziel, kopf)
        if teile.path == "/tarife/start":
            return umleitung("/tarife/alle.html")
        if teile.path in ("/tarife", "/tarife/alle.html"):
            return html(FOLGE)
        if teile.path == "/api/rate":
            monate = parse_qs(teile.query)["laufzeit"][0]
            rate = {"24": 41, "36": 35}[monate]
            return Antwort(200, "application/json", json.dumps({"rate": rate}))
        return Antwort(404)

    return antworte


def _ziel(server, weiter: Weiter | None, *pfade: str) -> Erkundungsziel:
    seiten = tuple(
        Seitenziel("beispielhandy-x", 256, server.adresse(p), weiter) for p in pfade
    )
    return Erkundungsziel("beispiel", "Beispielanbieter", seiten, None, 0.0)


def _erkunde(chromium, ziel, ausgabe: Path, robots: str = OFFEN) -> dict:
    def hole(url: str) -> tuple[int, str]:
        return 200, robots

    ende = time.monotonic() + 600
    return erkunde_anbieter(chromium, ziel, lambda: JETZT, hole, ausgabe, ende)


def _lies(ordner: Path, name: str):
    return json.loads((ordner / name).read_text(encoding="utf-8"))


def _texte(ordner: Path) -> dict[str, str]:
    texte = {}
    for datei in sorted(ordner.iterdir()):
        roh = datei.read_bytes()
        if datei.name.endswith(".gz"):
            roh = gzip.decompress(roh)
        texte[datei.name] = roh.decode("utf-8", errors="replace")
    return texte


def test_knopf_mit_post_fuehrt_zur_folgeseite_mit_eigenen_dateien(chromium, tmp_path):
    robots = "User-agent: *\nCrawl-delay: 1\nDisallow: /privat/\n"
    neu = tmp_path / "neu"
    with klickserver(_antworte()) as server:
        ziel = _ziel(server, KNOPF, "/handy/x")
        index = _erkunde(chromium, ziel, neu / "erkundung-beispiel", robots)

    assert (index["status"], index["grund"]) == ("gelesen", None)
    erste, folge = index["seiten"]
    assert [erste["nummer"], folge["nummer"], folge["folge_von"]] == [1, 2, 1]
    assert "folge_von" not in erste
    assert (folge["status"], folge["bot_schutz"], folge["http_status"]) == (
        "gelesen",
        False,
        200,
    )
    assert folge["adresse"] == server.adresse("/handy/x")
    assert folge["endadresse"] == server.adresse(FOLGEADRESSE)
    assert folge["weiter"] == {
        "selektor": KNOPF.selektor,
        "text": KNOPF.text,
        "treffer": 2,
        "sichtbar": 1,
        "geklickt": "Weiter zur Tarifauswahl",
        "von": server.adresse("/handy/x"),
        "nach": server.adresse(FOLGEADRESSE),
    }
    assert [p for p, _ in server.posts] == [KORB_PFAD]
    assert json.loads(server.posts[0][1]) == {
        "geraet": "beispielhandy-x",
        "speicher": "256",
    }
    assert server.mit("/handy/") == ["/handy/x", "/handy/x"]
    assert server.mit("/api/rate") == ["/api/rate?laufzeit=36", "/api/rate?laufzeit=24"]
    assert all(luecke >= 1 - 0.05 for luecke in server.luecken("/"))
    ordner = neu / "erkundung-beispiel" / "beispiel" / TAG
    dateien = folge["dateien"]
    assert dateien["bedienelemente"] == "bedienelemente-2.json"
    inventar = _lies(ordner, "bedienelemente-2.json")
    arten = {g["art"]: g for g in inventar["gruppen"]}
    laufzeit = [inventar["elemente"][i]["text"] for i in arten["laufzeit"]["elemente"]]
    assert laufzeit == ["24 Monate", "36 Monate"]
    preise = _lies(ordner, dateien["preise"])["preise"]
    assert any("35,99 €" in p["text"] for p in preise)
    proben = _lies(ordner, dateien["klicks"])["proben"]
    assert [p["text"] for p in proben] == ["24 Monate"]
    assert proben[0]["anfragen"][0]["url"].endswith("/api/rate?laufzeit=24")
    mitschnitt = _lies(ordner, dateien["mitschnitt"])
    post = [a for a in mitschnitt["anfragen"] if a["methode"] == "POST"]
    assert [a["url"] for a in post] == [server.adresse(KORB_PFAD)]
    antwort = next(a for a in mitschnitt["antworten"] if a["methode"] == "POST")
    assert json.loads(antwort["koerper"]) == {
        "ziel": FOLGEADRESSE,
        "korb": "[Cookie entfernt]",
    }
    alles = _texte(ordner)
    assert [name for name, text in alles.items() if KORB in text] == []
    zweig = tmp_path / "zweig"
    assert ea.einsortieren(neu, zweig) == ["beispiel"]
    assert ea.pruefe(zweig) == []
    abgelegt = sorted(p.name for p in (zweig / "beispiel" / TAG).iterdir())
    assert {"bedienelemente-2.json", "klicks-2.json", "mitschnitt-2.json"} <= set(
        abgelegt
    )


def test_link_folgt_der_umleitung_und_laesst_andere_links_liegen(chromium, tmp_path):
    with klickserver(_antworte(LINKS)) as server:
        index = _erkunde(chromium, _ziel(server, LINK, "/handy/x"), tmp_path)

    folge = index["seiten"][1]
    assert (folge["status"], folge["grund"]) == ("gelesen", None)
    assert folge["endadresse"] == server.adresse("/tarife/alle.html")
    assert folge["weiter"]["geklickt"] == "Zur Tarifauswahl"
    assert server.mit("/tarife") == ["/tarife/start", "/tarife/alle.html"]
    assert server.mit("/shop/") == []
    assert server.posts == []


@pytest.mark.parametrize(
    ("pfad", "seite", "erwartet"),
    [
        (
            "/shop/authentifizierung.html",
            NEUTRAL,
            "Anmeldung (Adresse: authentifizierung)",
        ),
        ("/schritt-2", ANMELDUNG, "Anmeldung (Passwortfeld)"),
        ("/bestellung/kasse", NEUTRAL, "Checkout (Adresse: kasse)"),
        ("/schritt-3", ZAHLUNG, "Zahlung (Karten- oder IBAN-Feld)"),
    ],
)
def test_anmeldung_checkout_oder_zahlung_als_folgeseite_ist_ein_befund(
    chromium, tmp_path, pfad, seite, erwartet
):
    link = f'<a class="primaer" href="{pfad}">Zur Tarifauswahl</a>'
    antworte = _antworte(link, **{pfad: html(seite)})
    with klickserver(antworte) as server:
        index = _erkunde(chromium, _ziel(server, LINK, "/handy/x"), tmp_path)

    folge = index["seiten"][1]
    grund = f"Folgeseite zeigt {erwartet}"
    assert (folge["status"], folge["grund"], folge["bot_schutz"]) == (
        "befund",
        grund,
        False,
    )
    assert (index["status"], index["grund"]) == ("befund", f"Seite 2: {grund}")
    proben = _lies(tmp_path / "beispiel" / TAG, folge["dateien"]["klicks"])["proben"]
    assert proben == []
    assert server.mit(pfad) == [pfad]
    assert server.abrufe[-1] == pfad
    assert server.posts == []


ZWEI_SICHTBAR = (
    '<button class="weiter-knopf">Weiter zur Tarifauswahl</button>'
    '<button class="weiter-knopf">Weiter zur Tarifauswahl</button>'
)


@pytest.mark.parametrize(
    ("weiter", "knoepfe", "erwartet"),
    [
        (
            Weiter(".gibt-es-nicht"),
            KNOEPFE,
            "Weiter-Knopf nicht gefunden: 0 Treffer, 0 sichtbar, 0 passend",
        ),
        (
            Weiter(".weiter-knopf", "Zur Kasse"),
            KNOEPFE,
            "Weiter-Knopf nicht gefunden: 2 Treffer, 1 sichtbar, 0 passend",
        ),
        (
            KNOPF,
            ZWEI_SICHTBAR,
            "Weiter-Knopf nicht eindeutig: 2 Treffer, 2 sichtbar, 2 passend",
        ),
        (
            Weiter("#angebot span"),
            "<span>Weiter zur Tarifauswahl</span>",
            "Weiter-Knopf „Weiter zur Tarifauswahl“ ist kein Knopf und kein Link"
            " (span)",
        ),
        (
            Weiter("#angebot button"),
            '<button class="weiter-knopf korb">Jetzt kaufen</button>',
            "Weiter-Knopf „Jetzt kaufen“ sieht nach Kauf, Kasse oder Anmeldung aus",
        ),
        (
            LINK,
            '<a class="primaer" href="/tarife/alle.html" target="_blank">'
            "Zur Tarifauswahl</a>",
            "Weiter-Knopf „Zur Tarifauswahl“ öffnet ein neues Fenster",
        ),
        (
            Weiter("#angebot button", "Weiter"),
            '<button type="button">Weiter</button>',
            "Weiter-Knopf führt nirgends hin: Adresse nach 1 s gleich",
        ),
    ],
)
def test_untauglicher_oder_fehlender_knopf_ist_ein_befund(
    chromium, tmp_path, monkeypatch, weiter, knoepfe, erwartet
):
    monkeypatch.setattr(klickfolgeseite, "WEITER_FRIST_MS", 1000)
    with klickserver(_antworte(knoepfe)) as server:
        index = _erkunde(chromium, _ziel(server, weiter, "/handy/x"), tmp_path)

    folge = index["seiten"][1]
    assert (folge["status"], folge["grund"]) == ("befund", erwartet)
    assert folge["dateien"]["bedienelemente"] == "bedienelemente-2.json"
    assert server.mit("/handy/") == ["/handy/x", "/handy/x"]
    assert server.mit("/tarife") == []
    assert server.posts == []


@pytest.mark.parametrize(
    ("weiter", "knoepfe", "robots", "verworfen", "methode"),
    [
        (LINK, LINKS, "Disallow: /tarife/", "/tarife/start", "GET"),
        (KNOPF, KNOEPFE, "Disallow: /frontend/", KORB_PFAD, "POST"),
    ],
)
def test_robots_sperrt_das_ziel_des_klicks(
    chromium, tmp_path, weiter, knoepfe, robots, verworfen, methode
):
    regeln = f"User-agent: *\n{robots}\n"
    with klickserver(_antworte(knoepfe)) as server:
        ziel = _ziel(server, weiter, "/handy/x")
        index = _erkunde(chromium, ziel, tmp_path, regeln)

    folge = index["seiten"][1]
    adresse = server.adresse(verworfen)
    assert folge["status"] == "gesperrt"
    assert folge["grund"].startswith(f"Weiter-Knopf: {methode} {adresse} ")
    assert "per robots.txt gesperrt" in folge["grund"]
    assert adresse in [v["url"] for v in folge["verworfen"]]
    assert server.mit(verworfen) == []
    assert server.mit("/tarife") == []
    assert server.posts == []


RADWARE = '{"seite": "Radware Bot Manager Captcha"}'


@pytest.mark.parametrize(
    ("weiter", "knoepfe", "pfad", "antwort"),
    [
        (LINK, LINKS, "/tarife/alle.html", html(PRUEFSEITE, 403)),
        (KNOPF, KNOEPFE, KORB_PFAD, Antwort(403, "application/json", "{}")),
        (KNOPF, KNOEPFE, KORB_PFAD, Antwort(200, "application/json", RADWARE)),
    ],
    ids=["folgeseite-403", "post-403", "post-challenge"],
)
def test_bot_schutz_der_folgeseite_beendet_den_anbieter(
    chromium, tmp_path, weiter, knoepfe, pfad, antwort
):
    with klickserver(_antworte(knoepfe, **{pfad: antwort})) as server:
        ziel = _ziel(server, weiter, "/handy/x", "/handy/y")
        index = _erkunde(chromium, ziel, tmp_path)

    erste, folge, zweite, zweite_folge = index["seiten"]
    assert [s["nummer"] for s in index["seiten"]] == [1, 3, 2, 4]
    assert erste["status"] == "gelesen"
    assert (folge["status"], folge["bot_schutz"], folge["folge_von"]) == (
        "gestoert",
        True,
        1,
    )
    assert server.mit("/handy/y") == []
    assert server.abrufe[-1] == pfad
    assert (zweite["status"], zweite["grund"]) == ("nicht_besucht", GRUND_NACH_BOT)
    assert (zweite_folge["status"], zweite_folge["grund"]) == (
        "nicht_besucht",
        GRUND_NACH_BOT,
    )
    assert zweite_folge["weiter"] == {"selektor": weiter.selektor, "text": weiter.text}
    assert index["status"] == "gestoert"


def test_ohne_gelesene_ausgangsseite_keine_folgeseite(chromium, tmp_path):
    with klickserver(_antworte(LINKS)) as server:
        ziel = _ziel(server, LINK, "/handy/x")
        index = _erkunde(chromium, ziel, tmp_path, "User-agent: *\nDisallow: /handy/\n")

    erste, folge = index["seiten"]
    assert erste["status"] == "gesperrt"
    assert folge["status"] == "nicht_besucht"
    assert folge["grund"].startswith("Ausgangsseite 1 gesperrt: per robots.txt")
    assert (folge["dateien"], folge["karte"], folge["folge_von"]) == ({}, None, 1)
    assert server.abrufe == []
