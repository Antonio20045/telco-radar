"""Der Rechenkern der TCO-first-Ansicht: `tco_model.tco_bindung`.

Gerechnet wird gegen die ECHTEN Saetze aus `data/state/geraete_tco.json`
und die Rechenprobe des Auftrags - eine Fixture, die ihre eigenen Zahlen
mitbringt, bewiese nur, dass sie mit sich selbst uebereinstimmt.

Die eine Falle, gegen die die Haelfte dieser Tests steht: o2 bindet den
TARIF 24 Monate und finanziert das GERAET ueber 36. Wer die zwei
gleichsetzt, addiert zwoelf Tarifmonate, die niemand schuldet.
"""
from __future__ import annotations

import json
import pathlib

import pytest

from telco_radar.tco_model import (LEITFRAGE_MONATE, POSTEN_ANSCHLUSS,
                                   POSTEN_RABATTE, POSTEN_RATE, POSTEN_TARIF,
                                   POSTEN_TARIFBINDUNG, Buendel, Rabatt,
                                   effektiv_ohne_geraet, tco_bindung)

WURZEL = pathlib.Path(__file__).resolve().parents[1]


def o2_iphone17pro() -> Buendel:
    """Der Satz der Rechenprobe, mit den Betraegen des Auftrags.

    `anschlusspreis` steht hier auf 0,00 EUR - so, wie er im Bestand steht
    (o2 nimmt fuer die L-Linie keinen Anschlusspreis). Der Auftrag rechnete
    mit 39,99 EUR; die Abweichung ist in der Uebergabe dokumentiert.
    """
    return Buendel(sku_id="apple-iphone-17-pro-256gb-silber", anbieter="o2",
                   tarif_name="O2 Mobile L Plus mit 150 GB+ (24 Mon.)",
                   tarif_id="o2:o2-mobile-l", tarif_monatlich=19.99,
                   tarif_bindung_monate=24, geraet_zuzahlung=1.00,
                   geraet_monatsrate=36.50, laufzeit_monate=36,
                   anschlusspreis=0.00)


def test_die_rechenprobe_des_auftrags_geht_auf():
    e = tco_bindung(o2_iphone17pro())
    assert e.bindung == 36, "die LAENGERE Bindung fuehrt die Karte (A5.5)"
    assert e.tarif_bindung == 24 and e.raten_laufzeit == 36
    # 0,00 + 1,00 + 24 x 19,99 (479,76) + 36 x 36,50 (1314,00)
    assert e.gesamt == 1794.76
    assert e.schnitt_monat == 49.85
    assert e.label == "TCO-36"
    assert e.belastbar


def test_die_leitfrage_wird_woertlich_beantwortet():
    """A5.2: was nach 24 Monaten gezahlt ist, und was dann noch offen ist."""
    e = tco_bindung(o2_iphone17pro())
    # 0,00 + 1,00 + 24 x 19,99 + 24 x 36,50
    assert e.gezahlt_nach_24 == 1356.76
    # zwoelf offene Geraeteraten
    assert e.offen_nach_24 == 438.00
    assert round(e.gezahlt_nach_24 + e.offen_nach_24, 2) == e.gesamt


def test_die_tarifbindung_wird_nicht_auf_die_ratenlaufzeit_gedehnt():
    """Der teuerste denkbare Fehler dieser Rechnung, als eigener Test.

    36 statt 24 Tarifmonate waeren 12 x 19,99 = 239,88 EUR zu viel - und
    die Zahl saehe vollkommen plausibel aus.
    """
    e = tco_bindung(o2_iphone17pro())
    tarifposten = [p for p in e.bestandteile if p["kategorie"] == "tarif"]
    assert len(tarifposten) == 1
    assert tarifposten[0]["betrag"] == 479.76
    assert e.gesamt != 1794.76 + 239.88


def test_ohne_gemessene_tarifbindung_gibt_es_keine_leitzahl():
    """Ein Grundpreis ohne Bindungsdauer ist kein Bestandteil.

    Ohne diese Zusicherung stuende die Geraetesumme allein als "TCO-36" da -
    ein sehr guenstiges Buendel, das es nicht gibt.
    """
    b = o2_iphone17pro()
    b.tarif_bindung_monate = None
    e = tco_bindung(b)
    assert POSTEN_TARIFBINDUNG in e.luecken
    assert not e.belastbar
    assert e.bindung == 36, "die Ratenlaufzeit steht trotzdem"


def test_fehlende_groessen_werden_benannt_und_nie_zu_null():
    b = Buendel(sku_id="x", anbieter="o2", tarif_name="T",
                tarif_monatlich=None, tarif_bindung_monate=24,
                geraet_zuzahlung=None, geraet_monatsrate=None,
                anschlusspreis=None)
    e = tco_bindung(b)
    for posten in (POSTEN_TARIF, POSTEN_RATE, POSTEN_ANSCHLUSS,
                   POSTEN_RABATTE):
        assert posten in e.luecken
    assert e.gesamt is None and not e.belastbar


def test_null_euro_ist_eine_messung_und_keine_luecke():
    e = tco_bindung(o2_iphone17pro())
    assert POSTEN_ANSCHLUSS not in e.luecken
    assert any(p["name"] == POSTEN_ANSCHLUSS and p["betrag"] == 0.0
               for p in e.bestandteile)


