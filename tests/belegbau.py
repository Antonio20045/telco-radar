"""Bausteine für die Tests des Beleg-Archivs: Karte, Text, Antwort, Bild, Beleg.

Alles ist ein BEISPIEL wie ``tests/fixtures/klickcrawler/``: kein echter Anbieter.
Zeitpunkte sind fest, nie die Uhr.
"""

from __future__ import annotations

import io
import json
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

from PIL import Image

from telco_radar.collect.geraete.klickbeleg import (
    Beleg,
    Belegdatei,
    Belegpaket,
    Belegquelle,
    baue_beleg,
)
from telco_radar.collect.geraete.klickecho import Variante, lies_antwort
from telco_radar.collect.geraete.klickhar import Antwortkopie
from telco_radar.collect.geraete.klickkarte import lade_klickkarte
from telco_radar.collect.geraete.klicktext import lies_zusammenfassung

FIXTURES = Path(__file__).parent / "fixtures" / "klickcrawler"
ZEIT = datetime(2026, 10, 3, 5, 0, tzinfo=UTC)
PREIS_URL = "http://127.0.0.1:8000/api/preis?speicher=256&tarif=S&laufzeit=24"
TEXT = "\n".join(
    [
        "Ihre Auswahl: 256 GB · Tarif S · 24 Monate",
        "Einmalige Anzahlung 1.099,00 €",
        "Monatliche Gerätrate 25,00 € · 24 Raten",
        "Tarif S: 29,99 € mtl. in den Monaten 1–24, ab dem 25. Monat 34,99 € mtl.",
        "Mindestlaufzeit 24 Monate",
        "Anschlusspreis 39,99 €",
        "Datenvolumen 25 GB",
    ]
)
NUTZLAST = {
    "auswahl": {"speicher": "256", "tarif": "S", "laufzeit": "24"},
    "preis": {"anzahlung": 1099.0, "rate": 25.0, "raten": 24},
    "tarif": {
        "phasen": [
            {"ab": 1, "bis": 24, "betrag": 29.99},
            {"ab": 25, "bis": None, "betrag": 34.99},
        ],
        "mindestlaufzeit": 24,
        "anschluss": 39.99,
        "volumen_gb": 25,
    },
}


def karte():
    return lade_klickkarte(FIXTURES / "beispiel_karte.yaml")


def png(farbe: tuple[int, int, int] = (200, 30, 30)) -> bytes:
    bild = Image.new("RGB", (40, 20), farbe)
    bild.putpixel((3, 4), (0, 0, 0))
    ziel = io.BytesIO()
    bild.save(ziel, "PNG")
    return ziel.getvalue()


def antwortkopie(nutzlast: dict | None = None, **kopf: str) -> Antwortkopie:
    daten = json.dumps(nutzlast or NUTZLAST).encode("utf-8")
    return Antwortkopie(
        methode="GET",
        url=PREIS_URL,
        anfragekopf={"accept": "*/*", **kopf},
        status=200,
        statustext="OK",
        antwortkopf={"content-type": "application/json", **kopf},
        koerper=daten,
    )


def quelle(**ersetzt) -> Belegquelle:
    k = karte()
    werte = lies_antwort(NUTZLAST, k.antwort, PREIS_URL).werte
    assert werte == lies_zusammenfassung(TEXT)
    grund = Belegquelle(
        anbieter="Beispielanbieter",
        adresse="http://127.0.0.1:8000/handy/beispielhandy-x",
        seite="http://127.0.0.1:8000/handy/beispielhandy-x",
        http_status=200,
        variante=Variante("256", "S", 24),
        status="erfasst",
        werte=werte,
        text=TEXT,
        screenshot_png=png(),
        antwort=antwortkopie(),
    )
    return replace(grund, **ersetzt)


def paket(zeit: datetime = ZEIT, **ersetzt) -> Belegpaket:
    fertig, grund = baue_beleg(quelle(**ersetzt), karte(), zeit)
    assert grund is None
    assert fertig is not None
    return fertig


def beleg(zeitpunkt: str, werte: dict, kennung: str, **variante) -> Beleg:
    """Ein Beleg mit festen Feldern für die Aufbewahrung; Dateien nur benannt."""
    datei = Belegdatei(f"{kennung}.webp", "image/webp", "0" * 64, 1)
    har = Belegdatei(f"{kennung}.har", "application/json", "0" * 64, 1)
    return Beleg(
        beleg_id=kennung,
        anbieter="Beispielanbieter",
        zeitpunkt=zeitpunkt,
        adresse="http://127.0.0.1:8000/handy/beispielhandy-x",
        seite="http://127.0.0.1:8000/handy/beispielhandy-x",
        http_status=200,
        antwort_url=PREIS_URL,
        antwort_status=200,
        variante={"speicher": "256", "tarif": "S", "laufzeit": 24, **variante},
        status="erfasst",
        werte=werte,
        fundstellen=(),
        bild=datei,
        mitschnitt=har,
    )
