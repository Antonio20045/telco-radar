"""Klick-Karte Format 2, Stufe 3 im Lader und im Echo: Adressen, Vertragsform, 202.

Erkundung vom 07.10.2026: Telekom führt den Tarif über die Adresse (``tariffId``),
freenet jedes Bündel auf eigener Seite, 1&1 und freenet sind ein Vertrag aus Gerät und
Tarif (Bündelbetrag und Einmalzahlung, keine Rate); Telekom antwortete auf eine
xhr- und eine Skriptanfrage der eigenen Website mit HTTP 202. Die Karten und Adressen
hier sind Beispiele.
"""

from __future__ import annotations

import copy

import pytest

BASIS = {
    "anbieter": "Beispielanbieter",
    "knoepfe": {
        "speicher": {"selektor": "#speicher button"},
        "tarif": {"adressen": {"selektor": "a.tarif", "parameter": "tariffId"}},
        "laufzeit": {"fest": 24},
        "gewaehlt": {"attribut": "aria-pressed", "wert": "true"},
    },
    "zusammenfassung": {"selektor": "#preis"},
    "antwort": {
        "skript": "#zustand",
        "pfade": {"rate": "preis.rate"},
        "variante": {"tarif": "tarif"},
    },
    "kanarie": {"selektor": "#kanarie", "enthaelt": "Beispielhandy X"},
}
BUENDEL = {
    "vertragsform": "ein_vertrag",
    "antwort": {
        "global": "preise",
        "pfade": {
            "buendelbetrag": {"pfad": "preise.monat", "einheit": "cent"},
            "einmalzahlung": "preise.einmal",
        },
        "variante": {"tarif": "preise.tarif"},
    },
    "zusammenfassung": {
        "selektor": "#preis",
        "muster": {"buendelbetrag": r"([\d,]+) €/Monat"},
    },
}


def _lade(**teile):
    from telco_radar.collect.geraete.klickkarte import klickkarte_aus_daten

    daten = copy.deepcopy(BASIS)
    daten.update(copy.deepcopy(teile))
    return klickkarte_aus_daten(daten, "Prüfkarte")


def _fehler(**teile) -> tuple[str, str]:
    from telco_radar.collect.geraete.klickkarte import KlickkartenFehler

    with pytest.raises(KlickkartenFehler) as fehler:
        _lade(**teile)
    return fehler.value.feld, fehler.value.grund


def test_adressen_einer_dimension_mit_standardattribut():
    karte = _lade()

    knopf = karte.knoepfe["tarif"]
    assert (knopf.selektor, knopf.fest) == (None, None)
    assert (knopf.adressen.selektor, knopf.adressen.attribut) == ("a.tarif", "href")
    assert knopf.adressen.parameter == "tariffId"
    assert karte.adressdimension == "tarif"
    fest = karte.mit_fest("tarif", "MF_1")
    assert fest.knoepfe["tarif"].fest == "MF_1"
    assert fest.adressdimension is None
    assert (
        _lade(knoepfe=BASIS["knoepfe"] | {"tarif": {"fest": "M"}}).adressdimension
        is None
    )


@pytest.mark.parametrize(
    ("tarif", "laufzeit", "feld"),
    [
        (
            {"adressen": {"selektor": "a", "parameter": "t"}, "selektor": "#t b"},
            {"fest": 24},
            "knoepfe.tarif.selektor",
        ),
        (
            {"adressen": {"selektor": "a"}},
            {"fest": 24},
            "knoepfe.tarif.adressen.parameter",
        ),
        (
            {"adressen": {"selektor": "a", "parameter": "t", "muster": "x"}},
            {"fest": 24},
            "knoepfe.tarif.adressen.muster",
        ),
        (
            {"adressen": {"selektor": "a", "parameter": "t"}},
            {"adressen": {"selektor": "a.l", "parameter": "l"}},
            "knoepfe.laufzeit.adressen",
        ),
    ],
)
def test_kaputte_adressen_nennen_die_stelle(tarif, laufzeit, feld):
    knoepfe = {**BASIS["knoepfe"], "tarif": tarif, "laufzeit": laufzeit}

    assert _fehler(knoepfe=knoepfe)[0] == feld


