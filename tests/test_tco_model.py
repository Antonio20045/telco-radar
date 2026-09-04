"""Das TCO-Datenmodell: Ratenzahlung, Buendel, SIM-only-Referenz, TCO-24.

WAS DIESE TESTS FESTHALTEN
--------------------------
TCO-24 ist die Leitzahl (Entscheidung E2 vom 03.09.2026): Gesamtkosten ueber
24 Monate, Ø/Monat daneben. Sie wird GERECHNET, nie gespeichert, sie rechnet
keinen Rabatt ein, und was jenseits des Horizonts liegt, faellt nicht unter
den Tisch, sondern steht als offener Restbetrag daneben.

Die Zahlen stammen aus dem Live-Abruf des o2-Katalogs vom 03.09.2026, zitiert
in `docs/STRATEGY_GERAETE_TCO.md`: `oneTimePrice: 1`, `monthlyPrice: 30.0`,
`totalPrice: 721.0` - also 1 EUR Anzahlung plus 24 x 30 EUR = 721 EUR. Die
Tarifbetraege sind erfundene Rechenbeispiele und als solche gekennzeichnet;
es gibt noch keinen Sammellauf, der Buendel misst.

KEIN NETZ, KEINE UHR, KEIN gemeinsamer Zustand zwischen den Tests.
"""
import json
import shutil
from pathlib import Path

import pytest

from telco_radar.analyze.geraete_store import GeraeteDB
from telco_radar.analyze.tco_store import TcoDB
from telco_radar.geraete_model import (Ratenzahlung, listung_id,
                                       probe_geht_auf)
from telco_radar.tco_model import (Buendel, Geraeteanteil, Rabatt,
                                   SimOnlyReferenz, TCO_HORIZONT, buendel_id,
                                   geraeteanteil, sim_only_id, tco_24)

_WURZEL = Path(__file__).parent.parent

# Das Rechenbeispiel des Auftrags: 1 EUR + 24 x 30 EUR = 721 EUR.
_ANZAHLUNG, _RATE, _GESAMT = 1.0, 30.0, 721.0


def _buendel(**kw) -> Buendel:
    """Ein vollstaendiges Buendel; jeder Test aendert nur, was er misst."""
    felder = dict(sku_id="apple-iphone-14-128gb-mitternacht", anbieter="o2",
                  tarif_name="o2 Mobile M",
                  # Seit Phase 6 traegt ein Buendel den Fremdschluessel auf
                  # `data/state/tarife.jsonl` - ohne ihn nimmt `TcoDB` einen
                  # Geraetepreis nicht mehr auf.
                  tarif_id="o2:o2-mobile-m", tarif_id_guete="hoch",
                  tarif_monatlich=29.99,
                  geraet_zuzahlung=_ANZAHLUNG, geraet_monatsrate=_RATE,
                  laufzeit_monate=24, anschlusspreis=39.99,
                  quelle_url="https://www.o2online.de/tarife/mobile-m",
                  abgerufen_am="2026-09-03")
    felder.update(kw)
    return Buendel(**felder)


def _referenz(**kw) -> SimOnlyReferenz:
    felder = dict(anbieter="o2", tarif_name="o2 Mobile M",
                  tarif_id="o2:o2-mobile-m", tarif_id_guete="hoch",
                  tarif_sim_only_monatlich=19.99, anschlusspreis=39.99,
                  quelle_url="https://www.o2online.de/tarife/mobile-m-sim",
                  abgerufen_am="2026-09-03")
    felder.update(kw)
    return SimOnlyReferenz(**felder)


# --------------------------------------------------------------------------
# Die Preisform als eigene Groesse
# --------------------------------------------------------------------------

def test_die_ratenzahlung_rechnet_ihren_gesamtbetrag_selbst():
    """1 + 24 x 30 = 721 - die Zahl, die o2 als `totalPrice` ausweist."""
    raten = Ratenzahlung(anzahlung=_ANZAHLUNG, monatsrate=_RATE,
                         laufzeit_monate=24, zins_effektiv=0.0)
    assert raten.gesamt == _GESAMT
    assert raten.deckt(_GESAMT) is True
    assert raten.hinweis == "in 24 Raten (0 %)"


