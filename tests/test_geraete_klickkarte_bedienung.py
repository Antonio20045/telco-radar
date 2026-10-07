"""Klick-Karte Format 2, Bedienung: was der Lader annimmt und was er ablehnt.

Erkundung vom 07.10.2026: bei keinem der fünf Netzbetreiber lief die Karte im alten
Format. Die Befunde verlangen eine Marke je Dimension und als CSS (Eigenschaft
``checked``, Klassen-Token, Attribut), den Wert an einem Kind-Element oder per Muster,
eine feste Dimension ohne Knöpfe, eine Vorbereitung vor jeder Lesung, einen Dialog vor
der Lesung und einen Kanarienwert je Gerät. Eine kaputte Karte wirft
``KlickkartenFehler`` mit Punktpfad. Die Karten hier sind Beispiele.
"""

from __future__ import annotations

import copy

import pytest

BASIS = {
    "anbieter": "Beispielanbieter",
    "knoepfe": {
        "speicher": {"selektor": "#speicher button", "wert": "data-wert"},
        "tarif": {"selektor": "#tarif label"},
        "laufzeit": {"selektor": "#laufzeit label"},
        "gewaehlt": {"attribut": "aria-pressed", "wert": "true"},
    },
    "zusammenfassung": {"selektor": "#preis"},
    "antwort": {
        "url_muster": r"/api/preis\?",
        "pfade": {"rate": "preis.rate"},
        "variante": {"speicher": "auswahl.speicher"},
    },
    "kanarie": {"selektor": "#kanarie", "enthaelt": "Beispielhandy X"},
}


def _lade(**ersetzt):
    from telco_radar.collect.geraete.klickkarte import klickkarte_aus_daten

    daten = copy.deepcopy(BASIS)
    for pfad, wert in ersetzt.items():
        *weg, letztes = pfad.split("__")
        knoten = daten
        for teil in weg:
            knoten = knoten[teil]
        if wert is None:
            del knoten[letztes]
        else:
            knoten[letztes] = wert
    return klickkarte_aus_daten(daten, "Prüfkarte")


def _fehler(**ersetzt) -> str:
    from telco_radar.collect.geraete.klickkarte import KlickkartenFehler

    with pytest.raises(KlickkartenFehler) as fehler:
        _lade(**ersetzt)
    return fehler.value.feld


def test_marke_je_dimension_geht_vor_der_marke_der_karte():
    karte = _lade(
        knoepfe__tarif={
            "selektor": "#tarif label",
            "gewaehlt": {"attribut": "data-selected", "wert": "true"},
        },
        knoepfe__laufzeit={
            "selektor": "#laufzeit label",
            "gewaehlt": {"passt": "input:checked + label"},
        },
    )

    assert karte.marke("speicher").attribut == "aria-pressed"
    assert karte.marke("tarif").attribut == "data-selected"
    assert karte.marke("laufzeit").passt == "input:checked + label"
    assert karte.marke("laufzeit").attribut is None


def test_ohne_marke_der_karte_braucht_jede_geklickte_dimension_eine_eigene():
    eigene = {"passt": ".-active"}
    karte = _lade(
        knoepfe__gewaehlt=None,
        knoepfe__speicher={"selektor": "#speicher a", "gewaehlt": eigene},
        knoepfe__tarif={"selektor": "#tarif a", "gewaehlt": eigene},
        knoepfe__laufzeit={"fest": 24},
    )

    assert karte.gewaehlt is None
    assert karte.marke("speicher").passt == ".-active"
    assert _fehler(knoepfe__gewaehlt=None) == "knoepfe.gewaehlt"


@pytest.mark.parametrize(
    ("marke", "gemeldet"),
    [
        ({"passt": ":checked", "attribut": "aria-checked"}, "knoepfe.gewaehlt.passt"),
        ({"wert": "true"}, "knoepfe.gewaehlt.attribut"),
        ({"passt": " "}, "knoepfe.gewaehlt.passt"),
        ({"klasse": "-active"}, "knoepfe.gewaehlt.klasse"),
    ],
)
def test_kaputte_marke_wirft_mit_punktpfad(marke, gemeldet):
    assert _fehler(knoepfe__gewaehlt=marke) == gemeldet


