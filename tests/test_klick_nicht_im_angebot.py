"""„Bei Telekom nicht im Angebot“ statt „kein Bündel erhoben“ (Pitch 4, Schnitt 4).

Die Klick-Ergebnisdatei ``telekom.json`` trägt ``uebersichten[]`` (``klickuebersicht``).
Ein Gerät bekommt den Satz „Bei Telekom nicht im Angebot (Übersicht vom 09.10.2026
ganz gelesen)“ nur, wenn am Tag der Datei alle Übersichten gelesen und vollständig
sind, kein Titel unbekannt blieb und das Gerät mit keinem Speicher in einer Übersicht
steht. Gegenproben: eine Übersicht unvollständig, gestört oder mit unbekanntem Titel,
oder das Gerät nur mit anderem Speicher in der Übersicht: kein Satz. Datum fest.
"""

from __future__ import annotations

import json

import pytest
from bestand_pfad import abbild, lese_wurzel

from telco_radar.analyze.klick_erfassung import fuer_modell
from telco_radar.analyze.klick_zusammenfuehrung import fuehre_zusammen
from telco_radar.collect.geraete.klicklauf import LAUF_GELESEN, LAUF_GESTOERT
from telco_radar.collect.geraete.klickrohsatz import ausbeute
from telco_radar.config import load_config
from telco_radar.geraete_config import lade_katalog
from telco_radar.report.html import render_site

TAG = "2026-10-09"
SATZ = "Bei Telekom nicht im Angebot (Übersicht vom 09.10.2026 ganz gelesen)"
NUR_256 = "Bei Telekom nur mit 256 GB gelesen (09.10.2026)"
X = "apple-iphone-17-pro"
Y = "apple-iphone-17"
TARIFE = ("MF_17791", "MF_17779", "MF_17785", "MF_17797", "MF_17803")
ADRESSE = "https://www.telekom.de/shop/geraete/smartphones?tariffId={}"


@pytest.fixture(scope="module")
def katalog():
    return lade_katalog(lese_wurzel())


def _satz(titel: str, gb: int) -> dict:
    return {
        "titel": titel,
        "speicher_gb": gb,
        "tarif_name": "MagentaMobil M",
        "tarif_slug": "MF_17791",
        "tarif_monatlich": 49.95,
        "geraet_zuzahlung": 1.0,
        "geraet_monatsrate": 40.0,
        "anschlusspreis": 39.95,
        "laufzeit_monate": 36,
        "url": "https://www.telekom.de/shop/geraet/apple/apple-iphone-17/x-256-gb",
    }


def _uebersicht(tarif: str, saetze: list[dict], **felder) -> dict:
    eintrag = {
        "adresse": ADRESSE.format(tarif),
        "status": LAUF_GELESEN,
        "grund": None,
        "saetze": saetze,
        "seiten": [],
        "vollstaendig": True,
        "unvollstaendig": None,
    }
    return {**eintrag, **felder}


def _datei(*, dritte: dict | None = None, extra: list[dict] = ()) -> dict:
    """Fünf vollständige Übersichten; iPhone 17 (Y) steht in jeder, X in keiner."""
    uebersichten = [
        _uebersicht(t, [_satz("Apple iPhone 17 256 GB", 256), *extra]) for t in TARIFE
    ]
    if dritte is not None:
        uebersichten[2] = {**uebersichten[2], **dritte}
    return {
        "anbieter": "telekom",
        "name": "Telekom",
        "datum": TAG,
        "format": 1,
        "laufstatus": LAUF_GELESEN,
        "grund": None,
        "seiten": [],
        "uebersichten": uebersichten,
    }


def _erfassung(datei: dict, katalog) -> dict[str, str]:
    zug = fuehre_zusammen([], [datei], katalog, TAG, lambda sku: ("", None))
    return zug.erfassung


def test_ausbeute_meldet_angebotene_geraete_und_vollstaendigkeit(katalog):
    daten = ausbeute(_datei(), katalog).als_daten()
    assert daten["angeboten"] == [Y]
    assert X in daten["nicht_im_angebot"]
    assert Y not in daten["nicht_im_angebot"]


def test_satz_bei_x_mit_datum_bei_y_nur_der_speicher(katalog):
    gruende = _erfassung(_datei(), katalog)
    assert fuer_modell(gruende, {"karten": [], "device_id": X}) == {"Telekom": SATZ}
    assert fuer_modell(gruende, {"karten": [], "device_id": Y}) == {"Telekom": NUR_256}


def test_karte_mit_betrag_verdraengt_den_satz(katalog):
    gruende = _erfassung(_datei(), katalog)
    karte = {"anbieter": "Telekom", "gesamt": 1234.0}
    assert fuer_modell(gruende, {"karten": [karte], "device_id": X}) == {}


@pytest.mark.parametrize(
    "dritte",
    [
        {"vollstaendig": False, "unvollstaendig": "Obergrenze von 6 Seiten erreicht"},
        {"status": LAUF_GESTOERT, "grund": "Übersicht ohne Gerät", "saetze": []},
        {"status": "nicht_besucht", "grund": "nicht besucht", "saetze": []},
    ],
    ids=["unvollstaendig", "gestoert", "nicht-besucht"],
)
def test_gegenprobe_eine_uebersicht_nicht_ganz_kein_satz(katalog, dritte):
    gruende = _erfassung(_datei(dritte=dritte), katalog)
    assert fuer_modell(gruende, {"karten": [], "device_id": X}) == {}


def test_gegenprobe_unbekannter_titel_kein_satz(katalog):
    datei = _datei(extra=[_satz("Beispielfon Z9 256 GB", 256)])
    gruende = _erfassung(datei, katalog)
    assert fuer_modell(gruende, {"karten": [], "device_id": X}) == {}


def test_gegenprobe_anderer_speicher_zaehlt_als_angeboten(katalog):
    datei = _datei(extra=[_satz("Apple iPhone 17 Pro 2 TB", 2048)])
    gruende = _erfassung(datei, katalog)
    assert fuer_modell(gruende, {"karten": [], "device_id": X}) == {}


def test_gegenprobe_veraltete_datei_kein_satz(katalog):
    zug = fuehre_zusammen([], [_datei()], katalog, "2026-10-10", lambda s: ("", None))
    assert fuer_modell(zug.erfassung, {"karten": [], "device_id": X}) == {}


def test_gerenderte_seite_zeigt_den_satz_in_der_telekom_zeile(tmp_path, katalog):
    berichte = abbild(tmp_path)
    pfad = tmp_path / "data" / "state" / "geraete_tco.json"
    daten = json.loads(pfad.read_text(encoding="utf-8"))
    daten["erfassung"] = _erfassung(_datei(), katalog)
    pfad.write_text(json.dumps(daten, ensure_ascii=False), encoding="utf-8")
    render_site(tmp_path / "site", berichte, load_config(tmp_path))
    seite = (tmp_path / "site" / "geraete.html").read_text(encoding="utf-8")
    assert f'<span class="wr-grund">{SATZ}</span>' in seite


def test_unbekannter_erneuerter_titel_haelt_den_satz_nicht_auf(katalog):
    """Telekom 10.10.2026: „Apple iPhone 13 (Erneuert Basic) 128 GB“ fehlt im Katalog,
    der nur Neuware führt; der Satz bleibt."""
    datei = _datei(extra=[_satz("Apple iPhone 13 (Erneuert Basic) 128 GB", 128)])
    gruende = _erfassung(datei, katalog)
    assert fuer_modell(gruende, {"karten": [], "device_id": X}) == {"Telekom": SATZ}