def test_die_rechenprobe_steht_an_einer_stelle_und_faellt_ohne_zahlen_durch():
    """Eine Probe, die ohne Zahlen zustimmt, prueft nichts."""
    assert probe_geht_auf(_ANZAHLUNG, _RATE, 24, _GESAMT) is True
    assert probe_geht_auf(_ANZAHLUNG, _RATE, 24, 999.0) is False
    assert probe_geht_auf(None, _RATE, 24, _GESAMT) is False
    assert probe_geht_auf(_ANZAHLUNG, None, 24, _GESAMT) is False
    assert probe_geht_auf(_ANZAHLUNG, _RATE, None, _GESAMT) is False
    assert probe_geht_auf(_ANZAHLUNG, _RATE, 0, _GESAMT) is False


def test_die_probe_erlaubt_genau_einen_cent_abweichung():
    """Rundung auf zwei Nachkommastellen darf sie nicht kippen (G26)."""
    assert probe_geht_auf(_ANZAHLUNG, _RATE, 24, _GESAMT + 0.01) is True
    assert probe_geht_auf(_ANZAHLUNG, _RATE, 24, _GESAMT + 0.02) is False


def test_eine_ratenzahlung_ohne_laufzeit_gibt_es_nicht():
    with pytest.raises(ValueError, match="laufzeit_monate"):
        Ratenzahlung(anzahlung=_ANZAHLUNG, monatsrate=_RATE, laufzeit_monate=0)


def test_die_geraetefinanzierung_des_buendels_ist_dieselbe_struktur():
    """Eine Zuzahlung mit Rate IST ein Teilzahlungsgeschaeft - dieselbe
    Klasse wie bei der Listung, also dieselbe Rechnung."""
    raten = _buendel().geraeteraten
    assert isinstance(raten, Ratenzahlung)
    assert raten.gesamt == _GESAMT


def test_ohne_rate_gibt_es_keine_halbe_finanzierung():
    assert _buendel(geraet_monatsrate=None).geraeteraten is None


# --------------------------------------------------------------------------
# TCO-24: die Leitzahl
# --------------------------------------------------------------------------

def test_die_tco_summiert_tarif_geraet_und_anschluss():
    ergebnis = tco_24(_buendel())
    assert ergebnis.horizont == TCO_HORIZONT
    # 29,99 x 24 = 719,76 | 1,00 | 30,00 x 24 = 720,00 | 39,99
    assert ergebnis.bestandteile == {
        "Tarif über 24 Monate": 719.76,
        "Gerätezuzahlung": 1.0,
        "Geräteraten (24 von 24)": 720.0,
        "Anschlusspreis": 39.99,
    }
    assert ergebnis.gesamt == 1480.75
    assert ergebnis.monatlich == 61.7          # 1480,75 / 24, kaufmaennisch
    assert ergebnis.restbetrag == 0.0


def test_nur_die_geraeteseite_ergibt_die_721_euro_des_auftrags():
    """`1 € + 24 x 30 € = 721 €`, nachvollziehbar in den Bestandteilen."""
    ergebnis = tco_24(_buendel(tarif_monatlich=None, anschlusspreis=None))
    assert ergebnis.bestandteile["Gerätezuzahlung"] == _ANZAHLUNG
    assert ergebnis.bestandteile["Geräteraten (24 von 24)"] == 720.0
    assert ergebnis.gesamt == _GESAMT
    assert ergebnis.luecken == ["Tarifgrundpreis", "Anschlusspreis",
                                "Boni und Rabatte"]
    assert ergebnis.belastbar is False, "ohne Tarifpreis ist es keine TCO"


def test_null_euro_zuzahlung_ist_eine_aussage_und_keine_luecke():
    """0.0 ist gemessen, None ist unbekannt - der Unterschied ist der Punkt."""
    ergebnis = tco_24(_buendel(geraet_zuzahlung=0.0))
    assert ergebnis.bestandteile["Gerätezuzahlung"] == 0.0
    assert "Gerätezuzahlung" not in ergebnis.luecken
    assert ergebnis.gesamt == 1479.75

    ohne = tco_24(_buendel(geraet_zuzahlung=None))
    assert "Gerätezuzahlung" in ohne.luecken
    assert "Gerätezuzahlung" not in ohne.bestandteile


def test_ein_fehlender_anschlusspreis_ist_nicht_kostenlos():
    ergebnis = tco_24(_buendel(anschlusspreis=None))
    assert "Anschlusspreis" in ergebnis.luecken
    assert ergebnis.gesamt == 1440.76


