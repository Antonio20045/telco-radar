"""Grenzen des Weiter-Schritts im Lauf: Frist und Sperren (Prüferbefunde zu 6b9c3dd0).

BEISPIEL-Seiten aus ``test_geraete_klickweiter``. ``klicke_durch`` verspricht: schneidet
die Frist Kombinationen ab, ist der Lauf ``zeitgrenze``, und jede nicht besuchte heißt
„nicht besucht: Zeitgrenze erreicht“; das gilt auch, wenn die Frist genau nach dem
Warenkorb-POST abläuft und das Tor die Navigation in die Strecke verwirft. Gelesene
Kacheln bleiben, die Kachel 24 seit 08.10.2026 aus sich selbst (``klickkachel``).
Gegenprobe: derselbe Ablauf ohne ``weiter``. Nur eine Sperre von Dokument oder POST des
Klicks beendet den Lauf als gesperrt; sperrt robots.txt nur einen
Zähler, den die Seite beim Klick holt, heißt die Kombination „führt nirgends hin“, und
der nächste Speicher wird versucht. Keine Anfrage verlässt den Rechner.
"""

from __future__ import annotations

import math
from urllib.parse import urlsplit

import pytest
import test_geraete_klickweiter as weiter
from klickbeispiel import antworter, karte, nach_auswahl, preis, seite
from klickserver import JETZT, Antwort, html, klickserver, laufe

pytestmark = pytest.mark.browser

ZAEHLER = weiter.START_SKRIPT.replace(
    'fetch("/korb"', 'fetch("/zaehler/klick"); if (false) fetch("/korb"'
)
OHNE_WEITER = """
<div id="speicher"><button aria-pressed="true" data-wert="128">128</button>
<button aria-pressed="false" data-wert="256">256</button></div>
<div id="tarif"><button aria-pressed="true" data-wert="S">S</button></div>
<div id="laufzeit"><button aria-pressed="true" data-wert="24">24</button></div>
<div id="preis"></div>"""
OHNE_WEITER_SKRIPT = """
const wahl = () => Object.fromEntries(["speicher", "tarif", "laufzeit"].map((d) =>
  [d, document.querySelector('#' + d + ' [aria-pressed="true"]').dataset.wert]));
for (const k of document.querySelectorAll("button")) {
  k.addEventListener("click", () => {
    for (const a of k.parentElement.querySelectorAll("button"))
      a.setAttribute("aria-pressed", String(a === k));
    lade(wahl());
  });
}
lade(wahl());"""
NIRGENDS = "Weiter-Knopf führt nirgends hin: Adresse nach 1 s gleich"


def _mit_frist(chromium, antworte, k, ab: int):
    """Lauf mit ``Fristschleuse``; die Frist endet mit dem ``ab``-ten Abruf von
    ``/korb`` oder ``/api/preis``."""
    from telco_radar.collect.geraete.klickcrawler import klicke_durch
    from telco_radar.collect.geraete.klickseite import Fristschleuse
    from telco_radar.collect.geraete.klicktor import Hostschleuse
    from telco_radar.collect.geraete.robots import RobotsWaechter

    waechter = RobotsWaechter(hole=lambda url: (200, "User-agent: *\n"))
    schleuse = Fristschleuse(Hostschleuse(waechter, lambda: JETZT), math.inf)
    gezaehlt: list[str] = []

    def mit_ende(pfad: str) -> Antwort:
        if urlsplit(pfad).path in ("/korb", "/api/preis"):
            gezaehlt.append(pfad)
            if len(gezaehlt) >= ab:
                schleuse.setze(-math.inf)
        return antworte(pfad)

    with klickserver(mit_ende) as server:
        lauf = klicke_durch(
            chromium,
            server.adresse("/handy/x"),
            k,
            waechter,
            lambda: JETZT,
            schleuse=schleuse,
            frist_ms=3000,
            frist=schleuse.offen,
        )
    return lauf, server


