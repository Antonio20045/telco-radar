"""Klick-Karte Format 2, zweite Lesung: Quellen, Seitenwerte und Textmuster im Lader.

Erkundung vom 07.10.2026: congstar und Vodafone laden die Preise einmal (mehrere
Antworten unter einer Adresse), o2 hält den Startzustand in ``script#pageValue``, 1&1
in globalen Variablen; die Variante steht in Seitenadresse, Warenkorb-Link oder einem
Base64-Pfadsegment; Felder brauchen Textmuster und eigene Fundorte. Eine kaputte Karte
wirft ``KlickkartenFehler`` mit Punktpfad. Die Karten hier sind Beispiele.
"""

from __future__ import annotations

import copy

import pytest

BASIS = {
    "anbieter": "Beispielanbieter",
    "knoepfe": {
        "speicher": {"selektor": "#speicher button"},
        "tarif": {"selektor": "#tarif button"},
        "laufzeit": {"selektor": "#laufzeit button"},
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
QUELLEN = [
    {
        "url_muster": "/graphql$",
        "laden": True,
        "erkennung": "data.matrix",
        "pfade": {
            "rate": "data.matrix[plan={tarif}][geraet={geraet}].zahlweisen"
            "[dauer={laufzeit}].rate",
            "volumen_gb": {"pfad": "data.matrix.0.mb", "einheit": "mb"},
        },
        "variante": {"laufzeit": {"pfad": "data.angebot", "muster": r"-(\d+)xhigh"}},
    },
    {"skript": "script#pageValue", "start": True, "pfade": {"anzahlung": "a.b"}},
    {"global": ["hwdVariantsPrices"], "pfade": {"rate": "hwdVariantsPrices.p.0"}},
]
SEITE = {
    "geraet": {
        "selektor": "#warenkorb",
        "attribut": "href",
        "parameter": "deviceVariantId",
    },
    "speicher": {"parameter": "size"},
}


def _lade(**ersetzt):
    from telco_radar.collect.geraete.klickkarte import klickkarte_aus_daten

    daten = copy.deepcopy(BASIS)
    for pfad, wert in ersetzt.items():
        *weg, letztes = pfad.split("__")
        knoten = daten
        for teil in weg:
            knoten = knoten[int(teil) if isinstance(knoten, list) else teil]
        if wert is None:
            del knoten[int(letztes) if isinstance(knoten, list) else letztes]
        elif isinstance(knoten, list):
            knoten[int(letztes)] = wert
        else:
            knoten[letztes] = wert
    return klickkarte_aus_daten(daten, "Prüfkarte")


def _fehler(**ersetzt) -> str:
    from telco_radar.collect.geraete.klickkarte import KlickkartenFehler

    with pytest.raises(KlickkartenFehler) as fehler:
        _lade(**ersetzt)
    return fehler.value.feld


def test_liste_von_quellen_mit_seitenwerten():
    from telco_radar.collect.geraete.klickkarte import Wertpfad

    karte = _lade(antwort=copy.deepcopy(QUELLEN), seite=SEITE)

    laden, skript, globale = karte.quellen
    assert karte.antwort is laden
    assert (laden.laden, laden.je_klick, laden.erkennung) == (
        True,
        False,
        "data.matrix",
    )
    assert laden.pfade["volumen_gb"] == Wertpfad("data.matrix.0.mb", einheit="mb")
    assert laden.variante["laufzeit"].muster.pattern == r"-(\d+)xhigh"
    assert (skript.skript, skript.start, skript.url_muster) == (
        "script#pageValue",
        True,
        None,
    )
    assert globale.globale == ("hwdVariantsPrices",)
    assert not karte.je_klick
    assert karte.seite["geraet"].parameter == "deviceVariantId"
    assert karte.seite["speicher"].selektor is None


def test_eine_quelle_bleibt_eine_zuordnung():
    karte = _lade()

    assert karte.quellen == (karte.antwort,)
    assert karte.je_klick
    assert karte.antwort.pfade["rate"] == "preis.rate"


def test_seitenwert_einer_dimension_genuegt_als_echo():
    quelle = {"global": "preise", "pfade": {"rate": "preise.p"}}

    karte = _lade(antwort=quelle, seite={"speicher": {"parameter": "size"}})

    assert karte.antwort.globale == ("preise",)
    assert _fehler(antwort=quelle) == "antwort.variante"
    assert _fehler(antwort=[quelle]) == "antwort.0.variante"


@pytest.mark.parametrize(
    ("teil", "wert", "gemeldet"),
    [
        ("skript", "script#x", "antwort.0.skript"),
        ("laden", "ja", "antwort.0.laden"),
        ("erkennung", "data..matrix", "antwort.0.erkennung"),
        ("segment", "(offen", "antwort.0.segment"),
        ("pfade", {"rate": "a[b=1"}, "antwort.0.pfade.rate"),
        ("pfade", {"rate": "p.{farbe}"}, "antwort.0.pfade.rate"),
        (
            "pfade",
            {"rate": {"pfad": "p", "einheit": "pfund"}},
            "antwort.0.pfade.rate.einheit",
        ),
        ("pfade", {"rate": {"pfad": "p", "faktor": 2}}, "antwort.0.pfade.rate.faktor"),
        (
            "variante",
            {"tarif": {"pfad": "t", "einheit": "mb"}},
            "antwort.0.variante.tarif.einheit",
        ),
    ],
)
def test_kaputte_quelle_wirft_mit_punktpfad(teil, wert, gemeldet):
    quellen = copy.deepcopy(QUELLEN)
    quellen[0][teil] = wert

    assert _fehler(antwort=quellen, seite=SEITE) == gemeldet


@pytest.mark.parametrize(
    ("quelle", "gemeldet"),
    [
        ({"pfade": {"rate": "p"}}, "antwort.1.url_muster"),
        ({"skript": "#s", "laden": True, "pfade": {"rate": "p"}}, "antwort.1.laden"),
        (
            {"global": "x", "segment": "/c/(.+)", "pfade": {"rate": "p"}},
            "antwort.1.segment",
        ),
        ({"global": "1x", "pfade": {"rate": "p"}}, "antwort.1.global"),
        ({"global": ["x", ""], "pfade": {"rate": "p"}}, "antwort.1.global.1"),
    ],
)
def test_quelle_braucht_genau_eine_art(quelle, gemeldet):
    assert _fehler(antwort=[QUELLEN[2], quelle]) == gemeldet


@pytest.mark.parametrize(
    ("seite", "gemeldet"),
    [
        ({"Plan": {"parameter": "planId"}}, "seite.Plan"),
        ({"modell": {"parameter": "m"}}, "seite.modell"),
        ({"plan": {"muster": "x"}}, "seite.plan.selektor"),
        ({"plan": {"attribut": "href", "parameter": "p"}}, "seite.plan.attribut"),
        ({"plan": {"selektor": "a", "farbe": "x"}}, "seite.plan.farbe"),
        (["plan"], "seite"),
    ],
)
def test_kaputter_seitenwert_wirft(seite, gemeldet):
    assert _fehler(seite=seite) == gemeldet


def test_zusammenfassung_mit_bereichen_ausschluessen_und_mustern():
    karte = _lade(
        zusammenfassung={
            "selektor": ["#zahlung", "#tarif"],
            "ohne": "#werbung",
            "muster": {
                "rate": r"Gerät mtl\. \(\d+ Raten\):\s*([\d.,]+)",
                "ratenzahl": {
                    "selektor": "input:checked + label",
                    "muster": r"(\d+) Raten",
                },
            },
        }
    )

    lesung = karte.textlesung
    assert lesung.selektoren == ("#zahlung", "#tarif")
    assert lesung.ohne == ("#werbung",)
    assert lesung.muster["rate"].selektor is None
    assert lesung.muster["ratenzahl"].selektor == "input:checked + label"
    assert karte.zusammenfassung == "#zahlung, #tarif"


@pytest.mark.parametrize(
    ("zusammenfassung", "gemeldet"),
    [
        ({"selektor": "#p", "muster": {"preis": "x"}}, "zusammenfassung.muster.preis"),
        (
            {"selektor": "#p", "muster": {"rate": "(offen"}},
            "zusammenfassung.muster.rate",
        ),
        (
            {"selektor": "#p", "muster": {"rate": {"selektor": "#r"}}},
            "zusammenfassung.muster.rate.muster",
        ),
        ({"selektor": ["#p", " "]}, "zusammenfassung.selektor.1"),
        ({"selektor": "#p", "ohne": []}, "zusammenfassung.ohne"),
    ],
)
def test_kaputte_zusammenfassung_wirft(zusammenfassung, gemeldet):
    assert _fehler(zusammenfassung=zusammenfassung) == gemeldet
