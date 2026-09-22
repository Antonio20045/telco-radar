"""Das TCO-Datenmodell: Ratenzahlung, Buendel, SIM-only-Referenz, TCO-24.

WAS DIESE TESTS FESTHALTEN
--------------------------
Die Leitzahl heisst "Kosten ueber 24 Monate" (A1 vom 20.09.2026, vorher
TCO-24, Entscheidung E2 vom 03.09.2026): Gesamtkosten ueber 24 Monate,
Ø/Monat daneben. Sie wird GERECHNET, nie gespeichert, sie rechnet keinen
Rabatt ein, und was nach Monat 24 noch geschuldet ist, bleibt IN der Zahl
und steht zusaetzlich als offener Restbetrag daneben.

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
from telco_radar.tarif_model import Preisphase
from telco_radar.tco_model import (Buendel, Geraeteanteil, LAUFZEIT_LUECKE,
                                   POSTEN_LAUFZEIT, POSTEN_RATE, Rabatt,
                                   SimOnlyReferenz, TCO_HORIZONT,
                                   UNGLEICHER_ZEITRAUM,
                                   buendel_id, buendel_id_aktuell,
                                   buendel_id_ohne_laufzeit, geraeteanteil,
                                   laufzeit_in_monaten, laufzeit_segment,
                                   phasensumme, sim_only_id, tco_24,
                                   tco_bindung)

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
        "Geräteraten über 24 Monate": 720.0,
        "Anschlusspreis": 39.99,
    }
    assert ergebnis.gesamt == 1480.75
    assert ergebnis.leitzahl_monate == 24
    assert ergebnis.monatlich == 61.7          # 1480,75 / 24, kaufmaennisch
    assert ergebnis.restbetrag == 0.0


def test_der_monatsschnitt_teilt_durch_den_zeitraum_der_eigenen_summe():
    """P0-B-h1: Ø/Monat teilt die Summe durch die Monate, die sie TRAEGT.

    Der echte 1&1-Satz vom 21.09.2026 (iPhone 17 Pro 256 GB, All-Net-Flat
    S): 360,00 Zuzahlung + 36 x 44,99 Buendelpreis + 39,90 Anschlusspreis
    = 2.019,54 EUR. Der EINE Monatsbetrag traegt Tarif und Geraet (§ 13.2)
    und laeuft 36 Mal - der Zeitraum der Zahl ist damit 36 und nicht der
    24-Monats-Tarifhorizont.

    ROT GEGEN DEN ALTEN STAND: bis hierher rechnete `tco_24`
    `gesamt / TCO_HORIZONT` = 2.019,54 / 24 = 84,15 EUR. Die Seite zeigte
    "Kosten über 36 Monate 2.019,54 € · Ø 84,15 €/Monat", und 84,15 x 36
    = 3.029,40 EUR folgt aus keiner Definition dieser Seite.
    """
    ergebnis = tco_24(_buendel(tarif_monatlich=None, geraet_monatsrate=None,
                               buendel_monatlich=44.99, laufzeit_monate=36,
                               geraet_zuzahlung=360.0, anschlusspreis=39.9))
    assert ergebnis.gesamt == 2019.54
    # DER ZEITRAUM STEHT AM DATENSATZ - jeder Leser nimmt ihn von hier.
    assert ergebnis.leitzahl_monate == 36
    assert ergebnis.monatlich == 56.1          # 2.019,54 / 36
    assert ergebnis.monatlich != 84.15, "das ist 2.019,54 / 24 (der Befund)"
    # Die Gegenrechnung, die auf JEDER Zeile aufgehen muss: Ø x Zeitraum
    # ist die Summe (eine Cent-Rundung je Monat erlaubt).
    assert abs(ergebnis.monatlich * ergebnis.leitzahl_monate
               - ergebnis.gesamt) <= ergebnis.leitzahl_monate * 0.01


def test_ohne_gemessene_laufzeit_gibt_es_keinen_monatsschnitt():
    """Ein Teiler 24 waere geraten (Clean Code 3): ohne Laufzeit bleiben
    Zeitraum UND Ø/Monat `None`, und die Kennzahl ist unbelastbar."""
    ergebnis = tco_24(_buendel(tarif_monatlich=None, geraet_monatsrate=None,
                               buendel_monatlich=44.99,
                               laufzeit_monate=None))
    assert POSTEN_LAUFZEIT in ergebnis.luecken
    assert ergebnis.leitzahl_monate is None
    assert ergebnis.monatlich is None
    assert ergebnis.belastbar is False


def test_nur_die_geraeteseite_ergibt_die_721_euro_des_auftrags():
    """`1 € + 24 x 30 € = 721 €`, nachvollziehbar in den Bestandteilen."""
    ergebnis = tco_24(_buendel(tarif_monatlich=None, anschlusspreis=None))
    assert ergebnis.bestandteile["Gerätezuzahlung"] == _ANZAHLUNG
    assert ergebnis.bestandteile["Geräteraten über 24 Monate"] == 720.0
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


def test_36_raten_zaehlen_alle_und_der_rest_steht_daneben():
    """§ 6.3 und A1: Wer 36 Raten schuldet, hat nach 24 Monaten noch zwoelf
    offen - und auch die bleiben Kosten. Die Leitzahl rechnet ALLE 36 in
    die Zahl, der offene Teil steht zusaetzlich daneben."""
    ergebnis = tco_24(_buendel(laufzeit_monate=36))
    assert ergebnis.bestandteile["Geräteraten über 36 Monate"] == 1080.0
    assert ergebnis.restbetrag == 360.0, "12 offene Raten a 30 EUR"
    assert ergebnis.gesamt == 1840.75, "alle Raten in der Leitzahl"


def test_eine_kuerzere_ratenlaufzeit_hat_keinen_rest():
    ergebnis = tco_24(_buendel(laufzeit_monate=12))
    assert ergebnis.bestandteile["Geräteraten über 12 Monate"] == 360.0
    assert ergebnis.restbetrag == 0.0


def test_ein_buendelmonatspreis_binnen_24_monaten_hat_keinen_rest():
    b = Buendel(sku_id="apple-iphone-14-128gb-mitternacht", anbieter="1&1",
               tarif_name="1&1 Allnet Flat", tarif_id="einsundeins:allnet",
               tarif_id_guete="hoch", buendel_monatlich=44.99,
               laufzeit_monate=24, quelle_url="https://www.1und1.de/x",
               abgerufen_am="2026-09-03")
    ergebnis = tco_24(b)
    assert ergebnis.bestandteile == {
        "Bündelpreis (Tarif und Gerät zusammen) über 24 Monate": 1079.76,
    }
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
# A1 (20.09.2026): die Leitzahl heisst "Kosten ueber 24 Monate" und rechnet
# ALLE Geräteraten hinein - auch die Restschuld nach Monat 24.
#
#   Kosten über 24 Monate = Anzahlung + 24 Monate Tarif (phasengewichtet,
#   wenn das Pflichtdokument Preisphasen nennt) + alle Geräteraten der
#   eigenen Laufzeit + Anschlusspreis
#
# Bis dahin kappte `tco_24` die Raten bei 24 Monaten - der CHECK24-Vorwurf
# aus § 5.4 der Strategie, nur mit einem Ausweis daneben. Die Restschuld
# ist keine Fussnote mehr, sondern Teil der Zahl: wer 36 Raten schuldet,
# hat nach 24 Monaten noch 12 offen, und auch die gehoeren in die Kosten
# ueber 24 Monate (als noch GESCHULDETER Betrag, siehe `restbetrag`).
# --------------------------------------------------------------------------

def test_der_pflichtfall_des_auftrags_congstar_xs_ergibt_1459_euro():
    """A1, wortgerecht: congstar Allnet Flat XS zum iPhone 17 Pro 256 GB -
    1 € Anzahlung, 15 € Tarif, 36 Raten à 30,50 €, kein Anschlusspreis.

        1 + 24 × 15,00 + 36 × 30,50 + 0 = 1.459,00 €

    Der bis dahin gueltige Wert 1.093,00 € (24 statt 36 Raten gerechnet)
    darf nie wieder als Leitzahl auftauchen - er stand als "günstig mit
    Tarif" in der Antwortzeile und unterbot damit jedes echte Angebot."""
    b = _buendel(anbieter="congstar", tarif_name="Allnet Flat XS",
                 tarif_id="congstar:allnet-flat-xs", tarif_monatlich=15.0,
                 geraet_zuzahlung=1.0, geraet_monatsrate=30.5,
                 laufzeit_monate=36, anschlusspreis=0.0,
                 sku_id="apple-iphone-17-pro-256gb-cosmic-orange")
    ergebnis = tco_24(b)
    assert ergebnis.gesamt == 1459.0
    assert ergebnis.bestandteile == {
        "Tarif über 24 Monate": 360.0,
        "Gerätezuzahlung": 1.0,
        "Geräteraten über 36 Monate": 1098.0,
        "Anschlusspreis": 0.0,
    }
    # Die Restschuld ist IN der Leitzahl und zusaetzlich ausgewiesen:
    # 12 Raten à 30,50 € sind nach Monat 24 noch zu zahlen.
    assert ergebnis.restbetrag == 366.0
    assert round(ergebnis.gesamt - ergebnis.restbetrag, 2) == 1093.0
    assert ergebnis.monatlich == 60.79          # 1.459,00 / 24


