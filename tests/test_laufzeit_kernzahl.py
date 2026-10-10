"""Datenkonzept Geräte, Schritt 2 Teil A: die Kernzahl jeder Karte ist `kosten_ueber`.

Gerechnet wird über H = größerer Wert aus Ratenlaufzeit N und Tarifbindung (12 → 24,
24 → 24, 36 → 36; 1&1 ein Vertrag über 36). Die Karte, die Zeitreihe und der Export
lesen dieselbe Zahl aus `tco_kosten.kosten_ueber`. Der Tarif zählt nur seine
Bindung: bei 36 Raten Monat 1 bis 24 Tarif und Rate, Monat 25 bis 36 nur die Rate
(Antonio, 10.10.2026). Gegenproben: 12 und 24 Raten tragen weiter dieselbe Zahl wie
bisher, 1&1 ebenso.

Prüfrunde DK23: für jeden Anbieter gilt dieselbe Regel für die Monate nach der
Bindung. Eine einzige Phase „ab Monat 1, ohne Ende“ (so schreibt der Leser eines
Produktinformationsblatts ohne Phasentabelle den Grundpreis) und eine Tabelle, die
Monat 25 ausdrücklich nennt, ergeben dieselbe 36er-Zahl.
"""

from __future__ import annotations

import csv
import io

from bestand_pfad import lese_wurzel

from telco_radar.analyze.tco_buendel import aus_rohsaetzen
from telco_radar.collect.tarif_pdf import lies_text
from telco_radar.geraete_config import lade_katalog
from telco_radar.report import geraete_export, geraete_tco_view, geraete_zeitreihe
from telco_radar.report import geraete_tco_karten as karten
from telco_radar.tarif_bezug import Tarifbestand
from telco_radar.tarif_model import Preisphase
from telco_radar.tco_model import POSTEN_TARIF, Buendel, kosten_ueber

HEUTE = "2026-10-06"


TABELLE_AB_25 = [Preisphase(1, 24, 15.0), Preisphase(25, None, 15.0)]


def _getrennt(laufzeit: int, rate: float, phasen: bool = True, **kw) -> Buendel:
    """congstar Allnet Flat XS zum iPhone 17 Pro 256 GB: Tarif 15,00 €, 24 Monate
    gebunden; mit einer Phasentabelle, die Monat 25 ausdrücklich nennt
    (`TABELLE_AB_25`), ist der Preis auch nach Monat 24 belegt."""
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
        tarif_phasen=list(TABELLE_AB_25) if phasen else [],
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


def test_36_raten_rechnen_24_tarifmonate():
    """1 + 24 × 15 + 36 × 30,50 = 1.459,00 €: Monat 25 bis 36 nur die Rate."""
    b = _getrennt(36, 30.5)
    k = _karte(b)
    assert k["gesamt"] == 1459.0 == kosten_ueber(b).gesamt
    assert k["leitzahl_monate"] == 36
    assert k["label"] == "Kosten über 36 Monate"
    assert k["schnitt_monat"] == round(1459.0 / 36, 2)
    assert k["belastbar"]
    assert round(sum(s["betrag"] for s in k["zerlegung"]), 2) == k["gesamt"]
    assert not any(s["offen"] for s in k["zerlegung"])


def test_ohne_preis_ab_monat_25_traegt_die_36er_karte_ihre_zahl():
    k = _karte(_getrennt(36, 30.5, phasen=False))
    assert k["gesamt"] == 1459.0
    assert k["belastbar"]
    assert k["label"] == "Kosten über 36 Monate"
    assert f"{POSTEN_TARIF} Monat 25–36" not in k["luecken"]


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
        "gesamt": 1639.0,
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
            "preisphasen": [
                {"von_monat": 1, "bis_monat": 24, "betrag": 15.0},
                {"von_monat": 25, "bis_monat": None, "betrag": 15.0},
            ],
        }
    }
    messung = {"satz": satz, "stand": stand}
    assert geraete_zeitreihe._messwert(messung, tarife) == (1459.0, 36)
    rechnung = geraete_zeitreihe._rechung(messung, tarife)
    assert rechnung["gesamt"] == 1459.0
    assert round(sum(p["betrag"] for p in rechnung["posten"]), 2) == 1459.0


def test_der_export_traegt_dieselbe_zahl():
    b = _getrennt(36, 30.5)
    zeilen = geraete_tco_view._export_zeilen([b], [], [], None, {}, None, HEUTE)
    text, _ = geraete_export.tco_csv(zeilen)
    gelesen = next(csv.DictReader(io.StringIO(text.lstrip("\ufeff")), delimiter=";"))
    assert geraete_export.leitzahl_aus_zeile(gelesen) == "1459,00"
    assert gelesen["Leitzahl-Zeitraum Monate"] == "36"
    assert gelesen["Laufzeit Monate"] == "36"