def test_36_raten_werden_gekappt_und_der_rest_steht_daneben():
    """Der Ueberhang aus § 6.3: eine 24-Monats-Zahl darf zwoelf offene Raten
    nicht verschweigen - sonst belohnt sie, wer am weitesten streckt."""
    ergebnis = tco_24(_buendel(laufzeit_monate=36))
    assert ergebnis.bestandteile["Geräteraten (24 von 36)"] == 720.0
    assert ergebnis.restbetrag == 360.0, "12 offene Raten a 30 EUR"
    assert ergebnis.gesamt == 1480.75, "die Leitzahl bleibt der 24er-Horizont"


def test_eine_kuerzere_ratenlaufzeit_hat_keinen_rest():
    ergebnis = tco_24(_buendel(laufzeit_monate=12))
    assert ergebnis.bestandteile["Geräteraten (12 von 12)"] == 360.0
    assert ergebnis.restbetrag == 0.0


def test_rabatte_stehen_daneben_und_nie_in_der_zahl():
    """Der Nachlass aendert die Kennzahl um KEINEN Cent."""
    rabatte = [Rabatt(name="Wechselbonus", betrag_monatlich=10.0, von_monat=1,
                      bis_monat=6, beleg_url="https://www.o2online.de/x"),
               Rabatt(name="Startguthaben", einmalbetrag=50.0)]
    ohne = tco_24(_buendel())
    mit = tco_24(_buendel(rabatte=rabatte))
    assert mit.gesamt == ohne.gesamt
    assert mit.bestandteile == ohne.bestandteile
    assert mit.rabatte_offen == 110.0, "6 x 10 EUR plus 50 EUR einmalig"
    assert "Boni und Rabatte" not in mit.luecken


def test_ein_rabatt_jenseits_des_horizonts_zaehlt_nicht_mit():
    spaet = Rabatt(name="Treuebonus", betrag_monatlich=5.0, von_monat=25)
    assert spaet.wert(TCO_HORIZONT) == 0.0


def test_ohne_erfasste_rabatte_steht_eine_luecke_da():
    """Kein erfasster Bonus heisst nicht "es gibt keinen" - bei keinem
    Anbieter sind Boni strukturiert abrufbar (§ 6.2 Nr. 9)."""
    assert "Boni und Rabatte" in tco_24(_buendel()).luecken


def test_ein_rabatt_ohne_namen_ist_nicht_nachpruefbar():
    with pytest.raises(ValueError, match="Namen"):
        Rabatt(name="  ", betrag_monatlich=10.0)


def test_die_rechnung_ist_rein_und_fasst_ihr_buendel_nicht_an():
    """Zwei Aufrufe, dasselbe Ergebnis, kein veraendertes Buendel."""
    b = _buendel()
    vorher = dict(b.__dict__)
    erste, zweite = tco_24(b), tco_24(b)
    assert erste == zweite
    assert b.__dict__ == vorher
    assert not hasattr(b, "tco_24"), "die Zahl wird nicht am Objekt abgelegt"


def test_geld_wird_auf_zwei_stellen_gerundet():
    ergebnis = tco_24(_buendel(tarif_monatlich=19.999, geraet_monatsrate=0.005,
                               geraet_zuzahlung=0.0, anschlusspreis=0.0))
    assert ergebnis.bestandteile["Tarif über 24 Monate"] == 480.0
    assert ergebnis.gesamt == 480.24
    assert ergebnis.monatlich == 20.01


# --------------------------------------------------------------------------
# SIM-only-Referenz und effektiver Geraetepreis
# --------------------------------------------------------------------------

def test_der_geraeteanteil_ist_die_differenz_der_zwei_tco():
    """721 EUR Geraet plus 24 x 10 EUR Tarifaufschlag = 961 EUR - die Zahl,
    die auf keiner Seite des Anbieters steht."""
    ergebnis = geraeteanteil(_buendel(), _referenz())
    assert isinstance(ergebnis, Geraeteanteil)
    assert ergebnis.tco_buendel == 1480.75
    assert ergebnis.tco_sim_only == 519.75
    assert ergebnis.betrag == 961.0
    assert ergebnis.belastbar is True


