"""Option nur in anderer Farbe (``knoepfe.<dimension>.andere_farbe``) im Lauf.

Muster congstar (Pixel 11, Tageslauf 08.10.2026, Fixture
``congstar_produkt_pixel11.html.gz``): der Speicherknopf „512 GB nicht vorhanden“ ist
nicht disabled, die Seite führt 512 GB in einer anderen Farbe. Die Karte klickt keine
Farbe: ``nicht_erfasst`` mit Grund, nie ``nicht_angeboten``. Gegenprobe auf derselben
BEISPIEL-Seite: ein disabled Knopf, den keine Farbe führt, bleibt ``nicht_angeboten``.
Keine Anfrage verlässt den Rechner.
"""

from __future__ import annotations

import pytest
from klickbeispiel import laufe_mit
from klickserver import Antwort, html

from telco_radar.collect.geraete.klickkarte import klickkarte_aus_daten
from telco_radar.collect.geraete.klicklauf import (
    ERFASST,
    GRUND_ANDERE_FARBE,
    LAUF_GELESEN,
    NICHT_ANGEBOTEN,
    NICHT_ERFASST,
)

pytestmark = pytest.mark.browser

KARTE = klickkarte_aus_daten(
    {
        "anbieter": "Beispielanbieter",
        "knoepfe": {
            "speicher": {
                "selektor": "#speicher button",
                "wert": "aria-label",
                "muster": r"^(\d+\s*[GT]B)\b",
                "andere_farbe": '[aria-label$=" nicht vorhanden"]',
            },
            "tarif": {"fest": "M"},
            "laufzeit": {"fest": "36"},
            "gewaehlt": {"attribut": "aria-pressed", "wert": "true"},
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
SEITE = """<!doctype html><html><body>
<p>BEISPIEL: von Hand geschrieben, kein echter Anbieter.</p>
<h1 id="kanarie">Beispielhandy X</h1>
<div id="speicher">
  <button type="button" aria-pressed="true" aria-label="128 GB">128 GB</button>
  <button type="button" aria-pressed="false" aria-label="256 GB nicht vorhanden">
    256 GB</button>
  <button type="button" aria-pressed="false" aria-label="512 GB" disabled>
    512 GB</button>
</div>
<section id="preis">Monatliche Rate 30,00 € · 36 Raten</section>
<script id="daten" type="application/json">
{"speicher": "128 GB", "rate": 30.0, "raten": 36}</script>
</body></html>"""


def _antworte(pfad: str) -> Antwort:
    return html(SEITE) if pfad == "/handy/x" else Antwort(404)


def test_nur_in_anderer_farbe_ist_nicht_erfasst_nie_nicht_angeboten(chromium):
    lauf, server = laufe_mit(chromium, _antworte, KARTE)

    assert lauf.status == LAUF_GELESEN, lauf.grund
    je_speicher = {e.variante.speicher: e for e in lauf.ergebnisse}
    assert je_speicher["128 GB"].status == ERFASST
    anders = je_speicher["256 GB"]
    assert (anders.status, anders.grund) == (
        NICHT_ERFASST,
        f"speicher 256 GB {GRUND_ANDERE_FARBE}",
    )
    gesperrt = je_speicher["512 GB"]
    assert (gesperrt.status, gesperrt.grund) == (
        NICHT_ANGEBOTEN,
        "Seite bietet speicher 512 GB nicht an",
    )
    assert server.abrufe == ["/handy/x"]
