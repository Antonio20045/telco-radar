"""Welcher Preis bekommt das Belegbild, und was kostete dasselbe vorher?

Zahlen von Hand gerechnet: Tarif 30 € x 24 + Rate 20 € x 24 + Zuzahlung = Gesamtkosten.
"""

from __future__ import annotations

from telco_radar.analyze.beleg_schluessel import (
    GRUND_OHNE_BELEG,
    GRUND_OHNE_GERAET,
    Messung,
    ist_besser,
    ordne_zu,
    vorher_je_konfiguration,
)
from telco_radar.beleg_regeln import ist_grosse_aenderung


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
        "quelle_art": "klick",
        "zustand": "neu",
        "abgerufen_am": "2026-11-01",
    }
    daten.update(extra)
    return daten


def roh(beleg_id="b1", **extra) -> dict:
    daten = satz(**extra)
    daten.update(device_id="iphone-17", speicher_gb=256, beleg_id=beleg_id)
    return daten


def geraet(sku: str):
    return ("iphone-17", 256) if sku == "sku-1" else ("", None)


SCHLUESSEL = ("Telekom", "iphone-17", 256, "m", 24)


def test_gesamtkosten_wie_von_hand_gerechnet():
    vorher = vorher_je_konfiguration([satz()], geraet)
    assert vorher == {SCHLUESSEL: 1300.0}


def test_vorher_ist_der_jüngste_stand_derselben_konfiguration():
    bestand = [
        satz(abgerufen_am="2026-10-20", tarif=10.0),
        satz(abgerufen_am="2026-11-01"),
        satz(abgerufen_am="2026-10-25", tarif=25.0),
    ]
    assert vorher_je_konfiguration(bestand, geraet) == {SCHLUESSEL: 1300.0}


def test_gleicher_tag_nimmt_den_niedrigeren_wert():
    bestand = [satz(), satz(tarif=25.0)]
    assert vorher_je_konfiguration(bestand, geraet) == {SCHLUESSEL: 1180.0}


def test_vorher_ignoriert_unbekannte_geraete_fremde_quellen_und_quarantaene():
    bestand = [
        satz(sku_id="fremd"),
        satz(pruefung="quarantaene"),
        satz(quelle_art=None),
    ]
    assert vorher_je_konfiguration(bestand, geraet) == {}


def test_veraltet_zaehlt_als_letzter_stand():
    bestand = [satz(pruefung="veraltet 16")]
    assert vorher_je_konfiguration(bestand, geraet) == {SCHLUESSEL: 1300.0}


def test_billigerer_fremder_tarif_macht_unveraenderten_preis_nicht_gross():
    """Vorher: Minimum über alle Tarife, M (1300 €) gegen L (1000 €) war +30 %."""
    bestand = [satz(), satz(tarif_name="L", tarif=12.0)]
    heute = [roh("m"), roh("l", tarif_name="L", tarif=12.0)]
    zuordnung = ordne_zu(heute, bestand, geraet)
    assert zuordnung.messungen[0].beleg_id == "l"
    messung = zuordnung.messungen[0]
    assert messung.vorher_24 == messung.gesamt_24
    assert not ist_grosse_aenderung(messung.vorher_24, messung.gesamt_24)


def test_echte_preisaenderung_derselben_konfiguration_ist_gross():
    """Gegenprobe: 30 € statt 25 € Tarif über 24 Monate sind 120 € (mehr als 5 %)."""
    messung = ordne_zu([roh(tarif=25.0)], [satz(tarif=30.0)], geraet).messungen[0]
    assert (messung.vorher_24, messung.gesamt_24) == (1300.0, 1180.0)
    assert ist_grosse_aenderung(messung.vorher_24, messung.gesamt_24)


def test_neue_konfiguration_ohne_vorgaenger_hat_kein_vorher():
    messung = ordne_zu([roh(tarif_name="XL")], [satz()], geraet).messungen[0]
    assert messung.vorher_24 is None
    assert not ist_grosse_aenderung(messung.vorher_24, messung.gesamt_24)


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


def messung(beleg_id: str, gesamt: float | None) -> Messung:
    return Messung("iphone-17", 256, "Telekom", beleg_id, gesamt, None)


def test_ist_besser_bei_gleichem_preis_entscheidet_die_kleinere_beleg_id():
    """Über Jobs hinweg: gleicher Preis, egal in welcher Reihenfolge verglichen wird."""
    a, b = messung("b1", 1300.0), messung("b2", 1300.0)
    assert ist_besser(a, b)
    assert not ist_besser(b, a)


def test_ist_besser_gleiche_messung_ersetzt_sich_nicht():
    a = messung("b1", 1300.0)
    assert not ist_besser(a, messung("b1", 1300.0))


def test_ist_besser_zahl_schlaegt_none_in_beide_richtungen():
    zahl, luecke = messung("b9", 5000.0), messung("b1", None)
    assert ist_besser(zahl, luecke)
    assert not ist_besser(luecke, zahl)


def test_ist_besser_zwei_luecken_entscheidet_die_kleinere_beleg_id():
    a, b = messung("b1", None), messung("b2", None)
    assert ist_besser(a, b)
    assert not ist_besser(b, a)
