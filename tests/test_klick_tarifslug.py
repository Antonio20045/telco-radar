"""Klick-Sätze ohne alten Leser lösen ihren Tarif über die Seite auf (Pitch 3).

Die Sätze sind die echten Werte des Klick-Laufs vom 10.10.2026
(``data/state/klick/o2.json`` und ``congstar.json``, Commit 6a0ab4f5): o2 iPhone 16
128 GB mit vier Tarifen, congstar iPhone 16 128 GB mit XS und M. Der Bestand ist der
Schnappschuss vom 03.10.2026. Ohne Slug blieben o2 alle und congstar XS ohne Tarif.
"""

from __future__ import annotations

from urllib.parse import parse_qsl, urlsplit

import pytest
from bestand_pfad import ZUSTAND

from telco_radar.analyze.klick_tarifslug import (
    klick_beleglink,
    klick_slug,
    o2_slug,
    plan_nummer,
)
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
        ("o2", "O2 Mobile L Plus mit 150 GB+"): "o2:o2-mobile-l-plus",
        ("o2", "O2 Mobile Unlimited M Plus mit 100 MBit/s"): (
            "o2:o2-mobile-unlimited-m-plus"
        ),
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


def _query(adresse: str) -> dict[str, str]:
    return dict(parse_qsl(urlsplit(adresse).query))


def test_o2_beleglink_traegt_tarif_und_ratenzahl_der_zeile(saetze):
    """Preisprüfung 02.11.2026: die Seite blieb auf ``ratenzahlung=36`` und ihrem
    Konfigurationstarif, die Zeile war 24 Raten ``O2 Mobile L``."""
    satz = {**saetze[0], "tarif_name": "O2 Mobile L mit 150 GB+ (24 Mon.)"}
    satz["laufzeit_monate"] = 24

    link = klick_beleglink(satz)

    frage = _query(link)
    assert (frage["tarif"], frage["ratenzahlung"]) == ("o2-mobile-l", "24")
    assert urlsplit(link).path == urlsplit(O2_SEITE).path
    ohne = {k: v for k, v in frage.items() if k not in ("tarif", "ratenzahlung")}
    rest = {
        k: v for k, v in _query(O2_SEITE).items() if k not in ("tarif", "ratenzahlung")
    }
    assert ohne == rest


def test_beleglink_ohne_ratenzahl_behaelt_nicht_die_der_seite(saetze):
    satz = {**saetze[0], "laufzeit_monate": None}

    frage = _query(klick_beleglink(satz))

    assert "ratenzahlung" not in frage and frage["tarif"] == "o2-mobile-l-plus"


def test_beleglink_nur_fuer_o2_klick_saetze(saetze):
    o2, congstar = saetze[0], saetze[-1]
    assert klick_beleglink(congstar) == congstar["quelle_url"]
    assert klick_beleglink({**o2, "quelle_art": ""}) == O2_SEITE
    assert klick_beleglink({**o2, "quelle_url": ""}) == ""


def test_buendel_aus_o2_klick_satz_traegt_den_beleglink_der_zeile(bestand, saetze):
    satz = {**saetze[0], "laufzeit_monate": 24}

    bilanz = aus_rohsaetzen([satz], bestand, HEUTE)

    (buendel,) = bilanz.buendel
    assert _query(buendel.quelle_url)["ratenzahlung"] == "24"
    assert _query(buendel.quelle_url)["tarif"] == "o2-mobile-l-plus"
