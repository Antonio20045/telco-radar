"""Welcher Preis bekommt das Belegbild, und was kostete dasselbe vorher?

Zahlen von Hand gerechnet: Tarif 30 € x 24 + Rate 20 € x 24 + Zuzahlung = Gesamtkosten.
"""

from __future__ import annotations

from telco_radar.analyze.beleg_schluessel import (
    GRUND_OHNE_BELEG,
    GRUND_OHNE_GERAET,
    ordne_zu,
    vorher_je_geraet,
)


def satz(tarif=30.0, zuzahlung=100.0, rate=20.0, **extra) -> dict:
    daten = {
        "sku_id": "sku-1",
        "anbieter": "Telekom",
        "tarif_name": "M",
        "tarif_monatlich": tarif,
        "tarif_bindung_monate": 24,
        "geraet_zuzahlung": zuzahlung,
        "geraet_monatsrate": rate,
        "laufzeit_monate": 24,
        "anschlusspreis": 0.0,
        "pruefung": "gueltig",
    }
    daten.update(extra)
    return daten


def roh(beleg_id="b1", **extra) -> dict:
    daten = satz(**extra)
    daten.update(device_id="iphone-17", speicher_gb=256, beleg_id=beleg_id)
    return daten


def geraet(sku: str):
    return ("iphone-17", 256) if sku == "sku-1" else ("", None)


def test_gesamtkosten_wie_von_hand_gerechnet():
    vorher = vorher_je_geraet([satz()], geraet)
    assert vorher == {("iphone-17", 256, "Telekom"): 1300.0}


def test_vorher_ist_der_niedrigste_gueltige_wert():
    bestand = [satz(), satz(tarif=25.0), satz(tarif=10.0, pruefung="abweichend")]
    assert vorher_je_geraet(bestand, geraet) == {("iphone-17", 256, "Telekom"): 1180.0}


def test_vorher_ignoriert_unbekannte_geraete_und_ungueltiges():
    bestand = [satz(sku_id="fremd"), satz(pruefung="abweichend")]
    assert vorher_je_geraet(bestand, geraet) == {}


def test_billigster_rohsatz_je_geraet_und_anbieter_gewinnt():
    rohsaetze = [roh("teuer"), roh("billig", tarif=25.0), roh("mittel", tarif=28.0)]
    zuordnung = ordne_zu(rohsaetze, [satz()], geraet)
    assert [m.beleg_id for m in zuordnung.messungen] == ["billig"]
    assert zuordnung.mehrdeutig == 2
    messung = zuordnung.messungen[0]
    assert (messung.gesamt_24, messung.vorher_24) == (1180.0, 1300.0)


def test_gleichstand_entscheidet_die_kleinere_beleg_id():
    zuordnung = ordne_zu([roh("b2"), roh("b1")], [], geraet)
    assert [m.beleg_id for m in zuordnung.messungen] == ["b1"]


def test_ohne_bestand_ist_vorher_none_nicht_null():
    messung = ordne_zu([roh()], [], geraet).messungen[0]
    assert messung.vorher_24 is None


def test_anderer_anbieter_ist_eine_eigene_messung():
    rohsaetze = [roh("b1"), roh("b2", anbieter="o2")]
    zuordnung = ordne_zu(rohsaetze, [], geraet)
    assert sorted(m.anbieter for m in zuordnung.messungen) == ["Telekom", "o2"]


def test_satz_ohne_beleg_oder_geraet_wird_gezaehlt_nicht_verschluckt():
    ohne_beleg = roh()
    ohne_beleg["beleg_id"] = ""
    ohne_geraet = roh("b9")
    ohne_geraet["device_id"] = ""
    zuordnung = ordne_zu([ohne_beleg, ohne_geraet], [], geraet)
    assert zuordnung.messungen == []
    assert zuordnung.uebersprungen == {GRUND_OHNE_BELEG: 1, GRUND_OHNE_GERAET: 1}
