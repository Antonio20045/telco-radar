"""Klick-Sätze ohne alten Leser lösen ihren Tarif über die Seite auf (Pitch 3).

Die Sätze sind die echten Werte des Klick-Laufs vom 10.10.2026
(``data/state/klick/o2.json`` und ``congstar.json``, Commit 6a0ab4f5): o2 iPhone 16
128 GB mit vier Tarifen, congstar iPhone 16 128 GB mit XS und M. Der Bestand ist der
Schnappschuss vom 03.10.2026. Ohne Slug blieben o2 alle und congstar XS ohne Tarif.
"""

from __future__ import annotations

import pytest
from bestand_pfad import ZUSTAND

from telco_radar.analyze.klick_tarifslug import klick_slug, o2_slug, plan_nummer
from telco_radar.analyze.tco_buendel import aus_rohsaetzen
from telco_radar.collect.geraete.congstar import ergaenze_pib_slug
from telco_radar.tarif_bezug import Tarifbestand

HEUTE = "2026-10-10"
O2_SEITE = (
    "https://www.o2online.de/e-shop/apple/apple-iphone-16-128gb-schwarz-details"
    "?ohne-tarif=nein&zielgruppe=privatkunden&ratenzahlung=36&vertragsart=ratenzahlung"
    "&tarif=o2-mobile-on-demand-m-plus"
)
CONGSTAR_SEITE = "https://www.congstar.de/geraete/apple/apple-iphone-16/?paymentVariantBenefits=&planId={}"

O2_ANGEBOTE = {
    "O2 Mobile L Plus mit 150 GB+": "o2-mobile-l-plus",
    "O2 Mobile L mit 150 GB+": "o2-mobile-l",
    "O2 Mobile Unlimited L Plus mit 300 MBit/s": "o2-mobile-unlimited-l-plus",
    "O2 Mobile Unlimited L mit 300 MBit/s": "o2-mobile-unlimited-l",
    "O2 Mobile Unlimited M Plus mit 100 MBit/s": "o2-mobile-unlimited-m-plus",
    "O2 Mobile Unlimited M mit 100 MBit/s": "o2-mobile-unlimited-m",
    "O2 Mobile on Demand M Plus mit 50 GB+": "o2-mobile-on-demand-m-plus",
    "O2 Mobile on Demand M mit 50 GB+": "o2-mobile-on-demand-m",
}
"""Name auf der Seite → Kern des Angebots in der Antwortadresse (10.10.2026)."""


def _satz(anbieter: str, tarif: str, url: str, rate: float, monatlich: float) -> dict:
    return {
        "sku_id": "apple-iphone-16-128gb-ohne-farbe",
        "anbieter": anbieter,
        "zustand": "neu",
        "device_id": "apple-iphone-16",
        "speicher_gb": 128,
        "tarif_name": tarif,
        "tarif_slug": "",
        "laufzeit_monate": 36,
        "tarif_bindung_monate": 24,
        "quelle_url": url,
        "quelle": "klick",
        "quelle_art": "klick",
        "abgerufen_am": HEUTE,
        "geraet_zuzahlung": 1.0,
        "geraet_monatsrate": rate,
        "tarif_monatlich": monatlich,
        "buendel_monatlich": None,
        "tarif_phasen": [],
    }


@pytest.fixture(scope="module")
def bestand():
    tarife = Tarifbestand.aus_datei(ZUSTAND / "tarife.jsonl")
    ergaenze_pib_slug(tarife)
    return tarife


@pytest.fixture
def saetze():
    o2 = [
        _satz("o2", tarif, O2_SEITE, 20.0, 30.0)
        for tarif in (
            "O2 Mobile L Plus mit 150 GB+",
            "O2 Mobile Unlimited M Plus mit 100 MBit/s",
            "O2 Mobile on Demand M mit 50 GB+",
            "O2 Mobile Unlimited L mit 300 MBit/s",
        )
    ]
    congstar = [
        _satz("congstar", "Allnet Flat XS", CONGSTAR_SEITE.format(543), 21.0, 15.0),
        _satz("congstar", "Allnet Flat M", CONGSTAR_SEITE.format(540), 21.0, 30.0),
    ]
    return o2 + congstar


@pytest.mark.parametrize(("name", "angebot"), sorted(O2_ANGEBOTE.items()))
def test_o2_slug_ist_das_angebot_der_seite(name, angebot):
    assert o2_slug(name) == angebot


def test_congstar_slug_ist_die_plan_nummer():
    assert plan_nummer(CONGSTAR_SEITE.format(543)) == "543"
    assert plan_nummer("https://www.congstar.de/geraete/apple/apple-iphone-16/") == ""
    assert plan_nummer(CONGSTAR_SEITE.format("abc")) == ""


def test_nur_klick_saetze_ohne_slug_bekommen_einen(saetze):
    o2 = saetze[0]
    assert klick_slug(o2) == "o2-mobile-l-plus"
    assert klick_slug({**o2, "quelle_art": ""}) == ""
    assert klick_slug({**o2, "anbieter": "Vodafone"}) == ""


def test_klick_saetze_ohne_alten_leser_werden_buendel(bestand, saetze):
    bilanz = aus_rohsaetzen(saetze, bestand, HEUTE)

    assert bilanz.ohne_tarif == 0
    tarif = {(b.anbieter, b.tarif_name): b.tarif_id for b in bilanz.buendel}
    assert tarif == {
        ("o2", "O2 Mobile L Plus mit 150 GB+"): "o2:o2-mobile-l",
        ("o2", "O2 Mobile Unlimited M Plus mit 100 MBit/s"): "o2:o2-mobile-unlimited-m",
        ("o2", "O2 Mobile on Demand M mit 50 GB+"): "o2:o2-mobile-on-demand-m",
        ("o2", "O2 Mobile Unlimited L mit 300 MBit/s"): "o2:o2-mobile-unlimited-l",
        ("congstar", "Allnet Flat XS"): "congstar:allnet-flat-xs-mit-gb",
        ("congstar", "Allnet Flat M"): "congstar:allnet-flat-m",
    }


def test_gegenprobe_ohne_klick_kennung_bleibt_ohne_tarif(bestand, saetze):
    fremd = [{**s, "quelle_art": ""} for s in saetze]

    bilanz = aus_rohsaetzen(fremd, bestand, HEUTE)

    assert bilanz.ohne_tarif == 5
    assert [b.tarif_name for b in bilanz.buendel] == ["Allnet Flat M"]
