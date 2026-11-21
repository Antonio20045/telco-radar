"""1&1-Produktseiten aus der Geräteübersicht (20.11.2026), ohne Netz.

Bis zum 20.11.2026 standen die 1&1-Seiten des Klick-Laufs von Hand in
``config/klick_tageslauf.yaml``; Xiaomi 18 Pro und 18 Pro Max las nur der Adapter, der
seit #176 keine Bündel mehr liest. Jetzt liest der Eintrag ``1und1`` die
Geräteübersicht ``https://mobile.1und1.de/smartphones`` (Fixture
``tests/fixtures/klickcrawler/einsundeins_smartphones_20261120.html``: die 41 Kacheln
dieses Tages, je Kachel nur Titel und Produktlink), und beide 1&1-Einträge bekommen
ihre Seiten aus deren Kacheln (``klickliste_kacheln``).
"""

from __future__ import annotations

import copy
from pathlib import Path

import pytest
from bestand_pfad import lese_wurzel

from telco_radar.collect.geraete.basis import GeraeteAbrufFehler
from telco_radar.collect.geraete.klickliste_kacheln import (
    fuehre_vorrat,
    seiten_aus_kacheln,
)
from telco_radar.collect.geraete.klickraster import (
    ART_LISTE,
    BEREIT_JS,
    einsundeins_saetze,
)
from telco_radar.collect.geraete.klickrohsatz import ausbeute
from telco_radar.collect.geraete.klickziele import TAGESDATEI, lade_ziele
from telco_radar.geraete_config import lade_katalog
from telco_radar.geraete_model import Geraet, Katalog

WURZEL = Path(__file__).resolve().parents[1]
FIXTURE = WURZEL / "tests/fixtures/klickcrawler/einsundeins_smartphones_20261120.html"
UEBERSICHT = "https://mobile.1und1.de/smartphones"
XIAOMI = {
    "xiaomi-18-pro": ("Xiaomi", "18 Pro", [256, 512]),
    "xiaomi-18-pro-max": ("Xiaomi", "18 Pro Max", [256, 512]),
}


@pytest.fixture(scope="module")
def saetze() -> list[dict]:
    return einsundeins_saetze(FIXTURE.read_text(encoding="utf-8"), UEBERSICHT)


@pytest.fixture(scope="module")
def katalog() -> Katalog:
    """Der Katalog des Schnappschusses und die zwei Xiaomi-Modelle, die seit November
    darin stehen (Auto-Katalog)."""
    alt = lade_katalog(lese_wurzel())
    neu = [Geraet(hersteller=h, modell=m, speicher=s) for h, m, s in XIAOMI.values()]
    return Katalog(geraete=[*alt.geraete, *neu])


def _daten(uebersicht: dict, datum: str = "2026-11-21") -> dict:
    return {
        "anbieter": "1und1",
        "name": "1&1",
        "datum": datum,
        "vertragsform": "ein_vertrag",
        "seiten": [],
        "uebersichten": [uebersicht],
    }


def _gelesen(saetze: list[dict]) -> dict:
    return {
        "adresse": UEBERSICHT,
        "status": "gelesen",
        "vollstaendig": True,
        "saetze": copy.deepcopy(saetze),
    }


def test_uebersicht_liefert_je_kachel_titel_und_produktlink(saetze):
    assert len(saetze) == 41
    assert {s["art"] for s in saetze} == {ART_LISTE}
    xiaomi = [s for s in saetze if s["titel"] == "Xiaomi 18 Pro Max"]
    assert xiaomi == [
        {
            "art": ART_LISTE,
            "titel": "Xiaomi 18 Pro Max",
            "url": "https://mobile.1und1.de/xiaomi-18-pro-max",
        }
    ]
    assert len({s["url"] for s in saetze}) == 41


def test_gegenprobe_uebersicht_ohne_kachel_ist_gestoert():
    with pytest.raises(GeraeteAbrufFehler, match="ohne hardware-box"):
        einsundeins_saetze("<html><body>Wartung</body></html>", UEBERSICHT)


def test_gegenprobe_kachel_ohne_link_ist_gestoert():
    roh = FIXTURE.read_text(encoding="utf-8").replace(
        '<a href="https://mobile.1und1.de/iphone-17"', '<a data-x="weg"', 1
    )
    with pytest.raises(GeraeteAbrufFehler, match="ohne Titel/Link"):
        einsundeins_saetze(roh, UEBERSICHT)