def test_ein_subventioniertes_geraet_darf_negativ_herauskommen():
    """Geraet ohne Zuzahlung UND ein Buendeltarif unter dem SIM-only-Preis:
    dann ist das Buendel ueber 24 Monate billiger als der Tarif allein. Ein
    Abschneiden bei null waere eine stille Korrektur der Marktlage."""
    ergebnis = geraeteanteil(
        _buendel(tarif_monatlich=19.99, geraet_zuzahlung=0.0,
                 geraet_monatsrate=0.0),
        _referenz(tarif_sim_only_monatlich=29.99))
    assert ergebnis.betrag == -240.0


def test_ohne_sim_only_grundpreis_ist_die_differenz_nicht_belastbar():
    """Sonst enthaelt sie den ganzen Tarif und ist um Hunderte Euro zu hoch."""
    ergebnis = geraeteanteil(_buendel(),
                             _referenz(tarif_sim_only_monatlich=None))
    assert "Tarifgrundpreis" in ergebnis.luecken
    assert ergebnis.belastbar is False


def test_fehlende_rabatte_machen_die_differenz_nicht_unbelastbar():
    """Sie gehen auf beiden Seiten nicht in die Rechnung ein, ihr Fehlen
    kuerzt sich also heraus."""
    ergebnis = geraeteanteil(_buendel(), _referenz())
    assert ergebnis.luecken == ["Boni und Rabatte"]
    assert ergebnis.belastbar is True


def test_ein_fremder_anbieter_ergibt_keinen_geraetepreis():
    with pytest.raises(ValueError, match="Anbieter"):
        geraeteanteil(_buendel(), _referenz(anbieter="Vodafone"))


def test_ein_fremder_tarif_ergibt_keinen_geraetepreis():
    """Sonst misst die Differenz den Tarifunterschied und nennt ihn
    Geraetepreis."""
    with pytest.raises(ValueError, match="Tarifen"):
        geraeteanteil(_buendel(), _referenz(tarif_name="o2 Mobile L"))


def test_die_sim_only_referenz_rechnet_ueber_denselben_weg():
    """Zwei Rechenwege waeren zwei Rechnungen."""
    ergebnis = tco_24(_referenz().als_buendel())
    assert ergebnis.gesamt == 519.75
    assert "Gerätezuzahlung" not in ergebnis.luecken, \
        "einer SIM-only-Zeile fehlt kein Geraet - sie hat keins"


def test_ein_buendel_ohne_geraet_hat_keinen_geraeteanteil():
    with pytest.raises(ValueError, match="ohne Geraet"):
        geraeteanteil(_referenz().als_buendel(), _referenz())


# --------------------------------------------------------------------------
# Die Zusicherungen des Modells
# --------------------------------------------------------------------------

def test_ein_buendel_ohne_tarif_ist_keins():
    """Teil C4 auf der Buendelebene: "iPhone fuer 1 Euro" ist ohne den Tarif
    dahinter eine Zahl ohne Bedeutung."""
    with pytest.raises(ValueError, match="ohne Tarif"):
        _buendel(tarif_name="")


def test_ein_buendel_ohne_anbieter_ist_keins():
    with pytest.raises(ValueError, match="ohne Anbieter"):
        _buendel(anbieter="")


def test_eine_sim_only_zeile_kann_keinen_geraetepreis_tragen():
    """Sonst zoege der effektive Geraetepreis ihn von sich selbst ab."""
    with pytest.raises(ValueError, match="ohne SKU"):
        _buendel(sku_id="", geraet_zuzahlung=1.0, geraet_monatsrate=None)


def test_negative_betraege_kommen_nicht_ins_modell():
    with pytest.raises(ValueError, match="negativer preis"):
        _buendel(tarif_monatlich=-1.0)
    with pytest.raises(ValueError, match="negativer betrag"):
        Rabatt(name="Bonus", einmalbetrag=-50.0)


def test_das_buendel_hat_kein_feld_fuer_einen_barpreis():
    """Ein Ratengesamtbetrag gehoert nie in `preis_ohne_vertrag` - das war
    der Befund, mit dem dieses Vorhaben angefangen hat."""
    assert not hasattr(_buendel(), "preis_ohne_vertrag")


# --------------------------------------------------------------------------
# IDs: eine eigene Namensmenge
# --------------------------------------------------------------------------

def test_die_ids_sagen_im_klartext_was_sie_sind():
    assert buendel_id("apple-iphone-14-128gb-mitternacht", "o2",
                      "o2 Mobile M") == \
        "buendel--o2--apple-iphone-14-128gb-mitternacht--o2-mobile-m"
    assert sim_only_id("o2", "o2 Mobile M") == "simonly--o2--o2-mobile-m"


