"""„Bei Telekom nur mit 256 GB gelesen“ statt „Seite sperrt automatisches Lesen“.

Antonio, 10.10.2026: Beim Google Pixel 10 (128 GB) stand in der Telekom-Zeile „Telekom
nicht erfasst: Seite sperrt automatisches Lesen (HTTP 202, 10.10.2026)“. Die Telekom-
Übersichten waren ganz gelesen und führten das Pixel 10 mit 256 GB; erst eine spätere
Produktseite war gestört. Ein Gerät, das der Lauf von heute mit anderem Speicher gelesen
hat, bekommt darum den Satz mit diesen Speichern; der Anbietergrund bleibt für Geräte,
die der Lauf gar nicht gelesen hat (ein unbekannter Titel lässt „nicht im Angebot“
offen, wie am 10.10.). Gegenprobe: eine Datei von gestern gibt keinen Satz.
Datum fest.
"""

from __future__ import annotations

import pytest
from bestand_pfad import lese_wurzel

from telco_radar.analyze.klick_erfassung import fuer_modell
from telco_radar.analyze.klick_zusammenfuehrung import fuehre_zusammen
from telco_radar.collect.geraete.klicklauf import LAUF_GELESEN, LAUF_GESTOERT
from telco_radar.geraete_config import lade_katalog

TAG = "2026-10-10"
ADRESSE = "https://www.telekom.de/shop/geraete/smartphones?tariffId=MF_17791"
GESPERRT = (
    "https://www.telekom.de/shop/geraet/x: Abruf gestört (HTTP 202 auf "
    "https://www.telekom.de/resources/ag2/legalnote-replacer/build/p.js)"
)
PIXEL = "google-pixel-10"
SATZ = "Bei Telekom nur mit 256 GB gelesen (10.10.2026)"


@pytest.fixture(scope="module")
def katalog():
    return lade_katalog(lese_wurzel())


def _datei(datum: str = TAG) -> dict:
    satz = {
        "titel": "Google Pixel 10 256 GB",
        "speicher_gb": 256,
        "tarif_name": "MagentaMobil M",
        "tarif_slug": "MF_17791",
        "tarif_monatlich": 49.95,
        "geraet_zuzahlung": 1.0,
        "geraet_monatsrate": 20.2,
        "anschlusspreis": 39.95,
        "laufzeit_monate": 36,
        "url": "https://www.telekom.de/shop/geraet/google/google-pixel-10/x-256-gb",
    }
    uebersicht = {
        "adresse": ADRESSE,
        "status": LAUF_GELESEN,
        "grund": None,
        "saetze": [satz, {**satz, "titel": "Beispielfon Z9 256 GB"}],
        "vollstaendig": True,
        "unvollstaendig": None,
    }
    return {
        "anbieter": "telekom",
        "name": "Telekom",
        "datum": datum,
        "format": 1,
        "laufstatus": LAUF_GESTOERT,
        "grund": GESPERRT,
        "seiten": [],
        "uebersichten": [uebersicht],
    }


def _modell(gruende: dict, device_id: str) -> dict[str, str]:
    return fuer_modell(gruende, {"karten": [], "device_id": device_id})


def test_anderer_speicher_gelesen_nennt_die_speicher(katalog):
    zug = fuehre_zusammen([], [_datei()], katalog, TAG, lambda sku: ("", None))
    assert _modell(zug.erfassung, PIXEL) == {"Telekom": SATZ}


def test_nicht_gelesenes_geraet_behaelt_den_anbietergrund(katalog):
    zug = fuehre_zusammen([], [_datei()], katalog, TAG, lambda sku: ("", None))
    grund = _modell(zug.erfassung, "apple-iphone-17-pro")["Telekom"]
    assert grund.startswith("Telekom nicht erfasst: Seite sperrt")


def test_gegenprobe_datei_von_gestern_kein_speichersatz(katalog):
    gestern = _datei("2026-10-09")
    zug = fuehre_zusammen([], [gestern], katalog, TAG, lambda s: ("", None))
    assert _modell(zug.erfassung, PIXEL).get("Telekom") != SATZ
