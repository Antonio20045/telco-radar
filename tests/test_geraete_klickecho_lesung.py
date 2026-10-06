"""Lesung der Preiszusammenfassung und Variantenprüfung: Grenzfälle des Prüfers.

Ein entfallender Posten bekommt nicht den nächsten Betrag, begrenztes Volumen wird nicht
unbegrenzt, ein Betrag vor „in den ersten N Monaten“ ist Phase 1–N, widersprüchliche
Phasen fallen weg, eine nicht lesbare Laufzeit gilt nie als bestätigt und die Antwort
nennt ihre Variante über Pfad oder Adressparameter (Pflicht in der Klick-Karte).
"""

from __future__ import annotations

import copy
import math

import pytest

from telco_radar.tarif_model import Preisphase

KARTE = {
    "anbieter": "Beispielanbieter",
    "knoepfe": {
        "speicher": {"selektor": "#speicher button", "wert": "data-wert"},
        "tarif": {"selektor": "#tarif button", "wert": "data-wert"},
        "laufzeit": {"selektor": "#laufzeit button", "wert": "data-wert"},
        "gewaehlt": {"attribut": "aria-pressed", "wert": "true"},
    },
    "zusammenfassung": {"selektor": "#preis"},
    "antwort": {
        "url_muster": r"/api/preis\?",
        "pfade": {
            "rate": "rate",
            "tarifphasen": {
                "liste": "phasen",
                "von": "ab",
                "bis": "bis",
                "betrag": "b",
            },
        },
        "parameter": {"tarif": "tarif", "laufzeit": "lz"},
    },
    "kanarie": {"selektor": "#kanarie", "enthaelt": "Beispielhandy X"},
}


def _karte(**antwort):
    from telco_radar.collect.geraete.klickkarte import klickkarte_aus_daten

    daten = copy.deepcopy(KARTE)
    daten["antwort"].update(antwort)
    daten["antwort"] = {k: v for k, v in daten["antwort"].items() if v is not None}
    return klickkarte_aus_daten(daten, "Prüfkarte")


@pytest.mark.parametrize(
    ("text", "feld", "erwartet"),
    [
        ("Anzahlung entfällt · Monatliche Rate 25,00 €", "anzahlung", 0.0),
        ("Anzahlung: keine · Rate: 25,00 € · 24 Raten", "anzahlung", 0.0),
        ("Keine Anzahlung · Monatliche Rate 25,00 €", "anzahlung", 0.0),
        ("Bereitstellungspreis entfällt (sonst 39,99 €)", "anschluss", 0.0),
        ("Anschlusspreis 0,00 € statt 39,99 €", "anschluss", 0.0),
        ("Anzahlung 99,00 € · Monatliche Rate 25,00 €", "anzahlung", 99.0),
        ("Anzahlung entfällt · Monatliche Rate 25,00 €", "rate", 25.0),
        ("Anzahlung: keine · Rate: 25,00 € · 24 Raten", "ratenzahl", 24),
    ],
)
def test_entfallender_posten_bekommt_nicht_den_naechsten_betrag(text, feld, erwartet):
    from telco_radar.collect.geraete.klickecho import lies_zusammenfassung

    assert getattr(lies_zusammenfassung(text), feld) == erwartet


@pytest.mark.parametrize(
    ("text", "erwartet"),
    [
        ("Allnet-Flat: unbegrenzt telefonieren, 20 GB Datenvolumen", 20.0),
        ("Datenvolumen 20 GB, danach unbegrenzt mit max. 64 kbit/s", 20.0),
        ("Datenvolumen unbegrenzt", math.inf),
        ("Datenvolumen unbegrenzt (statt 50 GB)", math.inf),
    ],
)
def test_unbegrenzt_nur_ohne_gb_zahl(text, erwartet):
    from telco_radar.collect.geraete.klickecho import lies_zusammenfassung

    assert lies_zusammenfassung(text).volumen_gb == erwartet


@pytest.mark.parametrize(
    ("zeile", "phasen"),
    [
        (
            "Tarif M: 39,99 € mtl. in den ersten 24 Monaten, danach 49,99 € mtl.",
            (Preisphase(1, 24, 39.99), Preisphase(25, None, 49.99)),
        ),
        (
            "Tarif M: in den ersten 6 Monaten 9,99 €, danach 19,99 € mtl.",
            (Preisphase(1, 6, 9.99), Preisphase(7, None, 19.99)),
        ),
        ("Tarif M: 29,99 € mtl. in den Monaten 24–1", None),
        ("Tarif M: 29,99 € mtl., ab dem 1. Monat 34,99 € mtl.", None),
    ],
)
def test_tarifphasen_betrag_vor_den_ersten_monaten_und_widersprueche(zeile, phasen):
    from telco_radar.collect.geraete.klickecho import lies_zusammenfassung

    assert lies_zusammenfassung(zeile).tarifphasen == phasen


