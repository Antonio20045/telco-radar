"""1&1-Anschlusspreis im Klick-Crawler: Tarifdetail-Seiten als Übersichten.

Fixture ``einsundeins_tarifdetails_anf_s.html.gz`` ist die Tarifdetail-Seite zu
All-Net-Flat S; die sieben Adressen stehen wörtlich als ``data-iframe`` auf den
Tarifübersichten vom 29.09.2026.
"""

from __future__ import annotations

import gzip
from dataclasses import replace
from datetime import UTC, datetime

import pytest
from bestand_pfad import lese_wurzel
from klickergebnisse import (
    FIX,
)

from telco_radar.collect.geraete import sammle_anbieter
from telco_radar.collect.geraete.basis import GeraeteAbrufFehler
from telco_radar.collect.geraete.klickuebersicht import LESARTEN
from telco_radar.collect.geraete.klickziele import TAGESDATEI, lade_ziele
from telco_radar.collect.geraete.robots import RobotsWaechter
from telco_radar.geraete_config import lade_farben, lade_katalog, lade_quellen

HEUTE = "2026-09-29"
DETAILS = (
    "https://mobile.1und1.de/details-all-net-flat-preisliste"
    "?chosenTariff=tariff-anf-s-mvl"
    "&chosenNet=1u1&lightbox=true&bk=false",
    "https://mobile.1und1.de/details-all-net-flat-preisliste"
    "?chosenTariff=tariff-anf-m-mvl"
    "&chosenNet=1u1&lightbox=true&bk=false",
    "https://mobile.1und1.de/details-all-net-flat-preisliste"
    "?chosenTariff=tariff-anf-l-mvl"
    "&chosenNet=1u1&lightbox=true&bk=false",
    "https://mobile.1und1.de/details-all-net-flat-preisliste"
    "?chosenTariff=tariff-anf-xxl-unlimited-s-mvl"
    "&chosenNet=1u1&lightbox=true&bk=false",
    "https://mobile.1und1.de/details-all-net-flat-preisliste"
    "?chosenTariff=tariff-anf-xxl-unlimited-m-mvl"
    "&chosenNet=1u1&lightbox=true&bk=false",
    "https://mobile.1und1.de/details-all-net-flat-preisliste"
    "?chosenTariff=tariff-anf-xxl-unlimited-l-mvl"
    "&chosenNet=1u1&lightbox=true&bk=false",
    "https://mobile.1und1.de/details-all-net-flat-preisliste"
    "?chosenTariff=tariff-anf-xxl-unlimited-xl-ovl"
    "&chosenNet=1u1&lightbox=true&bk=false",
)
DETAILS_S, DETAILS_M = DETAILS[0], DETAILS[1]
UEBERSICHTEN = (
    "einsundeins_tarifuebersicht_all_net_flat_2026-09-29.html.gz",
    "einsundeins_tarifuebersicht_unlimited_2026-09-29.html.gz",
)


def _text(name: str) -> str:
    return gzip.decompress((FIX / name).read_bytes()).decode("utf-8")


@pytest.fixture(scope="module")
def katalog():
    return lade_katalog(lese_wurzel())


@pytest.fixture(scope="module")
def details() -> str:
    return _text("einsundeins_tarifdetails_anf_s.html.gz")


def test_die_sieben_adressen_stehen_auf_den_tarifuebersichten():
    seiten = "".join(_text(name) for name in UEBERSICHTEN)
    for adresse in DETAILS:
        assert f'data-iframe="{adresse}"' in seiten
    assert "unlimited-xs-ovl" in seiten
    assert "smartphones-unlimited-xs" not in seiten


def test_lesart_liest_anschluss_und_slug(details):
    lesart = LESARTEN["1&1"]

    assert lesart.saetze(details, DETAILS_S) == [
        {
            "art": "anschluss",
            "tarif_slug": "tariff-anf-s-mvl",
            "tarif_name": "1&1 All-Net-Flat S",
            "anschlusspreis": 39.9,
        }
    ]
    assert lesart.folgelink(details) is None


def test_seite_ohne_betrag_ist_gestoert(details):
    ohne = details.replace("Tarif mit Smartphone", "Tarif")

    with pytest.raises(GeraeteAbrufFehler):
        LESARTEN["1&1"].saetze(ohne, DETAILS_S)


def test_adresse_ohne_tarif_ist_gestoert(details):
    with pytest.raises(GeraeteAbrufFehler):
        LESARTEN["1&1"].saetze(details, "https://mobile.1und1.de/iphone-17-pro")


def test_tagesdatei_1und1_hat_sieben_uebersichten():
    wurzel = lese_wurzel()
    ziele = lade_ziele(wurzel, TAGESDATEI, hoechste=None)
    (einsundeins,) = [z for z in ziele if z.schluessel == "1und1"]
    anbieter = lade_quellen(wurzel).nach_name("1&1")
    klick = [e.url for e in anbieter.klick_einstiege if e.kind == "klick"]

    assert einsundeins.uebersichten[:7] == DETAILS
    assert tuple(klick[:7]) == DETAILS


def test_alter_geraetelauf_ruft_kind_klick_nicht_ab():
    wurzel = lese_wurzel()
    quelle = lade_quellen(wurzel).nach_name("1&1")
    anbieter = replace(quelle, rate_limit_sekunden=0)
    geholt: list[str] = []

    def hole(url, **_):
        geholt.append(url)
        return (200, "") if url.endswith("/robots.txt") else (404, "")

    assert [e.url for e in anbieter.klick_einstiege][:7] == list(DETAILS)
    assert [e.kind for e in anbieter.einstiege] == ["static"]
    bilanz = sammle_anbieter(
        anbieter,
        lade_katalog(wurzel),
        lade_farben(wurzel),
        hole,
        HEUTE,
        RobotsWaechter(hole=hole),
        datetime(2026, 9, 29, 3, tzinfo=UTC),
    )

    assert "https://mobile.1und1.de/smartphones" in geholt
    assert not any("details-all-net-flat-preisliste" in url for url in geholt)
    assert bilanz.seiten_versucht == 1