def test_eine_fehlende_angabe_steht_offen_in_der_id():
    assert buendel_id("", "o2", "o2 Mobile M").split("--")[2] == "ohne-geraet"
    assert sim_only_id("o2", "").endswith("--ohne-tarif")


def test_keine_neue_id_kann_eine_listung_id_treffen():
    """Nicht dem Zufall ueberlassen, sondern der Form: eine `listung_id` hat
    zwei Bestandteile, ein Buendel vier, eine Referenz drei - auch bei einem
    Anbieter, der wirklich "Buendel" hiesse."""
    sku = "apple-iphone-14-128gb-mitternacht"
    ids = [listung_id(sku, "o2"), listung_id(sku, "Buendel"),
           listung_id(sku, "SIM only"), buendel_id(sku, "o2", "o2 Mobile M"),
           sim_only_id("o2", "o2 Mobile M")]
    assert len(set(ids)) == len(ids)
    assert [len(i.split("--")) for i in ids] == [2, 2, 2, 4, 3]


# --------------------------------------------------------------------------
# Der Bestand - und dass er den bestehenden nicht anfasst
# --------------------------------------------------------------------------

def test_der_bestand_nimmt_buendel_und_referenzen_auf(tmp_path):
    db = TcoDB(tmp_path / "geraete_tco.json")
    neu, gesehen = db.upsert_buendel([_buendel()], "2026-09-03")
    assert (neu, gesehen) == (1, {_buendel().id})
    assert db.setze_referenzen([_referenz()], "2026-09-03") == 1

    eintrag = db.buendel()[0]
    assert eintrag["first_seen"] == "2026-09-03"
    assert eintrag["tarif_monatlich"] == 29.99
    assert db.referenz("o2", "o2 Mobile M")["tarif_sim_only_monatlich"] == 19.99


def test_derselbe_lauf_zweimal_legt_kein_zweites_buendel_an(tmp_path):
    db = TcoDB(tmp_path / "geraete_tco.json")
    db.upsert_buendel([_buendel()], "2026-09-03")
    neu, _ = db.upsert_buendel([_buendel(tarif_monatlich=34.99)], "2026-09-04")
    assert neu == 0
    assert len(db.buendel()) == 1
    eintrag = db.buendel()[0]
    assert eintrag["first_seen"] == "2026-09-03", "seit wann ist keine Messung"
    assert eintrag["last_verified"] == "2026-09-04"
    assert eintrag["tarif_monatlich"] == 34.99


def test_ein_buendel_zeigt_immer_EINE_messung(tmp_path):
    """Ein Tarifpreis von gestern plus eine Geraeterate von heute ergaebe eine
    Summe, die an keinem Tag gegolten hat - anders als bei den Listungen wird
    hier gemeinsam geschrieben, auch leer."""
    db = TcoDB(tmp_path / "geraete_tco.json")
    db.upsert_buendel([_buendel()], "2026-09-03")
    db.upsert_buendel([_buendel(tarif_monatlich=None)], "2026-09-04")
    assert db.buendel()[0]["tarif_monatlich"] is None
    assert "Tarifgrundpreis" in tco_24(
        _buendel(tarif_monatlich=None)).luecken


def test_der_bestand_ueberlebt_das_schreiben_und_lesen(tmp_path):
    pfad = tmp_path / "geraete_tco.json"
    db = TcoDB(pfad)
    db.upsert_buendel([_buendel(rabatte=[Rabatt(name="Wechselbonus",
                                                betrag_monatlich=10.0,
                                                bis_monat=6)])], "2026-09-03")
    db.setze_referenzen([_referenz()], "2026-09-03")
    assert db.save("2026-09-03") is True

    wieder = TcoDB(pfad)
    assert wieder.lesbar is True
    assert wieder.buendel() == db.buendel()
    assert wieder.referenzen() == db.referenzen()
    assert wieder.buendel()[0]["rabatte"][0]["name"] == "Wechselbonus"


def test_ein_leerer_bestand_legt_keine_datei_an(tmp_path):
    """Eine Datei mit zwei leeren Listen sieht im Repo aus wie ein Ergebnis."""
    pfad = tmp_path / "geraete_tco.json"
    assert TcoDB(pfad).save("2026-09-03") is False
    assert not pfad.exists()


