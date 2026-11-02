"""Preispositionierung (Geräteseite, ganz oben): jeder Punkt ist die TCO-Zahl.

Die Achse ist `gesamt` der Karte, die die Seite als Zeile des Bandes M bei 24
Raten führt (`geraete_zeitreihe._band_zeilen`). Veraltete Preise, Schätzungen
und die Vodafone-Näherung bekommen keinen Punkt; ein Anbieter ohne Preis ist
eine benannte Lücke, nie ein Punkt bei 0. Die Tests hängen nicht am Datum.
"""

from __future__ import annotations

from pathlib import Path

import jinja2
import test_geraete_tco_zustand
from bs4 import BeautifulSoup

from telco_radar.geraete_model import Geraet, Katalog
from telco_radar.report import geraete_preisposition as pp
from telco_radar.report import geraete_zeitreihe

VORLAGEN = Path(pp.__file__).parent / "templates"
M24 = 24


def _geraet(modell: str, generation: int, hersteller: str = "Apple") -> Geraet:
    return Geraet(
        hersteller=hersteller, modell=modell, generation=generation, speicher=[256, 512]
    )


def _karte(anbieter: str, gesamt, **mehr) -> dict:
    karte = {
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
    }
    karte.update(mehr)
    return karte


def _geraete(karten: list[dict], zweites: list[dict] | None = None) -> dict:
    """Eine Zeile (iPhone 18 Pro); mit `zweites` eine zweite (iPhone 18)."""
    modelle = [{"id": "apple-iphone-18-pro-256", "karten": karten}]
    geraete = [_geraet("iPhone 18 Pro", 18)]
    if zweites is not None:
        modelle.append({"id": "apple-iphone-18-256", "karten": zweites})
        geraete.append(_geraet("iPhone 18", 18))
    return {
        "katalog_obj": Katalog(geraete=geraete),
        "tco": {
            "baender_katalog": [{"key": "m", "label": "M"}],
            "modelle": modelle,
        },
    }


KARTEN = [
    _karte("Vodafone", 2157.4),
    _karte("o2", 2087.75),
    _karte("congstar", 1867.0),
    _karte("1&1", 1890.66),
]


def _punkte(daten: dict, breit: bool = True) -> dict[str, float]:
    svg = BeautifulSoup(daten["svg_breit" if breit else "svg_schmal"], "html.parser")
    return {
        p["data-anbieter"]: float(p["data-wert"]) for p in svg.select(".gr-pp-punkt")
    }


def test_jeder_punkt_ist_die_tco_zahl_der_seite():
    geraete = _geraete(KARTEN)
    daten = pp.aufbereiten(geraete)
    seite = {
        k["anbieter"]: k["gesamt"]
        for k in geraete_zeitreihe._band_zeilen(geraete["tco"]["modelle"][0], M24)["m"][
            "zeilen"
        ]
    }
    assert seite == {
        "Vodafone": 2157.4,
        "o2": 2087.75,
        "congstar": 1867.0,
        "1&1": 1890.66,
    }
    for breit in (True, False):
        assert _punkte(daten, breit) == seite


def test_ein_punkt_liegt_an_der_stelle_seiner_zahl_auf_der_achse():
    daten = pp.aufbereiten(_geraete(KARTEN))
    ach = daten["achse"]
    assert ach["von"] <= 1867.0 and ach["bis"] >= 2157.4
    svg = BeautifulSoup(daten["svg_breit"], "html.parser")
    for p in svg.select(".gr-pp-punkt"):
        erwartet = pp.BREIT["x0"] + (float(p["data-wert"]) - ach["von"]) / (
            ach["bis"] - ach["von"]
        ) * (pp.BREIT["x1"] - pp.BREIT["x0"])
        assert abs(float(p["data-x"]) - erwartet) < 0.1


def test_veraltete_preise_schaetzungen_und_die_naeherung_fehlen():
    """Gegenprobe: dieselben Karten, aber drei davon unzulässig."""
    karten = [
        *KARTEN,
        _karte("Telekom", 999.0, frisch=False),
        _karte("congstar", 700.0, zaehlt=False, schaetzung=True),
        _karte("o2", None),
    ]
    daten = pp.aufbereiten(_geraete(karten))
    assert _punkte(daten) == {
        "Vodafone": 2157.4,
        "o2": 2087.75,
        "congstar": 1867.0,
        "1&1": 1890.66,
    }
    assert "Telekom" not in _punkte(daten)
    assert 999.0 not in _punkte(daten).values()
    assert 0 not in _punkte(daten).values()
    assert daten["achse"]["von"] > 999


