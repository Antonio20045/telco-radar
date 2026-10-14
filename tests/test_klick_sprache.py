"""Sprache des Klick-Browsers: Seiten übersetzen sich nach ``navigator.language``.

congstar übersetzt seit dem 14.10.2026 im Browser (``data-csi18n``): der englische
Browser in Actions las „Storage:“ statt „Speicher:“, der Kanarienwert fehlte und der
Klick-Tageslauf brach nach drei Seiten ab. Ein lokaler Server auf 127.0.0.1 liefert eine
BEISPIEL-Seite, von Hand geschrieben, die je nach Browsersprache den Gerätenamen
deutsch oder englisch schreibt.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from urllib.parse import parse_qs, urlsplit

from klickserver import Antwort, html, klickserver
from test_geraete_klickfolge import OFFEN, RATE, TARIFE

from telco_radar.collect.geraete.klickcrawler import klicke_durch
from telco_radar.collect.geraete.klickkarte import klickkarte_aus_daten
from telco_radar.collect.geraete.klickkontext import SPRACHE
from telco_radar.collect.geraete.klicktor import Hostschleuse
from telco_radar.collect.geraete.robots import RobotsWaechter

JETZT = datetime(2026, 10, 14, 5, 0, tzinfo=UTC)
KARTE = klickkarte_aus_daten(
    {
        "anbieter": "Beispielanbieter",
        "knoepfe": {
            "speicher": {"selektor": "#speicher button", "wert": "data-wert"},
            "tarif": {"selektor": "#tarif button", "wert": "data-wert"},
            "laufzeit": {"selektor": "#laufzeit button", "wert": "data-wert"},
            "gewaehlt": {"attribut": "aria-pressed", "wert": "true"},
        },
        "zusammenfassung": {"selektor": "#preis"},
        "antwort": {
            "url_muster": r"/api/preis\?",
            "pfade": {"rate": "rate"},
            "parameter": {"tarif": "tarif"},
        },
        "kanarie": {"selektor": "#kanarie", "enthaelt": "Beispielhandy X"},
    },
    "Prüfkarte",
)

UEBERSETZT = TARIFE.replace(
    "<script>",
    "<script>\nif (!navigator.language.startsWith('de')) "
    "document.getElementById('kanarie').innerText = 'Example phone X';\n",
    1,
)


def _laufe(chromium, adresse: str):
    waechter = RobotsWaechter(hole=lambda url: (200, OFFEN))
    schleuse = Hostschleuse(waechter, lambda: JETZT)
    return klicke_durch(
        chromium, adresse, KARTE, waechter, lambda: JETZT, schleuse=schleuse
    )


def _antworte(pfad: str) -> Antwort:
    teile = urlsplit(pfad)
    if teile.path == "/handy/x":
        return html(UEBERSETZT)
    tarif = parse_qs(teile.query)["tarif"][0]
    return Antwort(200, "application/json", json.dumps({"rate": RATE[tarif]}))


def test_browser_spricht_deutsch_und_liest_die_deutsche_seite(chromium):
    with klickserver(_antworte) as server:
        lauf = _laufe(chromium, server.adresse("/handy/x"))

    assert SPRACHE == "de-DE"
    assert lauf.status == "gelesen", lauf.grund
    assert {e.variante.tarif: e.werte.rate for e in lauf.ergebnisse} == {
        "S": 20.0,
        "M": 30.0,
        "L": 40.0,
    }


def test_gegenprobe_englische_seite_faellt_am_kanarienwert(chromium, monkeypatch):
    from telco_radar.collect.geraete import klickkontext

    monkeypatch.setattr(klickkontext, "SPRACHE", "en-US")
    with klickserver(_antworte) as server:
        lauf = _laufe(chromium, server.adresse("/handy/x"))

    assert lauf.status == "gestoert"
    assert "Kanarienwert fehlt" in lauf.grund