def test_ein_buendelmonatspreis_wird_nicht_aufgeteilt():
    """1&1 nennt EINEN Betrag fuer Tarif und Geraet (Strategie § 13.2)."""
    b = Buendel(sku_id="apple-iphone-15-128gb-blau", anbieter="1&1",
                tarif_name="1&1 All-Net-Flat S", buendel_monatlich=32.99,
                laufzeit_monate=36)
    e = tco_bindung(b)
    assert e.bindung == 36
    assert e.gesamt == round(36 * 32.99, 2) == 1187.64
    assert e.schnitt_monat == 32.99
    assert e.gezahlt_nach_24 == round(24 * 32.99, 2) == 791.76
    assert e.offen_nach_24 == 395.88
    assert [p["kategorie"] for p in e.bestandteile] == ["buendel"]
    assert POSTEN_ANSCHLUSS in e.luecken, "unbekannt ist nicht kostenlos"
    assert e.belastbar, "der Tarifanteil steckt im Buendelbetrag"


def test_ein_buendelbetrag_neben_seinen_bestandteilen_ist_ein_fehler():
    with pytest.raises(ValueError):
        Buendel(sku_id="x", anbieter="1&1", tarif_name="T",
                buendel_monatlich=32.99, tarif_monatlich=14.99)


def test_eine_sim_only_zeile_kann_keinen_buendelbetrag_tragen():
    with pytest.raises(ValueError):
        Buendel(sku_id="", anbieter="1&1", tarif_name="T",
                buendel_monatlich=32.99)


def test_ein_belegter_bonus_wird_abgezogen_und_einzeln_genannt():
    """Katalog D: "− belegte Boni", und "niemals STILL einrechnen"."""
    b = o2_iphone17pro()
    b.rabatte = [Rabatt(name="Wechselbonus", einmalbetrag=50.0,
                        beleg_url="https://example.invalid/bonus")]
    e = tco_bindung(b)
    assert e.boni_abzug == 50.0
    assert e.boni[0]["name"] == "Wechselbonus"
    assert e.gesamt == round(1794.76 - 50.0, 2) == 1744.76
    # Der Abzug steht als eigener, negativer Posten - genau das braucht die
    # Balkengrafik fuer ihr Bonussegment.
    assert any(p["kategorie"] == "bonus" and p["betrag"] == -50.0
               for p in e.bestandteile)
    assert POSTEN_RABATTE not in e.luecken


def test_ein_bonus_innerhalb_der_ersten_24_monate_mindert_auch_die_leitfrage():
    b = o2_iphone17pro()
    b.rabatte = [Rabatt(name="6 Monate 10 EUR", betrag_monatlich=10.0,
                        von_monat=1, bis_monat=6)]
    e = tco_bindung(b)
    assert e.boni_abzug == 60.0
    assert e.gezahlt_nach_24 == round(1356.76 - 60.0, 2) == 1296.76
    assert e.offen_nach_24 == 438.00, "der Bonus liegt vor Monat 25"


def test_der_effektivpreis_braucht_einen_belegten_barpreis():
    e = tco_bindung(o2_iphone17pro())
    # 49,85 - 1249,00 / 36 = 49,85 - 34,6944 = 15,16
    assert effektiv_ohne_geraet(e, 1249.00) == 15.16
    assert effektiv_ohne_geraet(e, None) is None


def test_kein_effektivpreis_ohne_belastbare_kennzahl():
    b = o2_iphone17pro()
    b.tarif_monatlich = None
    assert effektiv_ohne_geraet(tco_bindung(b), 1249.00) is None


def test_am_echten_bestand_traegt_jede_o2_zeile_ihre_zwei_laufzeiten():
    """Gegen `data/state/geraete_tco.json`, nicht gegen eine Fixture.

    Der Tarifbestand liefert die Bindung; ohne ihn stuende hier fuer JEDES
    der 62 Buendel eine Luecke, und der ganze Reiter waere leer.
    """
    tco = json.loads((WURZEL / "data/state/geraete_tco.json").read_text())
    bindung_je_tarif = {}
    for zeile in (WURZEL / "data/state/tarife.jsonl").read_text().splitlines():
        satz = json.loads(zeile)
        if satz.get("tarif_id") and satz.get("laufzeit_monate"):
            bindung_je_tarif[satz["tarif_id"]] = satz["laufzeit_monate"]

    geprueft = 0
    for satz in tco["buendel"]:
        b = Buendel(sku_id=satz["sku_id"], anbieter=satz["anbieter"],
                    tarif_name=satz["tarif_name"],
                    tarif_id=satz.get("tarif_id", ""),
                    tarif_monatlich=satz.get("tarif_monatlich"),
                    tarif_bindung_monate=bindung_je_tarif.get(
                        satz.get("tarif_id", "")),
                    geraet_zuzahlung=satz.get("geraet_zuzahlung"),
                    geraet_monatsrate=satz.get("geraet_monatsrate"),
                    laufzeit_monate=satz.get("laufzeit_monate", 24),
                    anschlusspreis=satz.get("anschlusspreis"))
        e = tco_bindung(b)
        assert e.belastbar, f"{satz['id']} nicht belastbar: {e.luecken}"
        assert e.bindung == 36 and e.tarif_bindung == 24
        assert e.offen_nach_24 == round(satz["geraet_monatsrate"] * 12, 2)
        geprueft += 1
    assert geprueft == len(tco["buendel"]) >= 62, \
        "der Test muss ALLE Saetze angefasst haben, sonst prueft er nichts"


def test_der_leitfragehorizont_ist_vierundzwanzig_monate():
    assert LEITFRAGE_MONATE == 24