def test_ein_vertrag_mit_buendelfeldern_ohne_rate():
    karte = _lade(**BUENDEL)

    assert karte.ein_vertrag
    assert karte.entfallen == ("rate", "ratenzahl")
    assert "rate" not in karte.lesefelder
    assert karte.lesefelder[-2:] == ("buendelbetrag", "einmalzahlung")
    assert karte.antwort.pfade["buendelbetrag"].einheit == "cent"
    assert set(karte.textlesung.muster) == {"buendelbetrag"}
    assert not _lade().ein_vertrag
    assert _lade().entfallen == ()


@pytest.mark.parametrize(
    ("teile", "feld", "grund"),
    [
        (
            {"antwort": BUENDEL["antwort"]},
            "antwort.pfade.buendelbetrag",
            "nur mit vertragsform ein_vertrag",
        ),
        (
            {"zusammenfassung": BUENDEL["zusammenfassung"]},
            "zusammenfassung.muster.buendelbetrag",
            "nur mit vertragsform ein_vertrag",
        ),
        (
            {"vertragsform": "ein_vertrag"},
            "antwort.pfade.rate",
            "entfällt bei vertragsform ein_vertrag",
        ),
        (
            {
                "vertragsform": "ein_vertrag",
                "antwort": [BUENDEL["antwort"], BASIS["antwort"]],
            },
            "antwort.1.pfade.rate",
            "entfällt bei vertragsform ein_vertrag",
        ),
        (
            {"vertragsform": "leasing"},
            "vertragsform",
            "unbekannte Vertragsform leasing",
        ),
    ],
)
def test_vertragsform_prueft_die_felder(teile, feld, grund):
    assert _fehler(**teile) == (feld, grund)


def _echo(antwort, **weiter):
    from telco_radar.collect.geraete.klickecho import (
        Antwortlesung,
        Preiswerte,
        Variante,
        pruefe_echo,
    )

    gewaehlt = Variante("256 GB", "M", 24)
    lesung = Antwortlesung(Preiswerte(anzahlung=1.0), {}, antwort)
    return pruefe_echo(gewaehlt, gewaehlt, Preiswerte(anzahlung=1.0), lesung, **weiter)


def test_echo_vergleicht_buendelwerte_und_rate_entfaellt():
    from telco_radar.collect.geraete.klicktext import Buendelwerte

    gleich = Buendelwerte(44.99, 29.99)
    entfallen = ("rate", "ratenzahl")

    echo = _echo(gleich, buendel=gleich, entfallen=entfallen)

    assert echo.stimmt
    assert echo.buendel == gleich
    assert not {"rate", "ratenzahl"} & set(echo.luecken)
    ohne = _echo(gleich)
    assert {"rate", "ratenzahl"} <= set(ohne.luecken)
    assert ohne.buendel == Buendelwerte()
    anders = _echo(Buendelwerte(44.99, 19.99), buendel=gleich, entfallen=entfallen)
    assert [(b.feld, b.grund) for b in anders.befunde] == [
        ("einmalzahlung", "Text 29,99, Antwort 19,99")
    ]
    assert anders.buendel == Buendelwerte(44.99, None)


@pytest.mark.parametrize(
    ("url", "status", "art", "verdacht"),
    [
        ("https://www.b.invalid/opt-in/cookie.php", 202, "xhr", True),
        ("https://static.b.invalid/legalnote/p.js", 202, "script", True),
        ("https://www.andere.invalid/p.js", 202, "script", False),
        ("https://www.b.invalid/p.js", 403, "script", False),
        ("https://www.b.invalid/api/x", 429, "fetch", True),
        ("https://www.b.invalid/api/x", 200, "fetch", False),
    ],
)
def test_202_auf_jede_anfrage_der_eigenen_website_ist_verdacht(
    url, status, art, verdacht
):
    from telco_radar.collect.geraete.klickspur import (
        Eintrag,
        bot_verdacht,
        status_verdacht,
    )

    seite = "https://www.b.invalid/handy/x"

    grund = status_verdacht(url, status, art, seite)

    assert (grund is not None) == verdacht
    assert bot_verdacht(Eintrag(1, "GET", url, art, status), "", seite) == grund
    if verdacht:
        assert grund == f"Abruf gestört (HTTP {status} auf {url})"
