"""Klick-Crawler lädt wie ein Browser (Antonio, 11.10.2026, Wahl „c“).

Seitenaufrufe (Dokumente) halten den eigenen Abstand ``rate_limit_sekunden``, die
Unterressourcen einer Seite (Skripte, Stylesheets, XHR) nicht; der Crawl-delay aus
robots.txt gilt für beide. Nach einem Klick auf der Folgeseite endet das Warten, sobald
die Zusammenfassung einen neuen Text zeigt, auch wenn Nebenabrufe der Seite weiterlaufen
(Vodafone, Handlauf klick.yml 38117052694: etwa 15 s je Tarifklick ohne Ruhe).
Ein lokaler Server auf 127.0.0.1 liefert BEISPIEL-Seiten, von Hand geschrieben.
"""

from __future__ import annotations

import time
from types import SimpleNamespace

import pytest
from klickserver import JETZT, Antwort, html, klickserver

from telco_radar.collect.geraete.klickkarte import klickkarte_aus_daten
from telco_radar.collect.geraete.robots import RobotsWaechter

ADRESSE = "https://beispiel.invalid/handy/x"
ABSTAND = 1.5
FRIST_MS = 4000
SKRIPTE = 3
KARTE = klickkarte_aus_daten(
    {
        "anbieter": "Beispielanbieter",
        "knoepfe": {
            "speicher": {"fest": "256 GB"},
            "tarif": {"fest": "M"},
            "laufzeit": {"fest": "36"},
        },
        "zusammenfassung": {"selektor": "#preis"},
        "antwort": {
            "skript": "#daten",
            "pfade": {"rate": "rate", "ratenzahl": "raten"},
            "variante": {"speicher": "speicher"},
        },
        "kanarie": {"selektor": "#kanarie", "enthaelt": "Beispielhandy X"},
    },
    "B",
)
SEITE = (
    "<!doctype html><html><head>"
    + "".join(f'<script src="/s/{i}.js"></script>' for i in range(SKRIPTE))
    + "</head><body><p>BEISPIEL: von Hand geschrieben, kein echter Anbieter.</p>"
    '<h1 id="kanarie">Beispielhandy X</h1>'
    '<section id="preis">Monatliche Rate 30,00 € · 36 Raten</section>'
    '<script id="daten" type="application/json">'
    '{"speicher": "256 GB", "rate": 30.0, "raten": 36}</script>'
    "</body></html>"
)


def _antworte(pfad: str) -> Antwort:
    if pfad == "/handy/x":
        return html(SEITE)
    if pfad.startswith("/s/"):
        return Antwort(200, "application/javascript", "var a = 1;")
    return Antwort(404)


def _schleuse(robots: str, rate: float):
    from telco_radar.collect.geraete.klicktor import Hostschleuse

    waechter = RobotsWaechter(hole=lambda url: (200, robots))
    return Hostschleuse(waechter, lambda: JETZT, rate)


def _dauer(passiere) -> float:
    passiere(ADRESSE)
    beginn = time.monotonic()
    passiere(ADRESSE)
    return time.monotonic() - beginn


def test_unterressource_wartet_nicht_auf_den_eigenen_abstand():
    schleuse = _schleuse("User-agent: *\n", 0.5)

    assert _dauer(schleuse.passiere_unterressource) < 0.2
    assert _dauer(schleuse.passiere) >= 0.5


def test_crawl_delay_gilt_auch_fuer_unterressourcen():
    schleuse = _schleuse("User-agent: *\nCrawl-delay: 0.5\n", 0.0)

    assert _dauer(schleuse.passiere_unterressource) >= 0.5


@pytest.mark.browser
def test_skripte_der_seite_folgen_ohne_eigenen_abstand(chromium):
    from telco_radar.collect.geraete.klickcrawler import klicke_durch

    schleuse = _schleuse("User-agent: *\n", ABSTAND)
    waechter = RobotsWaechter(hole=lambda url: (200, "User-agent: *\n"))
    with klickserver(_antworte) as server:
        lauf = klicke_durch(
            chromium,
            server.adresse("/handy/x"),
            KARTE,
            waechter,
            lambda: JETZT,
            schleuse=schleuse,
            frist_ms=FRIST_MS,
        )

    assert lauf.status == "gelesen"
    assert len(server.mit("/s/")) == SKRIPTE
    assert max(server.luecken(("/handy/", "/s/"))) < ABSTAND


def _wache(seite_, karte_):
    from telco_radar.collect.geraete.klicklauf import Klicklauf
    from telco_radar.collect.geraete.klickwache import Wache

    tor = SimpleNamespace(
        stoerung=None, umleitung=None, pruefung=SimpleNamespace(url=None, offen=False)
    )
    lauf = Klicklauf(anbieter="Beispielanbieter", adresse=ADRESSE)
    return Wache(seite_, karte_, tor, lauf, FRIST_MS)


def _warte_nach_klick(chromium, neuer_text: str | None, mit_anzeige: bool) -> float:
    seite_ = chromium.new_page()
    try:
        seite_.route("**/nebenabruf", lambda route: None)
        seite_.set_content('<section id="preis">Summe 10 €</section>')
        wache = _wache(seite_, KARTE)
        seite_.evaluate(
            "() => { fetch('https://beispiel.invalid/nebenabruf').catch(() => {}); }"
        )
        if mit_anzeige:
            wache.anzeige = lambda: seite_.inner_text("#preis")
        wache.marke()
        if neuer_text is not None:
            seite_.evaluate(
                "(t) => setTimeout(() => {"
                " document.getElementById('preis').innerText = t; }, 300)",
                neuer_text,
            )
        beginn = time.monotonic()
        wache.warte_ruhe()
        return time.monotonic() - beginn
    finally:
        seite_.close()


@pytest.mark.browser
def test_neuer_text_beendet_das_warten_trotz_nebenabruf(chromium):
    assert _warte_nach_klick(chromium, "Summe 20 €", mit_anzeige=True) < 2.0


@pytest.mark.browser
def test_gegenprobe_ohne_anzeige_wartet_die_frist(chromium):
    assert _warte_nach_klick(chromium, "Summe 20 €", mit_anzeige=False) >= 3.5


@pytest.mark.browser
def test_gegenprobe_gleicher_text_wartet_die_frist(chromium):
    assert _warte_nach_klick(chromium, None, mit_anzeige=True) >= 3.5
