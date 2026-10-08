"""Laden der Hauptseite (``klickladung``): Fortschritt statt fester Frist, Diagnose.

Vodafone im Tageslauf vom 08.10.2026 (Actions-Lauf 37740022815): HTTP 200, aber „Seite
nach 30000 ms nicht geladen“; rund 43 Anfragen an www.vodafone.de standen noch im Tor,
das je Host nur eine Anfrage hinauslässt. Die BEISPIEL-Seite bildet das verkleinert
nach: viele Skripte desselben Hosts, jedes mit Serververzug, zusammen länger als die
(hier verkürzte) Frist. Keine Anfrage verlässt den Rechner.
"""

from __future__ import annotations

import pytest
from klickbeispiel import laufe_mit
from klickserver import Antwort, html

from telco_radar.collect.geraete import klickladung
from telco_radar.collect.geraete.klickkarte import klickkarte_aus_daten
from telco_radar.collect.geraete.klicklauf import (
    LAUF_GELESEN,
    LAUF_GESTOERT,
    STOERUNG_ZEIT,
)

pytestmark = pytest.mark.browser

FRIST_MS = 1000
SKRIPTE = 12
VERZUG_S = 0.15
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


def _antworter(skripte: int, verzug: float):
    koepfe = "".join(f'<script src="/s/{i}.js"></script>' for i in range(skripte))
    seite = (
        f"<!doctype html><html><head>{koepfe}</head><body>"
        "<p>BEISPIEL: von Hand geschrieben, kein echter Anbieter.</p>"
        '<h1 id="kanarie">Beispielhandy X</h1>'
        '<section id="preis">Monatliche Rate 30,00 € · 36 Raten</section>'
        '<script id="daten" type="application/json">'
        '{"speicher": "256 GB", "rate": 30.0, "raten": 36}</script>'
        "</body></html>"
    )

    def antworte(pfad: str) -> Antwort:
        if pfad == "/handy/x":
            return html(seite)
        if pfad.startswith("/s/"):
            return Antwort(200, "application/javascript", "var a = 1;", verzug=verzug)
        return Antwort(404)

    return antworte


@pytest.fixture
def kurze_frist(monkeypatch):
    monkeypatch.setattr(klickladung, "SEITEN_FRIST_MS", FRIST_MS)
    monkeypatch.setattr(klickladung, "LADE_HOECHSTENS_MS", 20 * FRIST_MS)


def test_seite_laedt_solange_antworten_kommen(chromium, kurze_frist):
    """12 Skripte zu je 0,15 s nacheinander dauern länger als die Frist von 1 s; vor
    dem Fortschrittswarten hieß das „Seite nach 1000 ms nicht geladen“."""
    lauf, server = laufe_mit(chromium, _antworter(SKRIPTE, VERZUG_S), KARTE)

    assert len(server.mit("/s/")) == SKRIPTE
    assert lauf.status == LAUF_GELESEN, lauf.grund
    assert lauf.stoerung is None
    ladung = lauf.ladung
    assert ladung["wartet_auf"] == "load"
    assert (ladung["geladen"], ladung["dokument"], ladung["offen"]) == (
        True,
        "complete",
        {},
    )
    assert ladung["anfragen"] == ladung["beendet"] >= SKRIPTE + 1
    assert ladung["takte_ms"] > FRIST_MS


def test_ohne_neue_antwort_ist_es_eine_benannte_zeitueberschreitung(
    chromium, kurze_frist
):
    """Gegenprobe: ein Skript hängt länger als die Frist, ohne dass etwas fertig wird;
    die Seite ist gestört mit ``zeitueberschreitung``, nicht mit Bot-Schutz."""
    lauf, _ = laufe_mit(chromium, _antworter(1, 3 * FRIST_MS / 1000), KARTE)

    assert lauf.status == LAUF_GESTOERT
    assert lauf.stoerung == STOERUNG_ZEIT
    assert lauf.grund.startswith("Seite nach ")
    assert lauf.grund.endswith(f"({FRIST_MS} ms ohne neue Antwort)")
    assert lauf.ergebnisse == []
    ladung = lauf.ladung
    assert (ladung["geladen"], ladung["offen"]) == (False, {"127.0.0.1": 1})
    assert ladung["dokument"] != "complete"
    assert ladung["ohne_antwort_ms"] == FRIST_MS
