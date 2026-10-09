"""1&1-Geräteraster je Tarif im Klick-Crawler: Lesart, Einstiege und Tarifname.

Fixtures ``einsundeins_tarifraster_*_2026-09-29.html.gz`` sind die sieben Raster vom
29.09.2026, gekürzt auf den Ausschnitt mit allen 43 Kacheln (Herkunft im Kopf von
``test_geraete_tarifstufen_einsundeins.py``). Die Adressen stehen als ``targetpage``
auf den Tarifübersichten vom selben Tag.
"""

from __future__ import annotations

import gzip

import pytest
from bestand_pfad import lese_wurzel
from klickergebnisse import FIX
from test_klick_anschluss_1und1 import DETAILS, DETAILS_S

from telco_radar.collect.geraete.basis import GeraeteAbrufFehler
from telco_radar.collect.geraete.einsundeins import tarifraster_adressen
from telco_radar.collect.geraete.klickuebersicht import LESARTEN
from telco_radar.collect.geraete.klickziele import TAGESDATEI, lade_ziele
from telco_radar.geraete_config import lade_quellen

RASTER = (
    "https://mobile.1und1.de/smartphones-all-net-flat-s",
    "https://mobile.1und1.de/smartphones-all-net-flat-m",
    "https://mobile.1und1.de/smartphones-all-net-flat-l",
    "https://mobile.1und1.de/smartphones-unlimited-s",
    "https://mobile.1und1.de/smartphones-unlimited-m",
    "https://mobile.1und1.de/smartphones-unlimited-l",
    "https://mobile.1und1.de/smartphones-unlimited-xl",
)
DATEIEN = {
    adresse: "einsundeins_tarifraster_"
    + adresse.rsplit("/smartphones-", 1)[1].replace("-", "_")
    + "_2026-09-29.html.gz"
    for adresse in RASTER
}
UEBERSICHTEN = (
    "einsundeins_tarifuebersicht_all_net_flat_2026-09-29.html.gz",
    "einsundeins_tarifuebersicht_unlimited_2026-09-29.html.gz",
)


def text(name: str) -> str:
    return gzip.decompress((FIX / name).read_bytes()).decode("utf-8")


def raster(adresse: str) -> list[dict]:
    return LESARTEN["1&1"].saetze(text(DATEIEN[adresse]), adresse)


@pytest.fixture(scope="module")
def unlimited_m() -> list[dict]:
    return raster(RASTER[4])


def test_die_sieben_raster_stehen_auf_den_tarifuebersichten():
    gefunden = {
        adresse
        for name in UEBERSICHTEN
        for adresse in tarifraster_adressen(text(name), "https://mobile.1und1.de")
    }

    assert gefunden == set(RASTER)


def test_raster_liest_jede_kachel(unlimited_m):
    assert len(unlimited_m) == 43
    assert {s["art"] for s in unlimited_m} == {"raster"}
    assert {s["tarif_name"] for s in unlimited_m} == {"1&1 Unlimited on demand M"}
    assert {s["laufzeit_monate"] for s in unlimited_m} == {36}
    assert len({s["url"] for s in unlimited_m}) == 43


def test_raster_iphone_17_pro_in_unlimited_m(unlimited_m):
    (satz,) = [s for s in unlimited_m if s["titel"] == "iPhone 17 Pro"]

    assert satz == {
        "art": "raster",
        "titel": "iPhone 17 Pro",
        "url": "https://mobile.1und1.de/iphone-17-pro?tariffFirst=true",
        "tarif_name": "1&1 Unlimited on demand M",
        "laufzeit_monate": 36,
        "buendel_monatlich": 54.99,
        "zubehoer": None,
    }


def test_kachel_mit_zubehoer_nennt_es():
    saetze = raster(RASTER[0])

    zubehoer = {s["titel"]: s["zubehoer"] for s in saetze}
    assert zubehoer["Samsung Galaxy A57 5G"] == "Samsung Galaxy Buds 4"
    assert zubehoer["Google Pixel 10a"] == "Google Pixel Buds 2a"
    assert zubehoer["iPhone 17 Pro"] is None


@pytest.mark.parametrize(
    ("adresse", "preis"),
    list(zip(RASTER, (44.99, 49.99, 54.99, 49.99, 54.99, 59.99, 69.99), strict=True)),
)
def test_iphone_17_pro_in_jedem_raster(adresse, preis):
    (satz,) = [s for s in raster(adresse) if s["titel"] == "iPhone 17 Pro"]

    assert satz["buendel_monatlich"] == preis


def test_raster_ohne_kachel_ist_gestoert():
    leer = text(DATEIEN[RASTER[0]]).split('<form class="hardware-box', 1)[0]

    with pytest.raises(GeraeteAbrufFehler):
        LESARTEN["1&1"].saetze(leer, RASTER[0])


def test_raster_mit_verschiedenen_tarifen_ist_gestoert():
    gemischt = text(DATEIEN[RASTER[0]]) + text(DATEIEN[RASTER[1]])

    with pytest.raises(GeraeteAbrufFehler):
        LESARTEN["1&1"].saetze(gemischt, RASTER[0])


def test_kachel_ohne_preis_ist_gestoert():
    ohne = text(DATEIEN[RASTER[0]]).replace('class="price__euro"', 'class="x"', 1)

    with pytest.raises(GeraeteAbrufFehler):
        LESARTEN["1&1"].saetze(ohne, RASTER[0])


def test_adresse_ohne_seitenart_ist_gestoert():
    with pytest.raises(GeraeteAbrufFehler):
        LESARTEN["1&1"].saetze(text(DATEIEN[RASTER[0]]), "https://mobile.1und1.de/x")


def test_detailseite_nennt_tarifnamen():
    details = text("einsundeins_tarifdetails_anf_s.html.gz")

    (satz,) = LESARTEN["1&1"].saetze(details, DETAILS_S)

    assert satz["tarif_name"] == "1&1 All-Net-Flat S"
    assert satz["tarif_slug"] == "tariff-anf-s-mvl"
    assert satz["anschlusspreis"] == 39.9


def test_detailseite_ohne_namen_bleibt_anschluss_ohne_namen():
    details = text("einsundeins_tarifdetails_anf_s.html.gz")
    ohne = details.replace("tariff-detail__heading", "x")

    (satz,) = LESARTEN["1&1"].saetze(ohne, DETAILS_S)

    assert satz["tarif_name"] is None and satz["anschlusspreis"] == 39.9


def test_bereit_wartet_beim_raster_auf_kacheln():
    bereit = LESARTEN["1&1"].bereit

    assert bereit is not None
    assert "form.hardware-box" in bereit and "/smartphones-" in bereit
    assert "complete" in bereit


def test_tagesdatei_und_quellen_nennen_details_dann_raster():
    wurzel = lese_wurzel()
    ziele = lade_ziele(wurzel, TAGESDATEI, hoechste=None)
    (einsundeins,) = [z for z in ziele if z.schluessel == "1und1"]
    anbieter = lade_quellen(wurzel).nach_name("1&1")
    klick = [e.url for e in anbieter.klick_einstiege if e.kind == "klick"]

    assert einsundeins.uebersichten == DETAILS + RASTER
    assert tuple(klick) == DETAILS + RASTER
    assert [e.kind for e in anbieter.einstiege] == ["static"]
