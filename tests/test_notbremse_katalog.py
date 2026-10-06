"""Notbremse in der Katalog-Modellzeile: „nur im Bündel, ab X €/Monat“ zählt.

Die Bündel-Angabe ist ein Günstigst-Wert und nimmt nur Bündel, die zählen
(Clean Code 1 und 7: dieselbe Menge wie Sieger, Spanne und bestes Bündel).

Synthetischer Bestand über den öffentlichen Eingang ``katalog_modellzeilen``;
fester Bezugstag, nie das heutige Datum.
"""

from __future__ import annotations

from telco_radar.report import geraete_view

HEUTE = "2026-10-03"
SKU = "pruefer-geraet-128-schwarz"


def _listung(anbieter: str) -> dict:
    return {
        "sku_id": SKU,
        "device_id": "pruefer-geraet",
        "speicher_gb": 128,
        "anbieter": anbieter,
        "zustand": "neu",
        "preis_ohne_vertrag": None,
        "zuzahlung": None,
        "quelle_url": f"https://example.org/{anbieter}",
        "abgerufen_am": HEUTE,
    }


def _buendel(anbieter: str, tarif: float, rate: float, **extra) -> dict:
    return {
        "sku_id": SKU,
        "anbieter": anbieter,
        "tarif_name": f"{anbieter} Tarif",
        "tarif_monatlich": tarif,
        "geraet_monatsrate": rate,
        "laufzeit_monate": 24,
        "quelle_url": f"https://example.org/{anbieter}/buendel",
        "abgerufen_am": HEUTE,
        **extra,
    }


def _zeile(buendel: list) -> dict:
    zeilen = geraete_view.katalog_modellzeilen(
        [_listung("o2"), _listung("congstar")],
        None,
        tco_modelle=None,
        buendel=buendel,
        heute=HEUTE,
    )
    assert len(zeilen) == 1, zeilen
    return zeilen[0]


def test_bundel_angabe_nimmt_keine_schaetzung():
    z = _zeile(
        [
            _buendel("o2", 10.0, 20.0, herleitung="tarifsumme_minus_geraeterate"),
            _buendel("congstar", 15.0, 25.0),
        ]
    )
    assert z["nur_buendel"], z
    assert (z["buendel_anbieter"], z["buendel_monat"]) == ("congstar", 40.0), (
        f"„nur im Bündel, ab {z['buendel_monat']} €/Monat bei "
        f"{z['buendel_anbieter']}“ - erwartet das gemessene congstar-Bündel "
        f"(40,00 €), nicht die o2-Schätzung (30,00 €)"
    )


def test_bundel_angabe_nimmt_keine_abgelaufene_aktion():
    aktion = {
        "art": "anschluss_erlassen",
        "bedingung": "Online-Aktion",
        "quelle_url": "https://example.org/congstar/aktion",
        "eingerechnet": True,
        "gueltig_bis": "2026-09-29",
    }
    z = _zeile(
        [
            _buendel("congstar", 5.0, 20.0, aktionen=[aktion]),
            _buendel("o2", 15.0, 25.0),
        ]
    )
    assert (z["buendel_anbieter"], z["buendel_monat"]) == ("o2", 40.0), (
        f"„ab {z['buendel_monat']} €/Monat bei {z['buendel_anbieter']}“ - "
        f"erwartet o2 (40,00 €), nicht congstar mit abgelaufener Aktion"
    )


def test_gegenprobe_gemessenes_guenstigstes_buendel_bleibt():
    z = _zeile([_buendel("o2", 10.0, 20.0), _buendel("congstar", 15.0, 25.0)])
    assert (z["buendel_anbieter"], z["buendel_monat"]) == ("o2", 30.0), z