def test_wert_am_kind_element_und_per_muster():
    karte = _lade(
        knoepfe__tarif={
            "selektor": "#tarif label",
            "wert_in": "input",
            "wert": "aria-label",
            "muster": "^Tarifoption (.+)$",
        },
        knoepfe__laufzeit={"selektor": "#laufzeit label", "muster": r"^(\d+) mtl\."},
    )

    tarif = karte.knoepfe["tarif"]
    assert (tarif.wert_in, tarif.wert_attribut) == ("input", "aria-label")
    assert tarif.muster.pattern == "^Tarifoption (.+)$"
    assert karte.knoepfe["laufzeit"].muster.search("36 mtl. Zahlungen")[1] == "36"
    assert karte.knoepfe["speicher"].muster is None


def test_kaputtes_muster_nennt_die_stelle():
    knopf = {"selektor": "#tarif label", "muster": "(offen"}

    assert _fehler(knoepfe__tarif=knopf) == "knoepfe.tarif.muster"


def test_feste_dimension_hat_keinen_knopf():
    karte = _lade(knoepfe__laufzeit={"fest": 36})

    laufzeit = karte.knoepfe["laufzeit"]
    assert (laufzeit.fest, laufzeit.selektor) == ("36", None)
    assert karte.knoepfe["tarif"].fest is None


@pytest.mark.parametrize(
    ("knopf", "gemeldet"),
    [
        ({"fest": 36, "selektor": "#laufzeit label"}, "knoepfe.laufzeit.selektor"),
        ({"fest": 36, "muster": "x"}, "knoepfe.laufzeit.muster"),
        ({"fest": " "}, "knoepfe.laufzeit.fest"),
    ],
)
def test_feste_dimension_mit_knopfteilen_wirft(knopf, gemeldet):
    assert _fehler(knoepfe__laufzeit=knopf) == gemeldet


def test_vorbereitung_als_liste_von_zustaenden():
    from telco_radar.collect.geraete.klickkarte import Vorbereitung

    karte = _lade(
        vorbereitung=[
            {"klick": "#rueckgabe", "bis": '[aria-checked="false"]'},
            {"klick": "label:has(#ohne)", "pruefe": "#ohne", "bis": ":checked"},
        ]
    )

    assert karte.vorbereitung == (
        Vorbereitung("#rueckgabe", '[aria-checked="false"]'),
        Vorbereitung("label:has(#ohne)", ":checked", "#ohne"),
    )
    assert _lade().vorbereitung == ()


@pytest.mark.parametrize(
    ("vorbereitung", "gemeldet"),
    [
        ({"klick": "#rueckgabe"}, "vorbereitung"),
        ([], "vorbereitung"),
        ([{"klick": "#rueckgabe"}], "vorbereitung.0.bis"),
        ([{"klick": "#a", "bis": "x", "warte": 5}], "vorbereitung.0.warte"),
    ],
)
def test_kaputte_vorbereitung_wirft(vorbereitung, gemeldet):
    assert _fehler(vorbereitung=vorbereitung) == gemeldet


def test_dialog_vor_der_lesung():
    karte = _lade(
        zusammenfassung={
            "selektor": "#preis",
            "oeffnen": "button:has-text('Preisübersicht anzeigen')",
            "schliessen": "#zu",
        }
    )

    assert karte.textlesung.oeffnen == "button:has-text('Preisübersicht anzeigen')"
    assert karte.textlesung.schliessen == "#zu"
    assert karte.zusammenfassung == "#preis"
    assert _lade().textlesung.oeffnen is None


def test_kanarie_mit_modellname_und_attribut():
    karte = _lade(
        kanarie={
            "selektor": "label.kachel",
            "attribut": "aria-label",
            "enthaelt": "Speicherauswahl {modell}",
        }
    )

    assert karte.kanarie.attribut == "aria-label"
    assert karte.kanarie.enthaelt == "Speicherauswahl {modell}"
    assert _fehler(kanarie__enthaelt="{hersteller} {modell}") == "kanarie.enthaelt"
