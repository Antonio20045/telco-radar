"""Echo der Preiszusammenfassung (Datenkonzept Geräteradar, Abschnitt 8, Punkt 4).

Der Klick-Crawler liest nach jedem Klick dieselben Werte zweimal: aus dem sichtbaren
Text der Preiszusammenfassung und aus der mitgeschnittenen Antwort. Ein Wert gilt nur,
wenn beide übereinstimmen und die Seite die gewählte Variante anzeigt; sonst entsteht
ein Befund mit Grund. Ein fehlender Wert ist ``None``, nie 0. Texte und Antworten hier
sind Beispiele, kein echter Anbieter.
"""

from __future__ import annotations

import math

import pytest

from telco_radar.collect.geraete.klickkarte import WERTFELDER, klickkarte_aus_daten
from telco_radar.tarif_model import Preisphase

ZUSAMMENFASSUNG = (
    "Ihre Auswahl: 256 GB · Tarif M · 24 Monate\n"
    "Einmalige Anzahlung 1.099,00 €\n"
    "Monatliche Gerätrate 25,00 € · 24 Raten\n"
    "Tarif M: 39,99 € mtl. in den Monaten 1–24, ab dem 25. Monat 49,99 € mtl.\n"
    "Mindestlaufzeit 24 Monate\n"
    "Anschlusspreis 39,99 €\n"
    "Datenvolumen 1.000 GB\n"
)
PHASEN_M = (Preisphase(1, 24, 39.99), Preisphase(25, None, 49.99))
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
            "anzahlung": "preis.anzahlung",
            "rate": "preis.rate",
            "ratenzahl": "preis.raten",
            "tarifphasen": {
                "liste": "tarif.phasen",
                "von": "ab",
                "bis": "bis",
                "betrag": "betrag",
            },
            "tarifbindung": "tarif.mindestlaufzeit",
            "anschluss": "tarif.anschluss",
            "volumen_gb": "tarif.volumen_gb",
        },
        "variante": {
            "speicher": "auswahl.speicher",
            "tarif": "auswahl.tarif",
            "laufzeit": "auswahl.laufzeit",
        },
    },
    "kanarie": {"selektor": "#kanarie", "enthaelt": "Beispielhandy X"},
}
ANTWORT = {
    "auswahl": {"speicher": 256, "tarif": "M", "laufzeit": "24"},
    "preis": {"anzahlung": 1099, "rate": "25,00", "raten": 24},
    "tarif": {
        "phasen": [
            {"ab": 1, "bis": 24, "betrag": 39.99},
            {"ab": 25, "bis": None, "betrag": "49,99"},
        ],
        "mindestlaufzeit": 24,
        "anschluss": 39.99,
        "volumen_gb": "1.000 GB",
    },
}


def _muster():
    return klickkarte_aus_daten(KARTE, "Beispielkarte").antwort


def _werte(**abweichend):
    from telco_radar.collect.geraete.klickecho import Preiswerte

    voll = dict(
        anzahlung=1099.0,
        rate=25.0,
        ratenzahl=24,
        tarifphasen=PHASEN_M,
        tarifbindung=24,
        anschluss=39.99,
        volumen_gb=1000.0,
    )
    voll.update(abweichend)
    return Preiswerte(**voll)


def _lesung(werte=None, variante=None):
    from telco_radar.collect.geraete.klickecho import Antwortlesung

    if variante is None:
        variante = {"speicher": "256", "tarif": "M", "laufzeit": 24}
    return Antwortlesung(werte=werte or _werte(), variante=variante)


def _variante(speicher="256", tarif="M", laufzeit=24):
    from telco_radar.collect.geraete.klickecho import Variante

    return Variante(speicher=speicher, tarif=tarif, laufzeit=laufzeit)


def test_preiswerte_tragen_genau_die_wertfelder_der_karte():
    from dataclasses import fields

    from telco_radar.collect.geraete.klickecho import Preiswerte

    assert tuple(f.name for f in fields(Preiswerte)) == WERTFELDER


def test_zusammenfassung_liefert_alle_werte():
    from telco_radar.collect.geraete.klickecho import lies_zusammenfassung

    assert lies_zusammenfassung(ZUSAMMENFASSUNG) == _werte()


