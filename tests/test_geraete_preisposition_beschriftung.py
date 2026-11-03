"""Preispositionierung: der Vodafone-Betrag steht je Zeile, ohne Überdeckung.

Der Betrag (größte Schrift der Zeile) ist in der breiten und der schmalen
Ausführung vorhanden und liegt weder auf Nachbarzeile, Lückenhinweis noch Achse.
Die Textboxen werden aus Schriftgröße, Anker und Zeichenzahl geschätzt; die
Schrift selbst lädt in der Cloud nicht (CLAUDE.md der Berichtsseiten).
Die Tests hängen nicht am Datum.
"""

from __future__ import annotations

import re

import pytest
from bs4 import BeautifulSoup

from telco_radar.geraete_model import Geraet, Katalog
from telco_radar.report import geraete_preisposition as pp

M24 = 24
SCHRIFT = {
    "gr-pp-tick": 12.0,
    "gr-pp-name": 15.0,
    "gr-pp-gb": 12.0,
    "gr-pp-summe": 12.0,
    "gr-pp-summe--eigen": 26.0,
    "gr-pp-fehlt": 12.0,
}
BREITE_JE_ZEICHEN = 0.62
HOEHE_JE_SCHRIFT = 0.75


def _karte(anbieter: str, gesamt: float) -> dict:
    return {
        "anbieter": anbieter,
        "band": "m",
        "gesamt": gesamt,
        "vergleichbar": True,
        "belastbar": True,
        "frisch": True,
        "zaehlt": True,
        "naeherung": False,
        "raten_laufzeit": M24,
        "leitzahl_monate": M24,
        "quelle_url": f"https://beispiel.test/{anbieter}?tarif=m",
    }


def _geraete() -> dict:
    """iPhone mit Vodafone mittendrin, Galaxy ohne o2 (Lücke), Pixel mit
    Vodafone nahe am Achsenende."""
    voll = [
        _karte("Vodafone", 1700.0),
        _karte("o2", 1500.0),
        _karte("congstar", 1400.0),
        _karte("1&1", 1900.0),
    ]
    ohne_o2 = [
        _karte("Vodafone", 1563.0),
        _karte("congstar", 1450.0),
        _karte("1&1", 1800.0),
    ]
    am_rand = [
        _karte("Vodafone", 1997.0),
        _karte("o2", 1500.0),
        _karte("congstar", 1400.0),
        _karte("1&1", 1650.0),
    ]
    geraete = [
        Geraet(
            hersteller="Apple", modell="iPhone 18 Pro", generation=18, speicher=[256]
        ),
        Geraet(
            hersteller="Samsung",
            modell="Galaxy S26 Ultra",
            generation=26,
            speicher=[256],
        ),
        Geraet(hersteller="Google", modell="Pixel 11", generation=11, speicher=[128]),
    ]
    ids = [f"{g.device_id}-{g.speicher[0]}" for g in geraete]
    return {
        "katalog_obj": Katalog(geraete=geraete),
        "tco": {
            "baender_katalog": [{"key": "m", "label": "M"}],
            "modelle": [
                {"id": ids[0], "karten": voll},
                {"id": ids[1], "karten": ohne_o2},
                {"id": ids[2], "karten": am_rand},
            ],
        },
    }


def _boxen(svg_html: str) -> list[dict]:
    """Geschätzte Textboxen (x0, x1, y0, y1) mit Klasse, Text und viewBox."""
    svg = BeautifulSoup(svg_html, "html.parser").svg
    breite = float(svg["viewbox"].split()[2])
    aus = []
    for t in svg.find_all("text"):
        klassen = t.get("class") or []
        gross = next(
            (k for k in SCHRIFT if k in klassen and k.endswith("--eigen")), None
        )
        klasse = gross or next((k for k in SCHRIFT if k in klassen), None)
        if klasse is None:
            continue
        text = t.get_text()
        w = len(text) * SCHRIFT[klasse] * BREITE_JE_ZEICHEN
        x = float(t["x"])
        anker = t.get("text-anchor", "start")
        x0 = {"start": x, "middle": x - w / 2, "end": x - w}[anker]
        y = float(t["y"])
        aus.append(
            {
                "klasse": klasse,
                "text": text,
                "x0": x0,
                "x1": x0 + w,
                "y0": y - SCHRIFT[klasse] * HOEHE_JE_SCHRIFT,
                "y1": y,
                "breite": breite,
            }
        )
    return aus


def _ueberdeckt(a: dict, b: dict) -> bool:
    return (
        a["x0"] < b["x1"]
        and b["x0"] < a["x1"]
        and a["y0"] < b["y1"]
        and b["y0"] < a["y1"]
    )


@pytest.fixture(scope="module")
def daten() -> dict:
    return pp.aufbereiten(_geraete())


@pytest.mark.parametrize("ausfuehrung", ["svg_breit", "svg_schmal"])
def test_jede_zeile_nennt_den_vodafone_betrag(daten, ausfuehrung):
    betraege = [
        b["text"] for b in _boxen(daten[ausfuehrung]) if b["klasse"].endswith("--eigen")
    ]
    assert betraege == ["1.700 €", "1.563 €", "1.997 €"]


@pytest.mark.parametrize("ausfuehrung", ["svg_breit", "svg_schmal"])
def test_kein_text_liegt_auf_einem_anderen(daten, ausfuehrung):
    boxen = _boxen(daten[ausfuehrung])
    for i, a in enumerate(boxen):
        for b in boxen[i + 1 :]:
            assert not _ueberdeckt(a, b), (a["text"], b["text"])


@pytest.mark.parametrize("ausfuehrung", ["svg_breit", "svg_schmal"])
def test_kein_text_ragt_aus_dem_bild(daten, ausfuehrung):
    for b in _boxen(daten[ausfuehrung]):
        assert b["x0"] >= 0 and b["x1"] <= b["breite"], b["text"]


def test_der_vodafone_betrag_ist_in_beiden_ausfuehrungen_dieselbe_zahl(daten):
    def zahlen(html):
        return re.findall(
            r"[\d.]+ €",
            " ".join(
                b["text"] for b in _boxen(html) if b["klasse"].endswith("--eigen")
            ),
        )

    assert zahlen(daten["svg_breit"]) == zahlen(daten["svg_schmal"])
