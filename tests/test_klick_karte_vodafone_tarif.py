"""Klick-Karte Vodafone auf der Tarifauswahl gegen die echte Antwort (Schnitt 8b, 2b).

Fixture ``vodafone_tarifauswahl_20261010.json.gz``: die Antwort
glados/v2/tariff/v2/hardware der Klick-Erkundung vom 10.10.2026 (iPhone 17 Pro 256 GB,
36 Raten; Herkunft in ``_herkunft.json``). Die Zusammenfassungen je Tarif sind aus
derselben Erkundung kopiert (klicks-3.json, „preise_geaendert“ der fünf Tarifklicks,
Zeile 2 der Preistabelle). Erwartet je Tarif: Anzahlung 1 €, Rate 33 €, Tarif Monat
1–24, Summe gleich dem Angebotspreis der Seite, Tarifname als Nachweis; das Echo über
die Summe bestätigt Rate und Tarif. Gegenprobe: die Summe eines anderen Tarifs ist ein
Befund.
"""

from __future__ import annotations

import gzip
import json
from pathlib import Path

import pytest

from telco_radar.collect.geraete.klickecho import Variante, lies_antwort, pruefe_echo
from telco_radar.collect.geraete.klickkarte import lade_klickkarte
from telco_radar.collect.geraete.klicktext import Buendelwerte, Preiswerte
from telco_radar.tarif_model import Preisphase

WURZEL = Path(__file__).resolve().parents[1]
FIXTURE = (
    WURZEL / "tests" / "fixtures" / "geraete" / "vodafone_tarifauswahl_20261010.json.gz"
)
ADRESSE = (
    "https://api.vodafone.de/glados/v2/tariff/v2/hardware?businessTransaction="
    "newContract&salesChannel=Online.Consumer&hardwareId=57562&virtualItemId=267"
    "&virtualItemId=268&virtualItemId=269&virtualItemId=270&virtualItemId=271"
    "&financingType=rate&financingDuration=36"
)
TARIFE = [
    ("267", "Mobil XS", 23.95, "Standardpreis 64,95 € – Angebotspreis 56,95 €"),
    ("268", "Mobil S", 31.45, "Standardpreis 74,95 € – Angebotspreis 64,45 €"),
    ("269", "Mobil M", 29.61, "Standardpreis 84,95 € – Angebotspreis 62,61 €"),
    ("270", "Mobil L", 36.61, "Standardpreis 94,95 € – Angebotspreis 69,61 €"),
    ("271", "Mobil XL", 50.11, "Standardpreis 114,95 € – Angebotspreis 83,11 €"),
]


@pytest.fixture(scope="module")
def karte():
    return lade_klickkarte(WURZEL / "config" / "klickkarten" / "vodafone.yaml")


@pytest.fixture(scope="module")
def nutzlast():
    with gzip.open(FIXTURE, "rt", encoding="utf-8") as fh:
        return json.load(fh)


def _lesung(karte, nutzlast, tarif: str):
    platz = {"speicher": "256 GB", "laufzeit": "36", "tarif": tarif}
    return lies_antwort(nutzlast, karte.antwort, ADRESSE, platz)


def _summe(karte, text: str) -> float:
    treffer = karte.textlesung.muster["buendelbetrag"].muster.search(text)
    return float(treffer[1].replace(",", "."))


@pytest.mark.parametrize(("tarif", "name", "betrag", "text"), TARIFE)
def test_jeder_tarif_aus_der_antwort_bestaetigt_ueber_die_summe(
    karte, nutzlast, tarif, name, betrag, text
):
    lesung = _lesung(karte, nutzlast, tarif)
    variante = Variante("256 GB", tarif, 36)
    echo = pruefe_echo(
        variante,
        variante,
        Preiswerte(anzahlung=1.0),
        lesung,
        buendel=Buendelwerte(buendelbetrag=_summe(karte, text)),
        summe=karte.summe,
    )

    assert lesung.nachweise["tarifname"] == name
    assert lesung.variante["speicher"] == "256 GB"
    assert lesung.buendel.buendelbetrag == _summe(karte, text)
    assert echo.befunde == ()
    assert echo.werte.anzahlung == 1.0
    assert echo.werte.rate == 33.0
    assert echo.werte.tarifphasen == (Preisphase(1, 24, betrag),)
    assert round(33.0 + betrag, 2) == _summe(karte, text)


def test_gegenprobe_summe_eines_anderen_tarifs_ist_ein_befund(karte, nutzlast):
    lesung = _lesung(karte, nutzlast, "269")
    variante = Variante("256 GB", "269", 36)
    echo = pruefe_echo(
        variante,
        variante,
        Preiswerte(anzahlung=1.0),
        lesung,
        buendel=Buendelwerte(buendelbetrag=_summe(karte, TARIFE[0][3])),
        summe=karte.summe,
    )

    assert {b.feld for b in echo.befunde} == {"buendelbetrag", "rate", "tarifphasen"}
    assert echo.werte.rate is None


def test_karte_klickt_den_tarif_auf_der_tarifauswahl(karte):
    assert karte.weiter.klicken == "tarif"
    assert karte.summe
    assert karte.knoepfe["tarif"].fest is None


@pytest.mark.parametrize("mit_name", [True, False], ids=["nachweis", "ohne"])
def test_rohsatz_nimmt_den_tarifnamen_aus_dem_nachweis(karte, nutzlast, mit_name):
    from bestand_pfad import lese_wurzel

    from telco_radar.collect.geraete.klickergebnis import kombination_als_daten
    from telco_radar.collect.geraete.klicklauf import ERFASST, Kombiergebnis
    from telco_radar.collect.geraete.klickrohsatz import rohsatz
    from telco_radar.geraete_config import lade_katalog

    lesung = _lesung(karte, nutzlast, "269")
    variante = Variante("256 GB", "269", 36)
    echo = pruefe_echo(
        variante,
        variante,
        Preiswerte(anzahlung=1.0),
        lesung,
        buendel=Buendelwerte(buendelbetrag=62.61),
        summe=karte.summe,
    )
    nachweise = dict(lesung.nachweise) if mit_name else {}
    ergebnis = Kombiergebnis(variante, ERFASST, werte=echo.werte, nachweise=nachweise)
    kombination = kombination_als_daten(ergebnis)
    seite = {"geraet": "apple-iphone-17-pro", "adresse": "https://www.vodafone.de/x"}
    daten = {"name": "Vodafone", "datum": "2026-10-10"}

    satz = rohsatz(kombination, seite, daten, lade_katalog(lese_wurzel()))

    assert satz["tarif_name"] == ("Mobil M" if mit_name else "269")
    assert (satz["geraet_zuzahlung"], satz["geraet_monatsrate"]) == (1.0, 33.0)
    assert satz["tarif_monatlich"] == 29.61
    assert satz["laufzeit_monate"] == 36
    assert [
        (p["von_monat"], p["bis_monat"], p["betrag"]) for p in satz["tarif_phasen"]
    ] == [(1, 24, 29.61)]