@pytest.mark.parametrize(
    ("text", "feld", "erwartet"),
    [
        ("Einmalige Anzahlung 1.099,00 €", "anzahlung", 1099.0),
        ("Anzahlung 0,00 €", "anzahlung", 0.0),
        ("Zuzahlung: 49 €", "anzahlung", 49.0),
        ("Monatliche Rate 1.234,56 €", "rate", 1234.56),
        ("Geräterate 7,5 €", "rate", 7.5),
        ("24 x 41,63 €", "rate", 41.63),
        ("24 x 41,63 €", "ratenzahl", 24),
        ("36 monatliche Raten", "ratenzahl", 36),
        ("Anschlusspreis 0,00 €", "anschluss", 0.0),
        ("Bereitstellungspreis 39,99\xa0€", "anschluss", 39.99),
        ("Datenvolumen 1.000 GB", "volumen_gb", 1000.0),
        ("Datenvolumen 12,5 GB", "volumen_gb", 12.5),
        ("Datenvolumen 500 MB", "volumen_gb", 0.5),
        ("Highspeed-Volumen 1,5 TB", "volumen_gb", 1500.0),
        ("Unbegrenztes Datenvolumen", "volumen_gb", math.inf),
        ("Mindestvertragslaufzeit: 24 Monate", "tarifbindung", 24),
        ("Tarifbindung 12 Monate", "tarifbindung", 12),
    ],
)
def test_deutsche_zahlen_im_text(text, feld, erwartet):
    from telco_radar.collect.geraete.klickecho import lies_zusammenfassung

    wert = getattr(lies_zusammenfassung(text), feld)

    assert wert is not None
    assert wert == erwartet


@pytest.mark.parametrize(
    ("zeile", "phasen"),
    [
        (
            "Tarif M: 39,99 € mtl. in den Monaten 1–24, ab dem 25. Monat 49,99 € mtl.",
            PHASEN_M,
        ),
        (
            "Tarif L: in den ersten 6 Monaten 9,99 €, danach 29,99 € mtl.",
            (Preisphase(1, 6, 9.99), Preisphase(7, None, 29.99)),
        ),
        ("Grundgebühr 19,99 € monatlich", (Preisphase(1, None, 19.99),)),
        (
            "Tarif S · 24 Monate\nGrundpreis 29,99 € mtl., ab Monat 25: 34,99 €",
            (Preisphase(1, 24, 29.99), Preisphase(25, None, 34.99)),
        ),
    ],
)
def test_tarifpreis_mit_phasen(zeile, phasen):
    from telco_radar.collect.geraete.klickecho import lies_zusammenfassung

    assert lies_zusammenfassung(zeile).tarifphasen == phasen


def test_fehlende_werte_sind_none_nicht_null():
    from telco_radar.collect.geraete.klickecho import Preiswerte, lies_zusammenfassung

    werte = lies_zusammenfassung("Ihre Auswahl: 128 GB · Tarif S · 24 Monate")

    assert werte == Preiswerte()
    assert all(getattr(werte, feld) is None for feld in WERTFELDER)


def test_antwort_liefert_dieselben_werte_aus_den_pfaden_der_karte():
    from telco_radar.collect.geraete.klickecho import lies_antwort

    lesung = lies_antwort(ANTWORT, _muster())

    assert lesung.werte == _werte()
    assert dict(lesung.variante) == {"speicher": "256", "tarif": "M", "laufzeit": 24}


def test_antwort_ohne_werte_bleibt_none():
    from telco_radar.collect.geraete.klickecho import Preiswerte, lies_antwort

    nutzlast = {"preis": {"anzahlung": True, "rate": None, "raten": "keine"}}

    lesung = lies_antwort(nutzlast, _muster())

    assert lesung.werte == Preiswerte()
    assert dict(lesung.variante) == {"speicher": None, "tarif": None, "laufzeit": None}


def test_antwort_mit_einfachem_tarifpfad_und_listenstelle():
    from telco_radar.collect.geraete.klickecho import lies_antwort

    karte = {
        **KARTE,
        "antwort": {
            "url_muster": "/api/preis",
            "pfade": {"tarifphasen": "tarife.0.preis", "volumen_gb": "tarife.0.gb"},
        },
    }
    muster = klickkarte_aus_daten(karte, "Beispielkarte").antwort
    nutzlast = {"tarife": [{"preis": "19,99", "gb": "unbegrenzt"}]}

    lesung = lies_antwort(nutzlast, muster)

    assert lesung.werte.tarifphasen == (Preisphase(1, None, 19.99),)
    assert lesung.werte.volumen_gb == math.inf
    assert dict(lesung.variante) == {}


def test_echo_uebernimmt_was_text_antwort_und_variante_teilen():
    from telco_radar.collect.geraete.klickecho import pruefe_echo

    echo = pruefe_echo(_variante(), _variante(), _werte(), _lesung())

    assert echo.stimmt
    assert echo.befunde == ()
    assert echo.luecken == ()
    assert echo.werte == _werte()