def test_eine_unlesbare_datei_ist_nicht_dasselbe_wie_leer(tmp_path):
    pfad = tmp_path / "geraete_tco.json"
    pfad.write_text("{kaputt", encoding="utf-8")
    db = TcoDB(pfad)
    assert db.lesbar is False
    assert db.buendel() == []


def test_nur_echte_buendel_kommen_in_den_bestand(tmp_path):
    """Ein Woerterbuch koennte jedes Feld tragen und keine Zusicherung."""
    db = TcoDB(tmp_path / "geraete_tco.json")
    with pytest.raises(TypeError):
        db.upsert_buendel([{"anbieter": "o2"}], "2026-09-03")


# --------------------------------------------------------------------------
# Migration: der bestehende Bestand bleibt unangetastet
# --------------------------------------------------------------------------

_ALTBESTAND = {
    "updated": "2026-09-03",
    "anbieter": {"o2": {"laeufe": 5, "termine": ["2026-09-01"]}},
    "listungen": [
        {"id": "o2--apple-iphone-14-128gb-mitternacht",
         "sku_id": "apple-iphone-14-128gb-mitternacht",
         "device_id": "apple-iphone-14", "anbieter": "o2",
         "anbieter_typ": "netzbetreiber", "netz": "o2", "speicher_gb": 128,
         "farbe_roh": "Mitternacht", "farbe_normalisiert": "schwarz",
         "ean": "", "zustand": "neu", "first_seen": "2026-08-10",
         "status": "aktiv", "missed_checks": 0, "erstpreis": 721.0,
         "erstpreis_art": "ohne_vertrag", "erstpreis_am": "2026-08-10",
         "last_verified": "2026-09-03", "letzter_check": "2026-09-03",
         "quelle_url": "https://www.o2online.de/p",
         "abgerufen_am": "2026-09-03", "verfuegbarkeit": "lieferbar",
         "confidence": "hoch", "preis_ohne_vertrag": 721.0},
        {"id": "freenet--apple-iphone-14-128gb-mitternacht",
         "sku_id": "apple-iphone-14-128gb-mitternacht",
         "device_id": "apple-iphone-14", "anbieter": "freenet",
         "anbieter_typ": "handel", "netz": "", "speicher_gb": 128,
         "farbe_roh": "Mitternacht", "farbe_normalisiert": "schwarz",
         "ean": "", "zustand": "neu", "first_seen": "2026-08-10",
         "status": "aktiv", "missed_checks": 0, "erstpreis": 949.0,
         "erstpreis_art": "ohne_vertrag", "erstpreis_am": "2026-08-10",
         "last_verified": "2026-09-03", "letzter_check": "2026-09-03",
         "quelle_url": "https://www.freenet.de/p",
         "abgerufen_am": "2026-09-03", "verfuegbarkeit": "lieferbar",
         "confidence": "hoch", "preis_ohne_vertrag": 949.0},
    ],
}

_ALTE_HISTORIE = (
    '{"listung_id": "o2--apple-iphone-14-128gb-mitternacht", '
    '"datum": "2026-08-10", "preis_ohne_vertrag": 721.0}\n'
    '{"listung_id": "freenet--apple-iphone-14-128gb-mitternacht", '
    '"datum": "2026-08-10", "preis_ohne_vertrag": 949.0}\n'
)


def _lege_altbestand_an(tmp_path) -> tuple[Path, Path]:
    db_pfad = tmp_path / "geraete_db.json"
    jsonl = tmp_path / "geraete_preise.jsonl"
    db_pfad.write_text(json.dumps(_ALTBESTAND, ensure_ascii=False, indent=1),
                       encoding="utf-8")
    jsonl.write_text(_ALTE_HISTORIE, encoding="utf-8")
    return db_pfad, jsonl


