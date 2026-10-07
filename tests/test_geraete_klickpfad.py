"""Pfadsprache der Klick-Karte und Lesung der Antwort mit Filtern, Einheiten, Mustern.

Erkundung vom 07.10.2026: feste Listenstellen lesen bei o2, congstar und Vodafone nur
zufällig die gewählte Variante; o2 nennt Volumen in MB mit -1 für unbegrenzt, die
Laufzeit nur als „24xhigh“ und die Variante nur im Base64-Pfadsegment; 1&1 hält
Preise in Cent unter Schlüsseln aus Farbe und Speicher. Alle Daten hier sind Beispiele.
"""

from __future__ import annotations

import base64
import math
import re

import pytest

from telco_radar.collect.geraete.klickkarte import Antwortmuster, Wertpfad
from telco_radar.collect.geraete.klickpfad import am_pfad, pfadfehler, vergleichbar

ATOMICS = {
    "atomics": [
        {
            "capacity": {"sortValue": 262144},
            "color": "Blau",
            "composition": [
                {"financingDuration": 36, "rate": 33.0},
                {"financingDuration": 24, "rate": 49.5},
            ],
        },
        {
            "capacity": {"sortValue": 524288},
            "color": "Blau",
            "composition": [{"financingDuration": 36, "rate": 40.0}],
        },
        {
            "capacity": {"sortValue": 524288},
            "color": "Orange",
            "composition": [{"financingDuration": 36, "rate": 40.0}],
        },
        {
            "capacity": {"sortValue": 262144},
            "color": "Orange",
            "composition": [{"financingDuration": 36, "rate": 34.0}],
        },
    ]
}


@pytest.mark.parametrize(
    ("pfad", "platz", "erwartet"),
    [
        (
            "atomics[capacity.sortValue={speicher}][color={farbe}]"
            ".composition[financingDuration={laufzeit}].rate",
            {"speicher": "262144", "farbe": "blau", "laufzeit": "24"},
            49.5,
        ),
        (
            "atomics[capacity.sortValue={speicher}].composition[financingDuration=36].rate",
            {"speicher": "524288"},
            40.0,
        ),
        ("atomics.1.composition.0.rate", {}, 40.0),
        ("atomics.*.capacity.sortValue", {}, None),
        ("atomics[capacity.sortValue=262144].composition.0.rate", {}, None),
        ("atomics[color={farbe}].color", {}, None),
        ("atomics[color=Grün].color", {}, None),
        ("atomics.9.color", {}, None),
    ],
)
def test_filter_platzhalter_und_mehrdeutigkeit(pfad, platz, erwartet):
    assert am_pfad(ATOMICS, pfad, platz) == erwartet


def test_filter_vergleicht_wahrheitswerte_zahlen_und_text_ohne_leerraum():
    daten = {
        "optionen": [{"selected": False, "name": "A"}, {"selected": True, "name": "B"}]
    }

    assert am_pfad(daten, "optionen[selected=true].name") == "B"
    assert am_pfad({"l": [{"n": 36.0, "w": 1}]}, "l[n=36].w") == 1
    assert am_pfad({"l": [{"n": " Allnet  M", "w": 2}]}, "l[n=allnetm].w") == 2
    assert vergleichbar("O<sub>2</sub> Mobile S") == "o2mobiles"
    assert vergleichbar({"a": 1}) is None


def test_platzhalter_im_schluessel():
    daten = {"preise": {"product-SCHWARZ-256": [5199], "product-SCHWARZ-128": [4499]}}

    platz = {"farbe": "SCHWARZ", "speicher": "256"}
    assert am_pfad(daten, "preise.product-{farbe}-{speicher}.0", platz) == 5199
    assert am_pfad(daten, "preise.product-{farbe}-{speicher}.0", {"farbe": "X"}) is None


