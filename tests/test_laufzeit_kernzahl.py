"""Datenkonzept Geräte, Schritt 2 Teil A: die Kernzahl jeder Karte ist `kosten_ueber`.

Gerechnet wird über H = größerer Wert aus Ratenlaufzeit N und Tarifbindung (12 → 24,
24 → 24, 36 → 36; 1&1 ein Vertrag über 36). Die Karte, die Zeitreihe und der Export
lesen dieselbe Zahl aus `tco_kosten.kosten_ueber`; ein Monat ohne gemessenen
Tarifpreis ist eine benannte Lücke und keine Zahl. Gegenproben: 12 und 24 Raten
tragen weiter dieselbe Zahl wie bisher, 1&1 ebenso.
"""

from __future__ import annotations

import csv
import io

from telco_radar.analyze.tco_buendel import aus_rohsaetzen
from telco_radar.report import geraete_export, geraete_tco_view, geraete_zeitreihe
from telco_radar.report import geraete_tco_karten as karten
from telco_radar.tarif_bezug import Tarifbestand
from telco_radar.tarif_model import Preisphase
from telco_radar.tco_model import POSTEN_TARIF, Buendel, kosten_ueber

HEUTE = "2026-10-06"


def _getrennt(laufzeit: int, rate: float, phasen: bool = True, **kw) -> Buendel:
    """congstar Allnet Flat XS zum iPhone 17 Pro 256 GB: Tarif 15,00 €, 24 Monate
    gebunden; mit Preisphase ohne Ende ist der Preis auch nach Monat 24 belegt."""
    felder = dict(
        sku_id="apple-iphone-17-pro-256gb-silber",
        anbieter="congstar",
        tarif_name="Allnet Flat XS",
        tarif_id="congstar:allnet-flat-xs",
        tarif_monatlich=15.0,
        tarif_bindung_monate=24,
        geraet_zuzahlung=1.0,
        geraet_monatsrate=rate,
        laufzeit_monate=laufzeit,
        anschlusspreis=0.0,
        zustand="neu",
        quelle_url="https://example.de/congstar",
        abgerufen_am=HEUTE,
        tarif_phasen=[Preisphase(1, None, 15.0)] if phasen else [],
    )
    felder.update(kw)
    return Buendel(**felder)


def _karte(b: Buendel) -> dict:
    return karten._karte(b, None, None, None, {}, zustand="neu", heute=HEUTE)


def test_aus_rohsaetzen_reicht_die_tarifbindung_durch():
    bestand = Tarifbestand(
        [
            {
                "tarif_id": "vodafone:vodafone-mobil-s",
                "anbieter": "Vodafone",
                "name": "Vodafone Mobil S",
                "grundgebuehr": 39.95,
            }
        ]
    )
    satz = {
        "anbieter": "Vodafone",
        "tarif_name": "Mobil S",
        "sku_id": "apple-iphone-17-pro-256gb-silber",
        "tarif_monatlich": 39.95,
        "geraet_zuzahlung": 1.0,
        "geraet_monatsrate": 30.0,
        "laufzeit_monate": 36,
        "anschlusspreis": 0.0,
        "tarif_bindung_monate": 24,
    }
    ohne = {k: v for k, v in satz.items() if k != "tarif_bindung_monate"}
    mit_bindung = aus_rohsaetzen([satz], bestand, HEUTE).buendel
    ohne_bindung = aus_rohsaetzen([ohne], bestand, HEUTE).buendel
    assert [b.tarif_bindung_monate for b in mit_bindung] == [24]
    assert [b.tarif_bindung_monate for b in ohne_bindung] == [None]


def test_36_raten_rechnen_36_tarifmonate():
    b = _getrennt(36, 30.5)
    k = _karte(b)
    assert k["gesamt"] == 1639.0 == kosten_ueber(b).gesamt
    assert k["leitzahl_monate"] == 36
    assert k["label"] == "Kosten über 36 Monate"
    assert k["schnitt_monat"] == round(1639.0 / 36, 2)
    assert k["belastbar"]
    assert round(sum(s["betrag"] for s in k["zerlegung"]), 2) == k["gesamt"]
    assert not any(s["offen"] for s in k["zerlegung"])