def test_die_neuen_datensaetze_lassen_listungen_und_historie_unberuehrt(
        tmp_path):
    """Der Migrationsbeweis: ein Buendel fuer DIESELBE SKU beim DEMSELBEN
    Anbieter darf keine `listung_id` verschieben und keine Zeile der
    Preishistorie anfassen."""
    db_pfad, jsonl = _lege_altbestand_an(tmp_path)
    vorher_db = db_pfad.read_bytes()
    vorher_jsonl = jsonl.read_bytes()

    tco = TcoDB(tmp_path / "geraete_tco.json")
    tco.upsert_buendel([_buendel()], "2026-09-04")
    tco.setze_referenzen([_referenz()], "2026-09-04")
    assert tco.save("2026-09-04") is True

    assert db_pfad.read_bytes() == vorher_db, "geraete_db.json angefasst"
    assert jsonl.read_bytes() == vorher_jsonl, "Preishistorie angefasst"

    # Und die IDs beider Bestaende beruehren sich nicht.
    bestand = GeraeteDB(db_pfad)
    listungen = {e["id"] for e in bestand.eintraege()}
    neue = {e["id"] for e in tco.buendel()} | {e["id"] for e in
                                               tco.referenzen()}
    assert listungen == {"o2--apple-iphone-14-128gb-mitternacht",
                         "freenet--apple-iphone-14-128gb-mitternacht"}
    assert not (listungen & neue)


def _nach_id(listungen: list) -> dict:
    """Die Listungen ueber ihre ID, damit die Reihenfolge der Datei die
    Gleichheit nicht beeinflusst - `eintraege()` sortiert nach Anbieter."""
    return {e["id"]: e for e in listungen}


def test_ein_altbestand_ueberlebt_laden_und_speichern_wertgleich(tmp_path):
    """Was schon da war, bleibt Feld fuer Feld dasselbe - bis auf das Datum,
    das der Lauf setzt."""
    db_pfad, _ = _lege_altbestand_an(tmp_path)
    bestand = GeraeteDB(db_pfad)
    bestand.save("2026-09-04")

    danach = json.loads(db_pfad.read_text(encoding="utf-8"))
    assert _nach_id(danach["listungen"]) == _nach_id(_ALTBESTAND["listungen"])
    assert danach["anbieter"] == _ALTBESTAND["anbieter"]
    assert danach["updated"] == "2026-09-04"


@pytest.mark.skipif(not (_WURZEL / "data/state/geraete_db.json").exists(),
                    reason="kein ausgelieferter Bestand im Arbeitsverzeichnis")
def test_der_echte_bestand_behaelt_jede_id_und_jeden_betrag(tmp_path):
    """Dieselbe Probe am wirklich ausgelieferten Bestand (391 Listungen).

    Gelesen wird das Original, geschrieben wird in ein temporaeres
    Verzeichnis - `data/state/` wird von einem Test nicht angefasst.
    """
    original = _WURZEL / "data/state/geraete_db.json"
    unberuehrt = original.read_bytes()
    kopie = tmp_path / "geraete_db.json"
    shutil.copy(original, kopie)
    vorher = json.loads(unberuehrt.decode("utf-8"))

    bestand = GeraeteDB(kopie)
    bestand.save("2026-09-04")
    danach = json.loads(kopie.read_text(encoding="utf-8"))

    assert len(vorher["listungen"]) > 100, "der Bestand ist unerwartet duenn"
    assert _nach_id(danach["listungen"]) == _nach_id(vorher["listungen"])
    assert original.read_bytes() == unberuehrt, "data/state/ angefasst"


# --------------------------------------------------------------------------
# Der Fremdschluessel (Phase 6, Abnahmekriterium 3)
# --------------------------------------------------------------------------

def test_ein_geraetepreis_ohne_tarif_id_kommt_nicht_in_den_bestand(tmp_path):
    """"Kein Buendelpreis im Bestand ohne aufloesbaren tarif_id."

    Die Regel sitzt am SPEICHER und nicht am Datensatz: ein Buendel zu
    bauen und festzustellen, dass sein Tarif nicht aufloest, ist ein
    gueltiger Zwischenschritt - es abzulegen waere eine Zahl, deren
    Bezugsgroesse niemand nachschlagen kann.
    """
    db = TcoDB(tmp_path / "geraete_tco.json")
    with pytest.raises(ValueError, match="ohne aufloesbaren Tarif"):
        db.upsert_buendel([_buendel(tarif_id="")], "2026-09-04")
    # Und die Gegenprobe: MIT Schluessel geht dasselbe Buendel durch.
    # Ohne sie bewiese der Test nur, dass irgendetwas wirft.
    neu, _ = db.upsert_buendel([_buendel()], "2026-09-04")
    assert neu == 1