def test_tarifphasen_werden_phasengewichtet_gerechnet():
    """Ein Tarif mit Preisphasen ("12 Monate 10 €, danach 20 €") wird
    phasengewichtet gerechnet: 12 × 10 + 12 × 20 = 360 € statt flach
    24 × 20 = 480 €. Die Phase ist die Aussage des Pflichtdokuments, die
    flat-Multiplikation waere unsere Erfindung dagegen."""
    phasen = [Preisphase(von_monat=1, bis_monat=12, betrag=10.0),
              Preisphase(von_monat=13, bis_monat=None, betrag=20.0)]
    ergebnis = tco_24(_buendel(tarif_monatlich=20.0, tarif_phasen=phasen))
    assert ergebnis.bestandteile["Tarif über 24 Monate"] == 360.0
    assert ergebnis.gesamt == 1120.99          # 1 + 360 + 720 + 39,99
    # Ohne Phasen gilt derselbe Tarifpreis flach - die Gegenprobe.
    flat = tco_24(_buendel(tarif_monatlich=20.0))
    assert flat.bestandteile["Tarif über 24 Monate"] == 480.0


def test_ein_buendelmonatspreis_zaehlt_alle_laufzeitmonate():
    """1&1 nennt EINEN Monatsbetrag fuer Tarif und Geraet (§ 13.2) - auch
    er laeuft 36 Monate, und alle 36 zaehlen: 36 × 44,99 = 1.619,64 €.
    Die Kappung auf 24 (1.079,76 €) waere wieder die CHECK24-Zahl."""
    b = Buendel(sku_id="apple-iphone-14-128gb-mitternacht", anbieter="1&1",
                tarif_name="1&1 Allnet Flat", tarif_id="einsundeins:allnet",
                tarif_id_guete="hoch", buendel_monatlich=44.99,
                laufzeit_monate=36, quelle_url="https://www.1und1.de/x",
                abgerufen_am="2026-09-03")
    ergebnis = tco_24(b)
    assert ergebnis.bestandteile == {
        "Bündelpreis (Tarif und Gerät zusammen) über 36 Monate": 1619.64,
    }
    assert ergebnis.gesamt == 1619.64
    assert ergebnis.restbetrag == 539.88, "12 Monate à 44,99 laufen weiter"