def test_frist_endet_im_ersten_weiter_lauf_heisst_zeitgrenze(chromium):
    lauf, server = _mit_frist(chromium, weiter._antworter(), karte(**weiter.KARTE), 1)

    assert lauf.status == "zeitgrenze", lauf.grund
    assert server.mit("/korb") == ["/korb"]
    assert server.mit("/bestellung") == []
    assert {e.variante.speicher: e.grund for e in lauf.ergebnisse} == {
        "128": "nicht besucht: Zeitgrenze erreicht",
        "256": "nicht besucht: Zeitgrenze erreicht",
    }


def test_frist_endet_im_zweiten_weiter_gelesene_kacheln_bleiben(chromium):
    lauf, server = _mit_frist(chromium, weiter._antworter(), karte(**weiter.KARTE), 2)

    erfasst = {
        (e.variante.speicher, e.variante.laufzeit)
        for e in lauf.ergebnisse
        if e.status == "erfasst"
    }
    assert lauf.status == "zeitgrenze", lauf.grund
    assert erfasst == {("128", 24), ("128", 36)}
    assert server.mit("/korb") == ["/korb", "/korb"]
    assert {e.grund for e in lauf.ergebnisse if e.variante.speicher == "256"} == {
        "nicht besucht: Zeitgrenze erreicht"
    }


def test_gegenprobe_ohne_weiter_ist_es_ebenfalls_zeitgrenze(chromium):
    def rechne(frage):
        laufzeit = int(frage["laufzeit"])
        return {
            "preis": preis(frage["speicher"], frage["tarif"], laufzeit),
            "auswahl": frage,
        }

    k = karte(
        knoepfe={
            "speicher": {"selektor": "#speicher button", "wert": "data-wert"},
            "tarif": {"selektor": "#tarif button", "wert": "data-wert"},
            "laufzeit": {"selektor": "#laufzeit button", "wert": "data-wert"},
            "gewaehlt": {"attribut": "aria-pressed", "wert": "true"},
        }
    )
    seite_html = seite(OHNE_WEITER, OHNE_WEITER_SKRIPT)
    lauf, _ = _mit_frist(chromium, antworter(seite_html, rechne), k, 1)

    assert lauf.status == "zeitgrenze", lauf.grund
    assert "256" in {v[0] for v in nach_auswahl(lauf)}


def _mit_robots(chromium, skript: str, regeln: str):
    start = seite(weiter.START.replace("@TEXT@", "Weiter zur Tarifauswahl"), skript)

    def antworte(pfad: str) -> Antwort:
        return html(start) if urlsplit(pfad).path == "/handy/x" else Antwort(204)

    with klickserver(antworte) as server:
        k = karte(**weiter.KARTE)
        lauf = laufe(chromium, server.adresse("/handy/x"), k, regeln, frist_ms=3000)
    return lauf, server


def test_fremde_sperre_macht_den_lauf_nicht_gesperrt(chromium, monkeypatch):
    from telco_radar.collect.geraete import klickweiter

    monkeypatch.setattr(klickweiter, "WEITER_FRIST_MS", 1000)
    lauf, server = _mit_robots(
        chromium, ZAEHLER, "User-agent: *\nDisallow: /zaehler/\n"
    )

    assert lauf.status != "gesperrt", lauf.grund
    assert {(e.variante.speicher, e.grund) for e in lauf.ergebnisse} == {
        ("128", NIRGENDS),
        ("256", NIRGENDS),
    }
    assert [urlsplit(v.url).path for v in lauf.verworfen] == ["/zaehler/klick"] * 2
    assert server.mit("/zaehler") == []


def test_gegenprobe_gesperrter_warenkorb_post_sperrt_den_lauf(chromium, monkeypatch):
    from telco_radar.collect.geraete import klickweiter

    monkeypatch.setattr(klickweiter, "WEITER_FRIST_MS", 1000)
    skript = weiter.START_SKRIPT
    lauf, server = _mit_robots(chromium, skript, "User-agent: *\nDisallow: /korb\n")

    assert lauf.status == "gesperrt"
    assert lauf.grund.startswith(f"Weiter-Knopf: POST {server.adresse('/korb')} ")
    assert server.posts == []
    assert lauf.ergebnisse == []