@pytest.mark.parametrize(
    ("pfad", "fehler"),
    [
        ("a..b", "leerer oder falsch geformter Schritt „“"),
        ("a[b=1", "Klammern passen nicht"),
        ("a[=1].b", "leerer oder falsch geformter Schritt „a[=1]“"),
        ("a[b.=1]", "leerer oder falsch geformter Schritt „“"),
    ],
)
def test_kaputter_pfad_nennt_den_grund(pfad, fehler):
    assert pfadfehler(pfad) == fehler


def test_gueltige_pfade_haben_keinen_fehler():
    for pfad in ("preis.rate", "tarif.phasen.0.betrag", "a[b.c={x}][d=1].*.e", "[s=1]"):
        assert pfadfehler(pfad) is None


def _muster(**teile) -> Antwortmuster:
    grund = {
        "url_muster": re.compile("/c/"),
        "pfade": {},
        "variante": {},
        "parameter": {},
    }
    grund.update(teile)
    return Antwortmuster(**grund)


def test_einheiten_cent_und_mb_und_minus_eins_ist_unbegrenzt():
    from telco_radar.collect.geraete.klickecho import lies_antwort

    muster = _muster(
        pfade={
            "rate": Wertpfad("p.0", einheit="cent"),
            "volumen_gb": Wertpfad("t[sel=true].mb", einheit="mb"),
        }
    )
    begrenzt = {
        "p": [4499],
        "t": [{"sel": True, "mb": "153600"}, {"sel": False, "mb": 1}],
    }
    offen = {"p": [5199], "t": [{"sel": True, "mb": -1}]}

    assert lies_antwort(begrenzt, muster).werte.rate == 44.99
    assert lies_antwort(begrenzt, muster).werte.volumen_gb == 150.0
    assert lies_antwort(offen, muster).werte.volumen_gb == math.inf
    assert (
        lies_antwort({"p": [4499]}, _muster(pfade={"rate": "p.0"})).werte.rate == 4499
    )


def test_variante_aus_base64_segment_mit_muster_und_ohne_markup():
    from telco_radar.collect.geraete.klickecho import lies_antwort

    roh = "type=B;hardware=x-geraet-512gb-blau-24xhigh;tariff=x-mobile-m"
    segment = base64.urlsafe_b64encode(roh.encode()).decode().rstrip("=")
    muster = _muster(
        segment=re.compile(r"/c/([^/?#]+)"),
        parameter={
            "speicher": Wertpfad("hardware", re.compile(r"-(\d+gb)-")),
            "laufzeit": Wertpfad("hardware", re.compile(r"-(\d+)xhigh")),
        },
        variante={"tarif": "tarif.name"},
    )
    nutzlast = {"tarif": {"name": "O<sub>2</sub> Mobile M"}}

    lesung = lies_antwort(nutzlast, muster, f"https://b.invalid/c/{segment}")

    assert dict(lesung.variante) == {
        "speicher": "512gb",
        "laufzeit": 24,
        "tarif": "O2 Mobile M",
    }
    ohne = lies_antwort(nutzlast, _muster(parameter=muster.parameter), "/c/x")
    assert ohne.variante["laufzeit"] is None


def test_echo_vergleicht_optionen_ohne_leerraum_und_gross_klein():
    from telco_radar.collect.geraete.klickecho import (
        Antwortlesung,
        Preiswerte,
        Variante,
        pruefe_echo,
    )

    gewaehlt = Variante("512 GB", "O2 Mobile M", 24)
    werte = Preiswerte(rate=10.0)
    gleich = Antwortlesung(werte, {"speicher": "512gb", "tarif": "o2 mobile m"})
    anders = Antwortlesung(werte, {"speicher": "256gb"})

    assert pruefe_echo(gewaehlt, gewaehlt, werte, gleich).stimmt
    befunde = pruefe_echo(gewaehlt, gewaehlt, werte, anders).befunde
    assert [b.grund for b in befunde] == ["Antwort nennt 256gb statt 512 GB"]
