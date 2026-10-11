"""„Bei Telekom nur mit 256 GB gelesen“ statt „Seite sperrt automatisches Lesen“.

Antonio, 10.10.2026: Beim Google Pixel 10 (128 GB) stand in der Telekom-Zeile „Telekom
nicht erfasst: Seite sperrt automatisches Lesen (HTTP 202, 10.10.2026)“. Die Telekom-
Übersichten waren ganz gelesen und führten das Pixel 10 mit 256 GB; erst eine spätere
Produktseite war gestört. Ein Gerät, das der Lauf von heute mit anderem Speicher gelesen
hat, bekommt darum den Satz mit diesen Speichern; der Anbietergrund bleibt für Geräte,
die der Lauf gar nicht gelesen hat (ein unbekannter Titel lässt „nicht im Angebot“
offen, wie am 10.10.). Nach dem ungestörten Lauf vom 10.10. 15:59 UTC stand beim
Pixel 10 (128 GB) „Für dieses Modell ist bei Telekom kein Bündel erhoben“: der Satz gilt
für jeden Lauf von heute, gestört oder nicht. Gegenprobe: eine Datei von gestern gibt
keinen Satz. Datum fest.
"""

from __future__ import annotations

import pytest
from bestand_pfad import lese_wurzel

from telco_radar.analyze.klick_angebot import angebot_aus
from telco_radar.analyze.klick_erfassung import (
    SATZ_SPEICHER,
    SATZ_SPEICHER_ANGEBOT,
    angebotene_speicher,
    erfassungsgruende,
    fuer_modell,
)
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


def _datei(datum: str = TAG, laufstatus: str = LAUF_GESTOERT) -> dict:
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
        "laufstatus": laufstatus,
        "grund": GESPERRT if laufstatus == LAUF_GESTOERT else None,
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


def test_ungestoerter_lauf_nennt_die_speicher(katalog):
    datei = _datei(laufstatus=LAUF_GELESEN)
    zug = fuehre_zusammen([], [datei], katalog, TAG, lambda sku: ("", None))
    assert _modell(zug.erfassung, PIXEL) == {"Telekom": SATZ}


def test_auf_jobs_verteilter_anbieter_nennt_alle_gelesenen_speicher():
    """Telekom auf vier Jobs (11.10.2026): die Übersicht in ``telekom`` liest das iPhone
    Air nur mit 256 GB, die Produktseite in ``telekom-3`` alle drei Speicher. Der Satz
    nennt alle; Gegenprobe: eine Datei von gestern zählt nicht mit."""
    kopf = {"anbieter": "Telekom", "datum": "2026-10-11", "laufstatus": LAUF_GELESEN}
    bilanz = {
        "dateien": [
            {
                **kopf,
                "alter_tage": 0,
                "speicher_gelesen": {"apple-iphone-air": [256, 512, 1024]},
            },
            {**kopf, "alter_tage": 1, "speicher_gelesen": {"apple-iphone-air": [128]}},
            {**kopf, "alter_tage": 0, "speicher_gelesen": {"apple-iphone-air": [256]}},
        ]
    }

    gruende = erfassungsgruende(bilanz)

    assert gruende["Telekom|apple-iphone-air"] == SATZ_SPEICHER.format(
        anbieter="Telekom", speicher="256 GB, 512 GB und 1 TB", datum="11.10.2026"
    )


def _listung(anbieter, speicher, **anders):
    return {
        "anbieter": anbieter,
        "device_id": "apple-iphone-17-pro",
        "speicher_gb": speicher,
        "status": "aktiv",
        "zustand": "neu",
        "last_verified": "2026-10-11",
        **anders,
    }


def test_nicht_gelistete_speicher_heissen_nicht_im_angebot():
    """Preisprüfung 11.10.2026: o2 führt das iPhone 17 Pro in seiner ganzen
    Geräteliste nur mit 256 GB; 512 GB und 1 TB sind keine Erfassungslücke.
    Gegenprobe: listet o2 auch 512 GB, bleibt es „nur mit 256 GB gelesen“; ohne heute
    gelesene Liste ebenso; ausgelistete und gebrauchte Listungen zählen nicht."""
    eintrag = {
        "anbieter": "o2",
        "datum": "2026-10-11",
        "alter_tage": 0,
        "laufstatus": LAUF_GELESEN,
        "speicher_gelesen": {"apple-iphone-17-pro": [256]},
    }
    nur_256 = [
        _listung("o2", 256),
        _listung("o2", 512, status="ausgelistet"),
        _listung("o2", 1024, zustand="gebraucht"),
    ]
    mit_512 = [*nur_256, _listung("o2", 512)]
    schluessel = "o2|apple-iphone-17-pro"

    def satz(listungen, gelesen):
        angebot = angebotene_speicher(listungen, gelesen, "2026-10-11")
        return erfassungsgruende({"dateien": [eintrag]}, angebot)[schluessel]

    angebot = SATZ_SPEICHER_ANGEBOT.format(
        anbieter="o2", speicher="256 GB", datum="11.10.2026"
    )
    gelesen = SATZ_SPEICHER.format(anbieter="o2", speicher="256 GB", datum="11.10.2026")
    assert satz(nur_256, {"o2"}) == angebot
    assert satz(mit_512, {"o2"}) == gelesen
    assert satz(nur_256, set()) == gelesen


class _Liste:
    """Bestand mit zwei Anbietern; nur o2 hat seine Liste heute ganz gelesen."""

    def eintraege(self):
        return [_listung("o2", 256), _listung("congstar", 512)]

    def lesezustand(self, anbieter, tag):
        return {"o2": "gelesen", "congstar": "lesefehler"}[anbieter]


def test_angebot_nur_aus_heute_ganz_gelesenen_listen():
    angebot = angebot_aus(_Liste(), "2026-10-11")
    assert angebot == {"o2": {"apple-iphone-17-pro": {256}}}