def test_eine_sim_only_zeile_braucht_keinen_geraetepreis_und_keinen_schluessel(
        tmp_path):
    """Die Sperre gilt dem GERAETEpreis, nicht jedem Datensatz.

    Ein Buendel ohne Geraet traegt keine Zuzahlung und keine Rate - es gibt
    dort keine Zahl, deren Bezug fehlen koennte.
    """
    db = TcoDB(tmp_path / "geraete_tco.json")
    ohne = _buendel(sku_id="", tarif_id="", geraet_zuzahlung=None,
                    geraet_monatsrate=None)
    neu, _ = db.upsert_buendel([ohne], "2026-09-04")
    assert neu == 1


def test_der_schluessel_ueberlebt_das_schreiben_und_lesen(tmp_path):
    """Sonst stuende er im Datensatz und nicht in der Datei - und die
    naechste Sitzung faende einen Bestand ohne Bezug."""
    pfad = tmp_path / "geraete_tco.json"
    db = TcoDB(pfad)
    db.upsert_buendel([_buendel(tarif_id="o2:o2-mobile-m",
                                tarif_id_guete="mittel")], "2026-09-04")
    db.setze_referenzen([_referenz()], "2026-09-04")
    db.save("2026-09-04")

    wieder = TcoDB(pfad)
    assert wieder.buendel()[0]["tarif_id"] == "o2:o2-mobile-m"
    assert wieder.buendel()[0]["tarif_id_guete"] == "mittel"
    assert wieder.referenzen()[0]["tarif_id"] == "o2:o2-mobile-m"


def test_die_referenz_reicht_ihren_schluessel_an_ihr_buendel_weiter():
    """`als_buendel()` ist derselbe Datensatz in anderer Form.

    Verloere er dabei den Schluessel, waere die SIM-only-Zeile im selben
    Bestand plotzlich beziehungslos - und `tco_24` rechnete gegen einen
    Tarif, den niemand nachschlagen kann.
    """
    b = _referenz(tarif_id="o2:o2-mobile-m", tarif_id_guete="hoch").als_buendel()
    assert b.tarif_id == "o2:o2-mobile-m"
    assert b.tarif_id_guete == "hoch"


def test_der_referenzbestand_wird_ersetzt_und_waechst_nicht(tmp_path):
    """Abgeleitete Daten werden neu gesetzt, nicht ergaenzt.

    Am 04.09.2026 gemessen: nach zwei Laeufen standen 40 Referenzen zu 32
    Tarifen auf der Seite - fuenfzehn davon zu Tarifnamen, die es im
    Bestand nicht mehr gab. Beide Laeufe hatten fuer sich richtig
    gerechnet; aufgefallen ist es beim ANSEHEN der Tafel.
    """
    db = TcoDB(tmp_path / "geraete_tco.json")
    db.setze_referenzen([_referenz(tarif_name="Alter Name")], "2026-09-04")
    neu, entfernt = db.ersetze_referenzen(
        [_referenz(tarif_name="Neuer Name")], "2026-09-04")
    assert (neu, entfernt) == (1, 1)
    assert [r["tarif_name"] for r in db.referenzen()] == ["Neuer Name"]


def test_zweimal_dasselbe_ersetzen_entfernt_nichts(tmp_path):
    """Der Normalfall des naechtlichen Laufs: nichts hat sich geaendert.

    Ohne diese Zeile bewiese der Test darueber nur, dass etwas geloescht
    wird - nicht, dass unveraenderte Referenzen stehen bleiben.
    """
    db = TcoDB(tmp_path / "geraete_tco.json")
    db.ersetze_referenzen([_referenz()], "2026-09-04")
    neu, entfernt = db.ersetze_referenzen([_referenz()], "2026-09-05")
    assert (neu, entfernt) == (0, 0)
    assert db.referenzen()[0]["last_verified"] == "2026-09-05"


def test_das_ersetzen_laesst_die_buendel_unberuehrt(tmp_path):
    """Ein Buendel ist eine MESSUNG und wird nie stillschweigend geloescht.

    Die Trennung ist der ganze Punkt: die Referenzen leitet dieses Projekt
    aus `tarife.jsonl` ab, die Buendel misst es bei einem Anbieter.
    """
    db = TcoDB(tmp_path / "geraete_tco.json")
    db.upsert_buendel([_buendel()], "2026-09-04")
    db.ersetze_referenzen([], "2026-09-04")
    assert len(db.buendel()) == 1
    assert db.referenzen() == []