def test_echo_toleriert_rundung_unter_einem_cent():
    from telco_radar.collect.geraete.klickecho import pruefe_echo

    antwort = _lesung(_werte(rate=25.000001))

    echo = pruefe_echo(_variante(), _variante(), _werte(), antwort)

    assert echo.stimmt
    assert echo.werte.rate == 25.0


def test_abweichende_rate_wird_befund_die_uebrigen_werte_bleiben():
    from telco_radar.collect.geraete.klickecho import pruefe_echo

    echo = pruefe_echo(_variante(), _variante(), _werte(rate=24.0), _lesung())

    assert not echo.stimmt
    assert [b.feld for b in echo.befunde] == ["rate"]
    assert "24,00" in echo.befunde[0].grund
    assert "25,00" in echo.befunde[0].grund
    assert echo.werte.rate is None
    assert echo.werte.anzahlung == 1099.0
    assert echo.werte.tarifphasen == PHASEN_M


def test_andere_angezeigte_variante_verwirft_alle_werte():
    from telco_radar.collect.geraete.klickecho import Preiswerte, pruefe_echo

    echo = pruefe_echo(_variante(), _variante(speicher="128"), _werte(), _lesung())

    assert [b.feld for b in echo.befunde] == ["variante.speicher"]
    assert "128" in echo.befunde[0].grund
    assert echo.werte == Preiswerte()


def test_antwort_fuer_eine_andere_variante_verwirft_alle_werte():
    from telco_radar.collect.geraete.klickecho import Preiswerte, pruefe_echo

    antwort = _lesung(variante={"speicher": "256", "tarif": "M", "laufzeit": 36})

    echo = pruefe_echo(_variante(), _variante(), _werte(), antwort)

    assert [b.feld for b in echo.befunde] == ["antwort.laufzeit"]
    assert echo.werte == Preiswerte()


def test_wert_nur_auf_einer_seite_wird_befund():
    from telco_radar.collect.geraete.klickecho import pruefe_echo

    nur_text = pruefe_echo(
        _variante(), _variante(), _werte(), _lesung(_werte(anschluss=None))
    )
    nur_antwort = pruefe_echo(
        _variante(), _variante(), _werte(volumen_gb=None), _lesung()
    )

    assert [b.feld for b in nur_text.befunde] == ["anschluss"]
    assert "Antwort" in nur_text.befunde[0].grund
    assert nur_text.werte.anschluss is None
    assert [b.feld for b in nur_antwort.befunde] == ["volumen_gb"]
    assert "Text" in nur_antwort.befunde[0].grund
    assert nur_antwort.werte.volumen_gb is None


def test_wert_auf_keiner_seite_ist_benannte_luecke():
    from telco_radar.collect.geraete.klickecho import pruefe_echo

    ohne = _werte(anschluss=None)

    echo = pruefe_echo(_variante(), _variante(), ohne, _lesung(ohne))

    assert echo.stimmt
    assert echo.luecken == ("anschluss",)
    assert echo.werte.anschluss is None


def test_ohne_antwort_gilt_kein_wert():
    from telco_radar.collect.geraete.klickecho import Preiswerte, pruefe_echo

    echo = pruefe_echo(_variante(), _variante(), _werte(), None)

    assert [b.feld for b in echo.befunde] == ["antwort"]
    assert echo.werte == Preiswerte()


def test_ratenzahl_muss_zur_gewaehlten_laufzeit_passen():
    from telco_radar.collect.geraete.klickecho import pruefe_echo

    gewaehlt = _variante(laufzeit=36)
    antwort = _lesung(variante={"speicher": "256", "tarif": "M"})

    echo = pruefe_echo(gewaehlt, gewaehlt, _werte(), antwort)

    assert [b.feld for b in echo.befunde] == ["ratenzahl"]
    assert echo.werte.ratenzahl is None
    assert echo.werte.rate == 25.0


def test_ohne_jeden_wert_ist_es_ein_befund_kein_leeres_ergebnis():
    from telco_radar.collect.geraete.klickecho import Preiswerte, pruefe_echo

    echo = pruefe_echo(_variante(), _variante(), Preiswerte(), _lesung(Preiswerte()))

    assert not echo.stimmt
    assert [b.feld for b in echo.befunde] == ["werte"]
    assert echo.luecken == WERTFELDER


@pytest.mark.parametrize(
    ("roh", "erwartet"),
    [
        ((256, " M ", "24 Monate"), ("256", "M", 24)),
        (("128 GB", "S", 36), ("128 GB", "S", 36)),
        ((None, "", "keine"), (None, None, None)),
    ],
)
def test_variante_wird_einheitlich_gelesen(roh, erwartet):
    from telco_radar.collect.geraete.klickecho import variante_aus

    variante = variante_aus(*roh)

    assert (variante.speicher, variante.tarif, variante.laufzeit) == erwartet