def test_phasensumme_wohnt_im_modul_der_leitzahl():
    """A1: `phasensumme` ist aus `report/effektivpreis.py` hierher gezogen
    - die Leitzahl und der Effektivpreis teilen EINE phasengewichtete
    Summe, sonst rechneten zwei Stellen dasselbe Blatt verschieden."""
    assert phasensumme([Preisphase(1, 12, 10.0),
                        Preisphase(13, None, 20.0)], 24) == 360.0
    assert phasensumme([Preisphase(1, 6, 9.99)], 24) == \
        round(6 * 9.99 + 18 * 9.99, 2)
    assert phasensumme([], 24) is None


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


def test_keine_differenz_ueber_zwei_verschiedene_zeitraeume():
    """P0-B-h1: dasselbe Tor wie jeder andere Vergleich.

    Ein Buendelmonatspreis ueber 36 Monate gegen eine SIM-only-Referenz
    ueber 24 Monate: die Differenz waere zum Teil der Laufzeitunterschied
    und nicht der Geraetepreis. Sie bleibt `None`, der Grund steht
    benannt daneben.

    ROT GEGEN DEN ALTEN STAND: bis hierher zog `geraeteanteil` die zwei
    Summen ohne Tor voneinander ab. Am Bestand vom 21.09.2026 traf das 74
    Buendel (1&1 All-Net-Flat S, iPhone 15 128 GB: 1.447,54 - 379,66 =
    1.067,88 EUR "Geraeteanteil", darin zwoelf Tarifmonate).
    """
    ergebnis = geraeteanteil(
        _buendel(tarif_monatlich=None, geraet_monatsrate=None,
                 buendel_monatlich=44.99, laufzeit_monate=36,
                 geraet_zuzahlung=360.0),
        _referenz())
    assert ergebnis.tco_buendel == 2019.63     # 360 + 36 x 44,99 + 39,99
    assert ergebnis.tco_sim_only == 519.75     # 24 x 19,99 + 39,99
    assert UNGLEICHER_ZEITRAUM in ergebnis.luecken
    assert ergebnis.betrag is None
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
    Geraetepreis.

    Seit dem 04.09.2026 entscheidet der `tarif_id`, nicht der Name - der
    Name ist, was auf der jeweiligen Seite stand, die ID ist der
    aufgeloeste Fremdschluessel.
    """
    with pytest.raises(ValueError, match="Tarifen"):
        geraeteanteil(_buendel(), _referenz(tarif_id="o2:o2-mobile-l",
                                            tarif_name="o2 Mobile L"))


def test_die_live_shop_lesart_ist_derselbe_tarif():
    """B2-Befund vom 08.09.2026 (Telekom): Die SIM-only-Referenz kommt aus
    der Shop-Kachel (`…#live_shop` - die Dublettenregel in
    `tarif_referenzen.aus_bestand` laesst die Live-Lesart vorn), das
    Buendel loest auf den PIB-Eintrag ohne Zusatz. Dieselbe Zeitreihen-
    Basis, derselbe Tarif - vorher warf genau diese Paarung, und der
    Auffangboden des Renderers machte daraus fuenf leere Reiter statt
    einen Geraeteanteil (Render-Log: "Geraetedaten nicht aufbereitbar").
    """
    ergebnis = geraeteanteil(
        _buendel(anbieter="Telekom", tarif_name="MagentaMobil L",
                 tarif_id="telekom:magentamobil-l"),
        _referenz(anbieter="Telekom", tarif_name="MagentaMobil L",
                  tarif_id="telekom:magentamobil-l#live_shop"))
    assert ergebnis.betrag is not None
    assert ergebnis.belastbar is True


def test_ein_hash_zusatz_bleibt_ein_fremder_tarif():
    """Gegenprobe zur Live-Lesart: Ein HASH-Zusatz an der tarif_id trennt
    zwei gleichnamige, VERSCHIEDENE Produkte (o2-home-l-flex und
    o2-home-l-175-flex, CLAUDE.md § 6) - er wird NICHT mitgestrichen,
    sonst maesse die Differenz zwei Vertrage gegeneinander."""
    with pytest.raises(ValueError, match="Tarifen"):
        geraeteanteil(
            _buendel(tarif_id="o2:o2-home-l-flex"),
            _referenz(tarif_id="o2:o2-home-l-flex#8f3a1c"))


def test_zwei_namen_fuer_denselben_tarif_rechnen_trotzdem():
    """Der Fall, wegen dem die Regel auf die ID umgestellt wurde.

    o2 nennt denselben Tarif im Geraetekatalog "O2 Mobile on Demand M Plus
    mit 50 GB+ (24 Mon.)" und in der SIM-only-Kachel "O2 Mobile on Demand
    M". Ueber den Namen verglichen waeren das zwei Tarife, und der
    Geraeteanteil - die Zahl, wegen der dieses Modul existiert - bliebe
    fuer JEDES o2-Buendel leer.
    """
    ergebnis = geraeteanteil(
        _buendel(tarif_name="O2 Mobile on Demand M Plus mit 50 GB+ (24 Mon.)"),
        _referenz(tarif_name="O2 Mobile on Demand M"))
    assert ergebnis.betrag is not None
    # Gegenprobe, dass der Fall ohne die Regel wirklich eintraete: ohne IDs
    # auf beiden Seiten faellt derselbe Aufruf wieder auf den Namen zurueck.
    with pytest.raises(ValueError, match="Tarifen"):
        geraeteanteil(
            _buendel(tarif_id="",
                     tarif_name="O2 Mobile on Demand M Plus mit 50 GB+"),
            _referenz(tarif_id="", tarif_name="O2 Mobile on Demand M"))


def test_ohne_ids_bleibt_der_name_die_pruefung():
    """Der Rueckfall fuer Saetze, die keinen Fremdschluessel tragen."""
    ergebnis = geraeteanteil(_buendel(tarif_id=""), _referenz(tarif_id=""))
    assert ergebnis.betrag is not None
    # Eine HALB gefuellte Paarung faellt ebenfalls auf den Namen zurueck -
    # ein Vergleich "ID gegen nichts" waere immer ungleich und schaltete
    # den Geraeteanteil stillschweigend ab.
    ergebnis = geraeteanteil(_buendel(), _referenz(tarif_id=""))
    assert ergebnis.betrag is not None


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
                      "o2 Mobile M", 36) == \
        "buendel--o2--apple-iphone-14-128gb-mitternacht--o2-mobile-m--36m"
    assert sim_only_id("o2", "o2 Mobile M") == "simonly--o2--o2-mobile-m"


def test_eine_fehlende_angabe_steht_offen_in_der_id():
    assert buendel_id("", "o2", "o2 Mobile M",
                      24).split("--")[2] == "ohne-geraet"
    assert sim_only_id("o2", "").endswith("--ohne-tarif")


def test_eine_fehlende_laufzeit_steht_offen_in_der_id():
    """B1: die Laufzeit gehoert in den Schluessel - fehlt sie, sagt die ID
    das, statt eine 24 zu raten. Eine geratene 24 verschmolze
    ein Angebot unbekannter Laufzeit mit dem echten 24-Monats-Angebot."""
    ohne = buendel_id("apple-iphone-14-128gb-mitternacht", "o2",
                      "o2 Mobile M", None)
    assert ohne.endswith("--" + LAUFZEIT_LUECKE)
    assert ohne != buendel_id("apple-iphone-14-128gb-mitternacht", "o2",
                              "o2 Mobile M", 24)
    # Auch eine unmoegliche Laufzeit wird benannt, nicht gerundet.
    assert buendel_id("x", "o2", "M", 0).endswith("--" + LAUFZEIT_LUECKE)


@pytest.mark.parametrize("wert", [24.5, "24,5", 23.9, -3, 0, "ohne Angabe",
                                  True, None])
def test_was_keine_ganze_monatszahl_ist_wird_benannt_nicht_gerundet(wert):
    """Befund 3 (P0-B-fix1): Docstring und Code decken sich wieder.

    `laufzeit_segment` kuendigt seit B1 an, eine Zahl, die keine Laufzeit
    sein kann - "0, negativ, kein Ganzes" -, werde benannt. Fuer 0 und
    negativ traf das zu; fuer "kein Ganzes" nicht: `int(24.5)` schnitt
    still auf 24 ab, und ein Angebot mit 24,5 Monaten Ratenlauf landete
    damit auf dem Schluessel des echten 24-Monats-Angebots - genau der
    Schaden, den das Segment verhindern soll.
    """
    assert laufzeit_in_monaten(wert) is None
    assert laufzeit_segment(wert) == LAUFZEIT_LUECKE
    assert buendel_id("x", "o2", "M", wert).endswith("--" + LAUFZEIT_LUECKE)
    assert buendel_id("x", "o2", "M", wert) != buendel_id("x", "o2", "M", 24)


@pytest.mark.parametrize("wert,monate", [(24, 24), (36, 36), ("12", 12),
                                         (24.0, 24), (1, 1)])
def test_eine_ganze_monatszahl_bleibt_die_laufzeit(wert, monate):
    """Die Gegenprobe: was eine Laufzeit IST, wird nicht zur Luecke.

    Ohne diese Zeilen waere die Pruefung oben auch mit einer Funktion
    gruen, die jede Eingabe verwirft."""
    assert laufzeit_in_monaten(wert) == monate
    assert laufzeit_segment(wert) == f"{monate}m"


def test_ein_buendel_ohne_laufzeit_traegt_die_luecke_statt_einer_zahl():
    """Befund 2 (P0-B-fix1) am Datensatz: keine Vorgabe von 24 mehr.

    `Buendel.laufzeit_monate` hatte bis hierher den Vorgabewert
    `STANDARD_LAUFZEIT = 24`. Ein Satz, dessen Quelle die Dauer nicht
    nennt (1&1, wenn die Produktseite sie weglaesst), bekam damit eine
    geratene Laufzeit - im Schluessel UND in der Kennzahl: 24 x 34,00 EUR
    = 816,00 EUR Geraeteraten, die niemand gemessen hat.

    Jetzt fehlt der Posten als BENANNTE Luecke, die Kennzahl ist
    unbelastbar, und die Karte sagt das (Regel 9).
    """
    ohne = Buendel(sku_id="apple-iphone-17-256gb-schwarz", anbieter="1&1",
                   tarif_name="Allnet Flat M", tarif_id="einsundeins:m",
                   tarif_monatlich=20.0, geraet_zuzahlung=0.0,
                   geraet_monatsrate=34.0, anschlusspreis=39.99)
    assert ohne.laufzeit_monate is None
    assert ohne.id.endswith("--" + LAUFZEIT_LUECKE)
    # Die Ratenzahlung ist ohne ihre Monatszahl kein Ratengeschaeft.
    assert ohne.geraeteraten is None

    tco = tco_24(ohne)
    assert POSTEN_LAUFZEIT in tco.luecken
    # Die RATE ist gemessen - benannt wird deshalb die Laufzeit, nicht sie.
    assert POSTEN_RATE not in tco.luecken
    assert not tco.belastbar
    assert tco.restbetrag is None
    assert all("Geräteraten" not in name for name in tco.bestandteile)
    # 20,00 x 24 Tarif + 0,00 Zuzahlung + 39,99 Anschluss = 519,99 EUR;
    # die 816,00 EUR geratener Raten sind NICHT darin.
    assert tco.gesamt == pytest.approx(519.99, abs=0.005)

    kennzahl = tco_bindung(ohne)
    assert POSTEN_LAUFZEIT in kennzahl.luecken
    assert not kennzahl.belastbar
    assert kennzahl.raten_laufzeit is None


def test_ein_buendelmonatspreis_ohne_laufzeit_ergibt_keine_summe():
    """Dieselbe Regel in der 1&1-Form: EIN Monatsbetrag, keine Monatszahl.

    Hier haengt der GANZE Monatsblock an der Laufzeit - der Buendelpreis
    steht anstelle von Tarif UND Rate. Mit der geratenen 24 stand
    44,99 x 24 = 1079,76 EUR in der Leitzahl; uebrig bleiben ohne sie nur
    Zuzahlung und Anschlusspreis, und die duerfen nicht als "Kosten über
    24 Monate" durchgehen.
    """
    ohne = Buendel(sku_id="apple-iphone-17-256gb-schwarz", anbieter="1&1",
                   tarif_name="Allnet Flat M", tarif_id="einsundeins:m",
                   buendel_monatlich=44.99, geraet_zuzahlung=360.0,
                   anschlusspreis=39.99)
    tco = tco_24(ohne)
    assert POSTEN_LAUFZEIT in tco.luecken
    assert not tco.belastbar
    assert tco.gesamt == pytest.approx(399.99, abs=0.005)
    assert tco.restbetrag is None
    kennzahl = tco_bindung(ohne)
    assert POSTEN_LAUFZEIT in kennzahl.luecken
    assert not kennzahl.belastbar
    assert kennzahl.bindung is None
    # `tco_bindung` fuehrt die Zuzahlung der Buendelform nicht als Posten
    # (eigener Befund, nicht dieser hier) - uebrig bleibt der
    # Anschlusspreis. Entscheidend ist, dass die 1079,76 EUR der
    # geratenen 24 Monate NICHT darin stehen.
    assert kennzahl.gezahlt_nach_24 == pytest.approx(39.99, abs=0.005)


@pytest.mark.parametrize("wert", [0, -12, 24.5, "ohne Angabe"])
def test_eine_unmoegliche_laufzeit_wirft_statt_zur_luecke_zu_werden(wert):
    """FEHLT ist eine Luecke, UNMOEGLICH ist ein Nutzlastfehler.

    `aus_rohsaetzen` faengt die Ausnahme, zaehlt den Satz als `ungueltig`
    und protokolliert ihn - sie stumm zur Luecke zu machen waere ein
    `except` ohne Weitergabe (CLAUDE.md, Clean Code 5). Bis P0-B-fix1
    wurde 24,5 hier still auf 24 abgeschnitten.
    """
    with pytest.raises(ValueError, match="laufzeit_monate"):
        Buendel(sku_id="x", anbieter="o2", tarif_name="M",
                tarif_monatlich=20.0, laufzeit_monate=wert)


def test_zwei_ratenlaufzeiten_zum_selben_tarif_sind_zwei_buendel():
    """B1, der Kern: Telekom finanziert 6/12/24/36, o2 und congstar 24/36.
    Ohne die Laufzeit im Schluessel ueberschrieben sich diese Varianten
    gegenseitig - der Bestand zeigte willkuerlich eine von ihnen."""
    sku = "apple-iphone-17-256gb-schwarz"
    kurz = Buendel(sku_id=sku, anbieter="congstar",
                   tarif_name="Allnet Flat M", tarif_id="congstar:m",
                   tarif_monatlich=22.0, geraet_zuzahlung=97.0,
                   geraet_monatsrate=50.25, laufzeit_monate=24)
    lang = Buendel(sku_id=sku, anbieter="congstar",
                   tarif_name="Allnet Flat M", tarif_id="congstar:m",
                   tarif_monatlich=22.0, geraet_zuzahlung=97.0,
                   geraet_monatsrate=33.50, laufzeit_monate=36)
    assert kurz.id != lang.id
    assert kurz.id.endswith("--24m") and lang.id.endswith("--36m")
    # Und der laufzeitfreie Teil ist derselbe: es ist DASSELBE Angebot in
    # zwei Zahlweisen.
    assert buendel_id_ohne_laufzeit(kurz.id) == \
        buendel_id_ohne_laufzeit(lang.id)


def test_die_lesemigration_haelt_eine_alte_id_am_selben_buendel():
    """Der Altbestand (vier Segmente) wird beim LESEN zugeordnet, nicht
    umgeschrieben - ueber `laufzeit_monate`, das jede Zeile traegt."""
    alt = "buendel--o2--apple-iphone-14-128gb-mitternacht--o2-mobile-m"
    assert buendel_id_aktuell(alt, 36) == \
        buendel_id("apple-iphone-14-128gb-mitternacht", "o2",
                   "o2 Mobile M", 36)
    # Eine ID, die das Segment schon traegt, bleibt unveraendert.
    heute = buendel_id("apple-iphone-14-128gb-mitternacht", "o2",
                       "o2 Mobile M", 36)
    assert buendel_id_aktuell(heute, 36) == heute
    # Eine fehlende Laufzeit am Altsatz wird benannt, nicht geraten.
    assert buendel_id_aktuell(alt, None).endswith("--" + LAUFZEIT_LUECKE)
    # Und eine Form, die weder alt noch neu ist, wird NICHT erfunden.
    assert buendel_id_aktuell("o2--apple-iphone-14", 24) is None
    assert buendel_id_aktuell("", 24) is None


def test_keine_neue_id_kann_eine_listung_id_treffen():
    """Nicht dem Zufall ueberlassen, sondern der Form: eine `listung_id` hat
    zwei Bestandteile, ein Buendel seit B1 fuenf (vorher vier), eine
    Referenz drei - auch bei einem Anbieter, der wirklich "Buendel" hiesse."""
    sku = "apple-iphone-14-128gb-mitternacht"
    ids = [listung_id(sku, "o2"), listung_id(sku, "Buendel"),
           listung_id(sku, "SIM only"),
           buendel_id(sku, "o2", "o2 Mobile M", 36),
           sim_only_id("o2", "o2 Mobile M")]
    assert len(set(ids)) == len(ids)
    assert [len(i.split("--")) for i in ids] == [2, 2, 2, 5, 3]


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


def test_der_scope_veraendert_und_loescht_keine_fremdanbieter(tmp_path):
    """Befund Runde 2 (15.09.2026): ein Lauf EINES Anbieters datierte 35
    Fremd-Referenzen. Der Scope schraenkt AUFFRISCHEN und WEGNEHMEN auf
    seinen Anbieter ein - ein fremder Bestandssatz bleibt bytegleich
    stehen, auch wenn er in der Ersetzungsmenge fehlt. Gegenprobe im
    selben Test: ohne Scope loescht dieselbe Menge ihn (dokumentierte
    Ersetzungs-Semantik)."""
    db = TcoDB(tmp_path / "geraete_tco.json")
    telekom = _referenz(
        anbieter="Telekom", tarif_name="MagentaMobil L",
        tarif_id="telekom:magentamobil-l",
        quelle_url="https://www.telekom.de/pib/magentamobil-l",
        tarif_sim_only_monatlich=59.95)
    db.setze_referenzen([_referenz(), telekom], "2026-09-14")
    fremd_vorher = {r["id"]: r for r in db.referenzen()}[_referenz().id]

    # Scoped-Ersetzung NUR mit dem Telekom-Satz in der Menge - die o2-
    # Referenz fehlt, darf dadurch weder datiert noch entfernt werden.
    _, entfernt = db.ersetze_referenzen(
        [_referenz(
            anbieter="Telekom", tarif_name="MagentaMobil L",
            tarif_id="telekom:magentamobil-l",
            quelle_url="https://www.telekom.de/pib/magentamobil-l",
            tarif_sim_only_monatlich=49.95)],
        "2026-09-15", anbieter={"Telekom"})
    nachher = {r["id"]: r for r in db.referenzen()}
    assert entfernt == 0
    assert nachher[_referenz().id] == fremd_vorher
    assert nachher[telekom.id]["last_verified"] == "2026-09-15"
    assert nachher[telekom.id]["tarif_sim_only_monatlich"] == 49.95

    # Gegenprobe: OHNE Scope loescht dieselbe Menge den Fremden -
    # genau deshalb gehoert der Scope in jeden Einzelanbieter-Lauf.
    _, entfernt_ohne = db.ersetze_referenzen([telekom], "2026-09-15")
    assert entfernt_ohne == 1
    assert _referenz().id not in {r["id"] for r in db.referenzen()}


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
