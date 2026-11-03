"""o2 „… Plus“-Tarife stehen nicht im Vergleich, ihr Preis braucht ein Zweitprodukt.

Preisprüfung 03.11.2026: Der Plus-Preis enthält den o2-Plus-Bundle-Rabatt, der laut
Fußnote nur gilt, wenn binnen 6 Wochen ein zweites Produkt gebucht wird; die Seite
verspricht Preise „ohne Boni“. Die Karte bleibt sichtbar („nur mit Zweitprodukt“),
stellt aber weder Δ noch Sieger noch Spanne, und die Rohsatz-Wege (Katalogzeile,
Abnahme) teilen die Definition. Synthetisch, fester Bezugstag.
"""

from __future__ import annotations

from dataclasses import asdict

import pytest

from telco_radar.analyze import geraete_pruefstatus
from telco_radar.report import geraete_notbremse as notbremse
from telco_radar.report import geraete_tco_karten, geraete_tco_view, geraete_view
from telco_radar.tco_model import Buendel

HEUTE = "2026-11-03"
SKU = "pruefer-phone-256-schwarz"
PLUS = "O2 Mobile on Demand M Plus mit 50 GB+ (24 Mon.)"
REGULAER = "O2 Mobile on Demand M mit 50 GB+ (24 Mon.)"


def _buendel(anbieter: str, tarif_name: str, tarif: float) -> Buendel:
    return Buendel(
        sku_id=SKU,
        anbieter=anbieter,
        tarif_name=tarif_name,
        tarif_monatlich=tarif,
        geraet_zuzahlung=1.0,
        geraet_monatsrate=30.0,
        laufzeit_monate=24,
        anschlusspreis=39.99,
        quelle_url=f"https://example.org/{anbieter}/buendel",
        abgerufen_am=HEUTE,
        zustand="neu",
    )


def _listung(anbieter: str) -> dict:
    return {
        "sku_id": SKU,
        "device_id": "pruefer-phone",
        "speicher_gb": 256,
        "anbieter": anbieter,
        "zustand": "neu",
        "farbe_normalisiert": "schwarz",
        "quelle_url": f"https://example.org/{anbieter}",
        "abgerufen_am": HEUTE,
    }


def _karte(modell: dict, anbieter: str) -> dict:
    return next(k for k in modell["karten"] if k["anbieter"] == anbieter)


def _modell_ueber_speicher(o2_name: str, vodafone_name: str = "Red M") -> dict:
    """Die Seite liest Bündel als Speichersätze (``geraete_tco_view``)."""
    saetze = [
        asdict(_buendel("Vodafone", vodafone_name, 30.0)),
        asdict(_buendel("o2", o2_name, 20.0)),
    ]
    listungen = [_listung("Vodafone"), _listung("o2")]
    erg = geraete_tco_view.aufbereiten(saetze, [], listungen, katalog=None, heute=HEUTE)
    assert len(erg["modelle"]) == 1, erg["modelle"]
    return erg["modelle"][0]


def test_plus_tarif_zaehlt_nicht_und_nennt_den_grund():
    modell = _modell_ueber_speicher(PLUS)
    o2, vodafone = _karte(modell, "o2"), _karte(modell, "Vodafone")
    assert o2["zaehlt"] is False
    assert o2["delta"] is None, o2["delta"]
    assert o2["notbremse"]["kurz"] == "nur mit Zweitprodukt"
    assert "zweites Produkt" in o2["notbremse"]["satz"]
    assert modell["spanne"] == [vodafone["gesamt"]] * 2, modell["spanne"]
    assert modell["antwort"]["tarif_gesamt"] == vodafone["gesamt"]


def test_gegengegenprobe_regulaerer_tarif_zaehlt_mit_delta():
    modell = _modell_ueber_speicher(REGULAER)
    o2, vodafone = _karte(modell, "o2"), _karte(modell, "Vodafone")
    assert o2["zaehlt"] is True
    assert o2["notbremse"] is None
    assert o2["delta"]["betrag"] == round(o2["gesamt"] - vodafone["gesamt"], 2)
    assert modell["spanne"] == [o2["gesamt"], vodafone["gesamt"]]


def test_plus_im_namen_eines_anderen_anbieters_ist_kein_zweitprodukt_tarif():
    """Das Merkmal gilt je Anbieter (``GERAETETARIF_MERKMAL``), nicht für das Wort."""
    modell = _modell_ueber_speicher(REGULAER, vodafone_name="GigaMobil Plus")
    vodafone = _karte(modell, "Vodafone")
    assert vodafone["zaehlt"] is True and vodafone["notbremse"] is None


@pytest.mark.parametrize(
    "name,bedingt",
    [
        ("O2 Mobile Unlimited M Plus mit 100 MBit/s (24 Mon.)", True),
        ("O2 Mobile L Plus mit 150 GB+", True),
        ("O2 Mobile Unlimited M mit 100 MBit/s", False),
        ("O2 Mobile Pluspaket", False),
        ("", False),
    ],
)
def test_merkmal_ist_das_wort_plus_im_o2_tarifnamen(name, bedingt):
    assert geraete_pruefstatus.ist_bedingter_tarif("o2", name) is bedingt
    assert geraete_pruefstatus.ist_bedingter_tarif("Vodafone", name) is False


def test_buendelobjekt_und_rohsatz_teilen_die_definition():
    for name, zaehlt in ((PLUS, False), (REGULAER, True)):
        b = _buendel("o2", name, 20.0)
        assert notbremse.zaehlt(notbremse.felder(b, HEUTE)) is zaehlt
        satz = asdict(b)
        assert notbremse.zaehlt(notbremse.felder_aus_satz(satz, HEUTE)) is zaehlt
        assert geraete_pruefstatus.satz_zaehlt(satz, HEUTE) is zaehlt


def _katalogzeile(o2_name: str) -> dict:
    listungen = [
        {**_listung(a), "preis_ohne_vertrag": None, "zuzahlung": None}
        for a in ("o2", "congstar")
    ]
    o2 = {**asdict(_buendel("o2", o2_name, 20.0))}
    congstar = {**asdict(_buendel("congstar", "Allnet M", 25.0))}
    zeilen = geraete_view.katalog_modellzeilen(
        listungen, None, tco_modelle=None, buendel=[o2, congstar], heute=HEUTE
    )
    assert len(zeilen) == 1, zeilen
    return zeilen[0]


def test_katalogzeile_nimmt_kein_plus_buendel_als_guenstigstes():
    assert _katalogzeile(PLUS)["buendel_anbieter"] == "congstar"
    assert _katalogzeile(REGULAER)["buendel_anbieter"] == "o2"


def test_karten_aus_buendelobjekten_sperren_plus_ebenso():
    erg = geraete_tco_karten.modelle(
        [_buendel("Vodafone", "Red M", 30.0), _buendel("o2", PLUS, 20.0)],
        [_listung("Vodafone"), _listung("o2")],
        [],
        {},
        None,
        heute=HEUTE,
    )
    assert _karte(erg["modelle"][0], "o2")["zaehlt"] is False