PIB_OHNE_PHASEN = """Produktinformationsblatt
Anbieter: congstar GmbH
Tarif: Allnet Flat XS mit GB+ (Mobilfunk)
Mindestvertragslaufzeit: 24 Monate
Entgelt Allnet Flat XS mit GB+ (ohne Endgerät) 15,00 € / Monat
"""


def _blatt(anbieter: str, preisphasen: list) -> dict:
    return {
        "anbieter": anbieter,
        "name": "XS",
        "art": "mobilfunk",
        "grundgebuehr": 15.0,
        "preisphasen": preisphasen,
        "laufzeit_monate": 24,
        "datenvolumen_gb": 15,
        "dokument_url": f"https://example.de/{anbieter}/tarife",
        "abgerufen_am": HEUTE,
    }


def _karten_je_anbieter(tarife: dict, laufzeit: int) -> dict:
    """Zwei Bündel, die sich nur im Anbieter unterscheiden, als Karten."""
    buendel = [
        _getrennt(
            laufzeit,
            {12: 80.0, 24: 41.0, 36: 30.5}[laufzeit],
            phasen=False,
            anbieter=anbieter,
            tarif_id=f"{anbieter}:xs",
            quelle_url=f"https://example.de/{anbieter}/{laufzeit}",
        )
        for anbieter in ("congstar", "o2")
    ]
    katalog = lade_katalog(lese_wurzel())
    modelle = karten.modelle(buendel, [], [], tarife, katalog, heute=HEUTE)
    return {
        k["anbieter"]: k
        for m in modelle["modelle"]
        for k in m["karten"]
        if k["anbieter"] in ("congstar", "o2")
    }


def test_dieselbe_auskunft_ergibt_bei_jedem_anbieter_dieselbe_36er_zahl():
    """congstar: das Produktinformationsblatt ohne Phasentabelle, gelesen vom
    PIB-Leser (er schreibt den Grundpreis als Phase „ab Monat 1, ohne Ende“);
    o2: dieselben Angaben ohne Phasen. Beide nennen 15,00 €, 24 Monate Bindung und
    nichts zu Monat 25 bis 36; beide tragen 1.459,00 €. Vorher trug congstar
    1.639,00 €, o2 die Lücke."""
    congstar = lies_text(PIB_OHNE_PHASEN, url="https://example.de/pib").als_dict()
    assert congstar["preisphasen"] == [
        {"von_monat": 1, "bis_monat": None, "betrag": 15.0}
    ], "der Leser speichert sein Format unverändert"
    tarife = {"congstar:xs": congstar, "o2:xs": _blatt("o2", [])}
    sechsunddreissig = _karten_je_anbieter(tarife, 36)
    for anbieter in ("congstar", "o2"):
        k = sechsunddreissig[anbieter]
        assert k["gesamt"] == 1459.0, (anbieter, k["gesamt"])
        assert f"{POSTEN_TARIF} Monat 25–36" not in k["luecken"], k["luecken"]
        assert k["nach_bindung"] is None, (anbieter, k["nach_bindung"])
    assert sechsunddreissig["congstar"]["luecken"] == sechsunddreissig["o2"]["luecken"]
    vierundzwanzig = _karten_je_anbieter(tarife, 24)
    assert {a: k["gesamt"] for a, k in vierundzwanzig.items()} == {
        "congstar": round(1 + 24 * 15 + 24 * 41.0, 2),
        "o2": round(1 + 24 * 15 + 24 * 41.0, 2),
    }


def test_eine_quelle_die_monat_25_nennt_aendert_die_36er_zahl_nicht():
    """Gegenprobe: nennt die Phasentabelle den Preis ab Monat 25 ausdrücklich,
    tragen beide Anbieter dieselbe Zahl über 36 Monate wie ohne Tabelle; die
    Zeile „ab Monat 25“ behält ihren Betrag."""
    tabelle = [
        {"von_monat": 1, "bis_monat": 24, "betrag": 15.0},
        {"von_monat": 25, "bis_monat": None, "betrag": 15.0},
    ]
    tarife = {f"{a}:xs": _blatt(a, tabelle) for a in ("congstar", "o2")}
    karten36 = _karten_je_anbieter(tarife, 36)
    assert {a: k["gesamt"] for a, k in karten36.items()} == {
        "congstar": 1459.0,
        "o2": 1459.0,
    }
    assert {k["nach_bindung"] for k in karten36.values()} == {15.0}