def test_antwortphase_mit_ende_vor_dem_anfang_faellt_weg():
    from telco_radar.collect.geraete.klickecho import lies_antwort

    nutzlast = {"rate": 25, "phasen": [{"ab": 25, "bis": 1, "b": 39.99}]}

    lesung = lies_antwort(nutzlast, _karte().antwort, "/api/preis?tarif=M&lz=24")

    assert lesung.werte.tarifphasen is None
    assert lesung.werte.rate == 25.0


def test_nicht_lesbare_gewaehlte_laufzeit_bestaetigt_nichts():
    from telco_radar.collect.geraete.klickecho import (
        Antwortlesung,
        Preiswerte,
        pruefe_echo,
        variante_aus,
    )

    werte = Preiswerte(anzahlung=99.0, rate=25.0, ratenzahl=24)
    gewaehlt = variante_aus("256", "M", "Einmalzahlung")

    echo = pruefe_echo(
        gewaehlt, variante_aus("256", "M", "24"), werte, Antwortlesung(werte, {})
    )
    gleich = pruefe_echo(gewaehlt, gewaehlt, werte, Antwortlesung(werte, {}))

    assert not echo.stimmt
    assert echo.werte == Preiswerte()
    assert [b.feld for b in gleich.befunde] == ["variante.laufzeit"]
    assert gleich.werte == Preiswerte()


def test_lesbare_gleiche_variante_bestaetigt():
    from telco_radar.collect.geraete.klickecho import (
        Antwortlesung,
        Preiswerte,
        pruefe_echo,
        variante_aus,
    )

    werte = Preiswerte(anzahlung=99.0, rate=25.0, ratenzahl=24)
    gewaehlt = variante_aus("256", "M", "24")

    echo = pruefe_echo(gewaehlt, gewaehlt, werte, Antwortlesung(werte, {}))

    assert echo.stimmt
    assert echo.werte == werte


def test_antwort_nennt_variante_ueber_adressparameter():
    from telco_radar.collect.geraete.klickecho import (
        Preiswerte,
        lies_antwort,
        pruefe_echo,
        variante_aus,
    )

    muster = _karte().antwort
    lesung = lies_antwort(
        {"rate": 30}, muster, "https://x.invalid/api/preis?tarif=M&lz=24"
    )
    text = Preiswerte(rate=30.0)

    passend = pruefe_echo(
        variante_aus("1", "M", "24"), variante_aus("1", "M", "24"), text, lesung
    )
    fremd = pruefe_echo(
        variante_aus("1", "L", "24"), variante_aus("1", "L", "24"), text, lesung
    )

    assert dict(lesung.variante) == {"tarif": "M", "laufzeit": 24}
    assert passend.stimmt
    assert [b.feld for b in fremd.befunde] == ["antwort.tarif"]
    assert fremd.werte == Preiswerte()


def test_antwort_ohne_genannten_parameter_ist_befund():
    from telco_radar.collect.geraete.klickecho import (
        Preiswerte,
        lies_antwort,
        pruefe_echo,
        variante_aus,
    )

    lesung = lies_antwort(
        {"rate": 30}, _karte().antwort, "https://x.invalid/api/preis?a=1"
    )
    gewaehlt = variante_aus("1", "M", "24")

    echo = pruefe_echo(gewaehlt, gewaehlt, Preiswerte(rate=30.0), lesung)

    assert {b.feld for b in echo.befunde} == {"antwort.tarif", "antwort.laufzeit"}


def test_karte_ohne_antwortvariante_ist_unvollstaendig():
    from telco_radar.collect.geraete.klickkarte import KlickkartenFehler

    with pytest.raises(KlickkartenFehler) as fehler:
        _karte(parameter=None)

    assert fehler.value.feld == "antwort.variante"


def test_karte_mit_pfad_oder_parameter_fuer_die_variante():
    nur_pfad = _karte(parameter=None, variante={"tarif": "auswahl.tarif"})
    nur_parameter = _karte()

    assert dict(nur_pfad.antwort.variante) == {"tarif": "auswahl.tarif"}
    assert dict(nur_pfad.antwort.parameter) == {}
    assert dict(nur_parameter.antwort.parameter) == {"tarif": "tarif", "laufzeit": "lz"}


@pytest.mark.parametrize(
    ("ersetzt", "feld"),
    [
        ({"parameter": {"farbe": "f"}}, "antwort.parameter.farbe"),
        ({"parameter": {"tarif": ""}}, "antwort.parameter.tarif"),
        ({"parameter": "tarif"}, "antwort.parameter"),
    ],
)
def test_kaputte_parameter_nennen_die_stelle(ersetzt, feld):
    from telco_radar.collect.geraete.klickkarte import KlickkartenFehler

    with pytest.raises(KlickkartenFehler) as fehler:
        _karte(**ersetzt)

    assert fehler.value.feld == feld