def test_ohne_preis_ab_monat_25_ist_die_36er_karte_eine_luecke():
    k = _karte(_getrennt(36, 30.5, phasen=False))
    assert k["gesamt"] is None
    assert not k["belastbar"]
    assert k["label"] == "Kosten über 36 Monate"
    assert f"{POSTEN_TARIF} Monat 25–36" in k["luecken"]
    assert "Monat 25–36" in k["leer_grund"]


def test_12_und_24_raten_tragen_weiter_24_monate():
    zwoelf, vierundzwanzig = _getrennt(12, 80.0), _getrennt(24, 41.0)
    assert _karte(zwoelf)["gesamt"] == round(1 + 24 * 15 + 12 * 80.0, 2)
    assert _karte(vierundzwanzig)["gesamt"] == round(1 + 24 * 15 + 24 * 41.0, 2)
    assert {_karte(b)["leitzahl_monate"] for b in (zwoelf, vierundzwanzig)} == {24}


def test_ein_vertrag_rechnet_seinen_betrag_ueber_36_monate():
    b = Buendel(
        sku_id="apple-iphone-17-pro-256gb-silber",
        anbieter="1&1",
        tarif_name="All-Net-Flat S",
        buendel_monatlich=44.99,
        geraet_zuzahlung=360.0,
        laufzeit_monate=36,
        anschlusspreis=39.9,
        zustand="neu",
        abgerufen_am=HEUTE,
    )
    k = _karte(b)
    assert k["gesamt"] == round(360.0 + 39.9 + 36 * 44.99, 2)
    assert k["leitzahl_monate"] == 36


def test_ein_fehlender_anschlusspreis_ist_keine_null():
    k = _karte(_getrennt(24, 41.0, anschlusspreis=None))
    assert k["gesamt"] is None
    assert "Anschlusspreis" in k["leer_grund"]


def test_die_zeitreihe_rechnet_dieselbe_zahl():
    b = _getrennt(36, 30.5)
    satz = {
        "id": b.id,
        "datum": HEUTE,
        "gesamt": 1459.0,
        "tarif_id": b.tarif_id,
        "tarif_monatlich": 15.0,
        "geraet_zuzahlung": 1.0,
        "geraet_monatsrate": 30.5,
        "laufzeit_monate": 36,
        "anschlusspreis": 0.0,
        "abgerufen_am": HEUTE,
    }
    stand = {"sku_id": b.sku_id, "anbieter": "congstar", "tarif_name": b.tarif_name}
    tarife = {
        b.tarif_id: {
            "laufzeit_monate": 24,
            "preisphasen": [{"von_monat": 1, "bis_monat": None, "betrag": 15.0}],
        }
    }
    messung = {"satz": satz, "stand": stand}
    assert geraete_zeitreihe._messwert(messung, tarife) == (1639.0, 36)
    rechnung = geraete_zeitreihe._rechung(messung, tarife)
    assert rechnung["gesamt"] == 1639.0
    assert round(sum(p["betrag"] for p in rechnung["posten"]), 2) == 1639.0


def test_der_export_traegt_dieselbe_zahl():
    b = _getrennt(36, 30.5)
    zeilen = geraete_tco_view._export_zeilen([b], [], [], None, {}, None, HEUTE)
    text, _ = geraete_export.tco_csv(zeilen)
    gelesen = next(csv.DictReader(io.StringIO(text.lstrip("\ufeff")), delimiter=";"))
    assert geraete_export.leitzahl_aus_zeile(gelesen) == "1639,00"
    assert gelesen["Leitzahl-Zeitraum Monate"] == "36"
    assert gelesen["Laufzeit Monate"] == "36"