def test_die_vodafone_naeherung_ist_kein_punkt():
    """Ohne eigenes Bündel steht die Näherung als Maßstab im Band, nicht im Bild."""
    karten = [k for k in KARTEN if k["anbieter"] != "Vodafone"]
    karten.append(_karte("Vodafone", 500.0, naeherung=True))
    daten = pp.aufbereiten(_geraete(karten))
    assert "Vodafone" not in _punkte(daten)
    assert 500.0 not in _punkte(daten).values()


def test_nur_die_ansicht_24_raten_zaehlt():
    karten = [*KARTEN, _karte("Telekom", 1500.0, raten_laufzeit=36, leitzahl_monate=36)]
    assert "Telekom" not in _punkte(pp.aufbereiten(_geraete(karten)))


def test_ein_anbieter_ohne_preis_ist_eine_benannte_luecke():
    """Telekom hat nur in der zweiten Zeile einen Preis: in der ersten steht
    die Lücke benannt, nie ein Punkt bei 0."""
    daten = pp.aufbereiten(_geraete(KARTEN, [*KARTEN, _karte("Telekom", 2300.0)]))
    zeilen = {z["name"]: z for z in daten["zeilen"]}
    ohne, mit = zeilen["iPhone 18 Pro"], zeilen["iPhone 18"]
    assert ohne["luecken"] == ["Telekom"] and mit["luecken"] == []
    assert "Telekom" not in {p["anbieter"] for p in ohne["punkte"]}
    assert 0 not in _punkte(daten).values()


def test_fehlt_ein_anbieter_in_jeder_zeile_steht_das_einmal_in_der_legende():
    daten = pp.aufbereiten(_geraete(KARTEN))
    fehlt = {e["name"]: e["fehlt"] for e in daten["legende"]}
    assert fehlt["Telekom"] == pp.FEHLT_TEXT
    assert fehlt["Vodafone"] == ""
    assert daten["zeilen"][0]["luecken"] == []


def test_ohne_geprueften_preis_nennt_die_seite_den_zustand():
    daten = pp.aufbereiten(_geraete([_karte("Telekom", 900.0, frisch=False)]))
    assert daten["leer"] is True and not daten["zeilen"]
    html = _vorlage({**_geraete([]), "preisposition": daten})
    assert "Kein geprüfter Preis" in html
    assert "<svg" not in html


def test_ein_ausfall_der_aufbereitung_steht_auf_der_seite():
    daten = pp.ergaenze({"tco": {"modelle": "kaputt"}, "katalog_obj": None})
    assert daten["preisposition"]["fehler"]
    html = _vorlage(daten)
    text = BeautifulSoup(html, "html.parser").get_text()
    assert "nicht verfügbar" in html and daten["preisposition"]["fehler"] in text


def _vorlage(geraete: dict) -> str:
    env = jinja2.Environment(loader=jinja2.FileSystemLoader(VORLAGEN), autoescape=True)
    return env.get_template("_geraete_preisposition.html.j2").render(geraete=geraete)


def test_die_vorlage_zeichnet_beide_ausfuehrungen_mit_denselben_zahlen():
    geraete = pp.ergaenze(_geraete(KARTEN))
    seite = BeautifulSoup(_vorlage(geraete), "html.parser")
    breit = seite.select(".gr-pp-breit .gr-pp-punkt")
    schmal = seite.select(".gr-pp-schmal .gr-pp-punkt")
    assert len(breit) == len(schmal) == len(KARTEN)
    assert sorted(p["data-wert"] for p in breit) == sorted(
        p["data-wert"] for p in schmal
    )
    assert len(seite.select(".gr-pp-legende li")) == len(pp.ANBIETER_FOLGE)
    assert seite.select_one("script") is None and "http" not in str(seite)


def test_die_geraeteseite_traegt_den_abschnitt(tmp_path):
    """Im Ganzen: render_site bindet ihn ein; mit dem Fixture der Seite."""
    seite = test_geraete_tco_zustand._baue(tmp_path)
    abschnitt = seite.select_one("#preisposition")
    assert abschnitt is not None
    assert "gx-art--tarif" in abschnitt["class"]
    punkte = abschnitt.select(".gr-pp-breit .gr-pp-punkt")
    assert punkte and all(float(p["data-wert"]) > 0 for p in punkte)
