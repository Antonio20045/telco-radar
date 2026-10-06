"""Notbremse nach der Prüfstelle: nur ein gültiges Bündel stellt Sieger, Spanne und Δ.

Datenkonzept Geräteradar, Schritt 7: Quarantäne, veraltet und eine gescheiterte
Prüfung (``unbekannt``) zählen nicht; die Karte nennt den Zustand mit der Regel aus
dem gespeicherten Vermerk (``"quarantaene 3"``). Ein
Bündel ohne Feld ``pruefung`` ist nie geprüft worden und zählt wie vor der
Prüfstelle. Synthetisch über die öffentlichen Eingänge
``geraete_tco_karten.modelle`` (Bündelobjekte) und
``geraete_view.katalog_modellzeilen`` (Rohsätze); fester Bezugstag.
"""

from __future__ import annotations

from dataclasses import asdict

import pytest

from telco_radar.report import geraete_notbremse as notbremse
from telco_radar.report import geraete_tco_karten, geraete_tco_view, geraete_view
from telco_radar.tco_model import Buendel

HEUTE = "2026-10-03"
SKU = "pruefer-phone-128-schwarz"
GRUND = "Regel 3: Tarif zum SIM-only-Preis."


def _pruefung(status: str) -> str:
    """Der gespeicherte Vermerk: Status und verletzte Regel, sonst der Fehler."""
    if status == "unbekannt":
        return "unbekannt RuntimeError: kaputt"
    return status if status == "gueltig" else f"{status} 3"


def _buendel(anbieter: str, tarif: float, pruefung: str | None = None) -> Buendel:
    return Buendel(
        sku_id=SKU,
        anbieter=anbieter,
        tarif_name=f"{anbieter} M",
        tarif_monatlich=tarif,
        geraet_zuzahlung=1.0,
        geraet_monatsrate=30.0,
        laufzeit_monate=24,
        anschlusspreis=39.99,
        quelle_url=f"https://example.org/{anbieter}/buendel",
        abgerufen_am=HEUTE,
        zustand="neu",
        pruefung=pruefung,
    )


def _listung(anbieter: str) -> dict:
    return {
        "sku_id": SKU,
        "device_id": "pruefer-phone",
        "speicher_gb": 128,
        "anbieter": anbieter,
        "zustand": "neu",
        "farbe_normalisiert": "schwarz",
        "quelle_url": f"https://example.org/{anbieter}",
        "abgerufen_am": HEUTE,
    }


def _modell(o2: str | None) -> dict:
    buendel = [_buendel("Vodafone", 30.0), _buendel("o2", 20.0, o2)]
    listungen = [_listung("Vodafone"), _listung("o2")]
    erg = geraete_tco_karten.modelle(buendel, listungen, [], {}, None, heute=HEUTE)
    assert len(erg["modelle"]) == 1, erg["modelle"]
    return erg["modelle"][0]


def _karte(modell: dict, anbieter: str) -> dict:
    return next(k for k in modell["karten"] if k["anbieter"] == anbieter)


GESPERRT = {
    "quarantaene": ("Quarantäne", "verletzt eine Prüfregel"),
    "veraltet": ("veraltet", "ist veraltet"),
    "unbekannt": ("Prüfung gescheitert", "Prüfung dieses Preises ist gescheitert"),
}


@pytest.mark.parametrize("status", sorted(GESPERRT))
def test_gesperrtes_buendel_stellt_weder_sieger_noch_delta(status):
    modell = _modell(_pruefung(status))
    o2, vodafone = _karte(modell, "o2"), _karte(modell, "Vodafone")
    assert o2["delta"] is None, o2["delta"]
    assert modell["spanne"] == [vodafone["gesamt"]] * 2, modell["spanne"]
    assert modell["antwort"]["tarif_gesamt"] == vodafone["gesamt"]
    kurz, satz = GESPERRT[status]
    assert o2["notbremse"]["kurz"] == kurz
    assert satz in o2["notbremse"]["satz"]
    if status != "unbekannt":
        assert GRUND in o2["notbremse"]["satz"], "die Karte nennt die Regel"
    else:
        assert "Regel" not in o2["notbremse"]["satz"], "gescheitert: keine Regel"