def test_bereit_auch_fuer_die_uebersicht():
    assert "location.pathname.startsWith('/smartphones')" in BEREIT_JS


def test_je_geraet_eine_seite_mit_dem_produktlink_der_kachel(saetze, katalog):
    ergebnis = seiten_aus_kacheln(_daten(_gelesen(saetze)), katalog)
    je_geraet = {s["geraet"]: s for s in ergebnis.seiten}

    assert ergebnis.luecken == []
    assert len(ergebnis.seiten) == len(je_geraet) == 41
    assert je_geraet["xiaomi-18-pro"]["url"] == "https://mobile.1und1.de/xiaomi-18-pro"
    assert je_geraet["xiaomi-18-pro-max"]["modell"] == "18 Pro Max"
    assert je_geraet["samsung-galaxy-s26-ultra"]["url"] == (
        "https://mobile.1und1.de/samsung-galaxy-s26-ultra"
    )
    assert {s["speicher_gb"] for s in ergebnis.seiten} == {None}


def test_gegenprobe_unbekanntes_geraet_bekommt_keine_seite(saetze):
    ohne_xiaomi = lade_katalog(lese_wurzel())
    seiten = seiten_aus_kacheln(_daten(_gelesen(saetze)), ohne_xiaomi).seiten

    assert len(seiten) == 39
    assert not [s for s in seiten if s["geraet"].startswith("xiaomi-18")]


def test_gegenprobe_fremder_link_wird_keine_seite(katalog):
    fremd = [
        {"art": ART_LISTE, "titel": "iPhone 17", "url": "https://www.1und1.de/x"},
        {"art": ART_LISTE, "titel": "iPhone 17", "url": f"{UEBERSICHT}?filter=apple"},
    ]
    assert seiten_aus_kacheln(_daten(_gelesen(fremd)), katalog).seiten == []


def test_teilausfall_nimmt_den_vorrat_und_nennt_die_luecke(saetze, katalog):
    alt = _daten(_gelesen(saetze), "2026-11-21")
    gestoert = {"adresse": UEBERSICHT, "status": "gestoert", "grund": "Bot-Schutz"}
    neu = fuehre_vorrat(_daten(gestoert, "2026-11-22"), alt)

    ergebnis = seiten_aus_kacheln(neu, katalog)

    assert len(ergebnis.seiten) == 41
    (luecke,) = ergebnis.luecken
    assert "nicht ganz gelesen (Bot-Schutz)" in luecke
    assert "Kacheln vom 21.11.2026" in luecke


def test_gegenprobe_vorrat_zu_alt_dann_seiten_des_laufs(saetze, katalog):
    alt = _daten(_gelesen(saetze), "2026-11-01")
    gestoert = {"adresse": UEBERSICHT, "status": "gestoert", "grund": "Bot-Schutz"}
    neu = fuehre_vorrat(_daten(gestoert, "2026-11-22"), alt)
    neu["seiten"] = [
        {"adresse": "https://mobile.1und1.de/iphone-17", "geraet": "apple-iphone-17"},
        {"adresse": "https://mobile.1und1.de/kaputt?x=1", "geraet": "apple-iphone-17"},
    ]

    ergebnis = seiten_aus_kacheln(neu, katalog)

    assert [s["url"] for s in ergebnis.seiten] == ["https://mobile.1und1.de/iphone-17"]
    assert "keine Kacheln jünger als 7 Tage" in ergebnis.luecken[0]
    assert ergebnis.luecken[1] == "keine Kachel, 1 Seiten des Laufs vom 22.11.2026"


def test_listensaetze_werden_keine_rohsaetze_aber_angeboten(saetze, katalog):
    ergebnis = ausbeute(_daten(_gelesen(saetze)), katalog)

    assert ergebnis.rohsaetze == []
    assert "xiaomi-18-pro" in ergebnis.angeboten
    assert len(ergebnis.angeboten) == 41


def test_tagesdatei_zwei_1und1_eintraege_aus_der_uebersicht():
    ziele = [
        z
        for z in lade_ziele(lese_wurzel(), TAGESDATEI, hoechste=None)
        if z.name == "1&1"
    ]

    assert [z.schluessel for z in ziele] == ["1und1", "1und1-2"]
    assert {z.seitenquelle for z in ziele} == {"1und1"}
    assert ziele[0].uebersichten[-1] == UEBERSICHT
    assert ziele[1].uebersichten == ziele[0].uebersichten[:-1]
    assert UEBERSICHT not in ziele[1].uebersichten