@pytest.mark.parametrize(
    "pruefung", [_pruefung("gueltig"), None], ids=["gueltig", "nie"]
)
def test_gegenprobe_gueltiges_und_nie_geprueftes_buendel_zaehlen(pruefung):
    modell = _modell(pruefung)
    o2, vodafone = _karte(modell, "o2"), _karte(modell, "Vodafone")
    assert o2["delta"]["betrag"] == round(o2["gesamt"] - vodafone["gesamt"], 2)
    assert o2["delta"]["betrag"] == -240.0, "24 Monate × 10 € Tarif"
    assert modell["spanne"] == [o2["gesamt"], vodafone["gesamt"]]
    assert modell["antwort"]["tarif_gesamt"] == o2["gesamt"]
    assert o2["notbremse"] is None


@pytest.mark.parametrize(
    "status,zaehlt",
    [("gueltig", True), ("quarantaene", False), ("veraltet", False), ("x", False)],
)
def test_zaehlt_nur_mit_status_gueltig(status, zaehlt):
    felder = notbremse.felder(_buendel("o2", 20.0, _pruefung(status)), HEUTE)
    assert notbremse.zaehlt(felder) is zaehlt
    satz = notbremse.felder_aus_satz({"pruefung": _pruefung(status)}, HEUTE)
    assert notbremse.zaehlt(satz) is zaehlt, "Objekt und Rohsatz: eine Definition"


def _rohsatz(anbieter: str, tarif: float, pruefung: str | None) -> dict:
    satz = {
        "sku_id": SKU,
        "anbieter": anbieter,
        "tarif_name": f"{anbieter} M",
        "tarif_monatlich": tarif,
        "geraet_monatsrate": 30.0,
        "laufzeit_monate": 24,
        "quelle_url": f"https://example.org/{anbieter}/buendel",
        "abgerufen_am": HEUTE,
    }
    return satz if pruefung is None else {**satz, "pruefung": pruefung}


def _katalogzeile(pruefung: str | None) -> dict:
    listungen = [
        {**_listung(a), "preis_ohne_vertrag": None, "zuzahlung": None}
        for a in ("o2", "congstar")
    ]
    zeilen = geraete_view.katalog_modellzeilen(
        listungen,
        None,
        tco_modelle=None,
        buendel=[_rohsatz("o2", 20.0, pruefung), _rohsatz("congstar", 25.0, None)],
        heute=HEUTE,
    )
    assert len(zeilen) == 1, zeilen
    return zeilen[0]


def test_katalogzeile_nimmt_kein_buendel_in_quarantaene():
    z = _katalogzeile(_pruefung("quarantaene"))
    assert (z["buendel_anbieter"], z["buendel_monat"]) == ("congstar", 55.0), z
    gegen = _katalogzeile(_pruefung("gueltig"))
    assert (gegen["buendel_anbieter"], gegen["buendel_monat"]) == ("o2", 50.0), gegen


def _ueber_den_speicher(pruefung: str) -> dict:
    """Die Karte des o2-Bündels, gelesen wie die Seite: als Speichersatz."""
    saetze = [
        asdict(_buendel("Vodafone", 30.0)),
        asdict(_buendel("o2", 20.0, pruefung)),
    ]
    listungen = [_listung("Vodafone"), _listung("o2")]
    erg = geraete_tco_view.aufbereiten(saetze, [], listungen, katalog=None, heute=HEUTE)
    return _karte(erg["modelle"][0], "o2")


@pytest.mark.parametrize("status", sorted(GESPERRT))
def test_vermerk_kommt_ueber_den_speicherweg_bis_zur_karte(status):
    """Die Seite liest Bündel als Speichersätze (``geraete_tco_view``): der Vermerk
    muss diesen Weg überleben, sonst stellt ein Bündel in Quarantäne doch den
    Sieger."""
    o2 = _ueber_den_speicher(_pruefung(status))
    assert o2["delta"] is None
    assert o2["notbremse"]["kurz"] == GESPERRT[status][0]


def test_gegenprobe_gueltiger_vermerk_ueber_den_speicherweg_behaelt_delta():
    assert _ueber_den_speicher(_pruefung("gueltig"))["delta"]["betrag"] == -240.0
