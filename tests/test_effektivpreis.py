"""Effektivpreis und Positionskarte.

Der wichtigste Test ist `test_rabattphasen_ergeben_den_durchschnitt`: er
haelt den Fall fest, wegen dem es dieses Modul gibt.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from telco_radar.report import tarife_view
from telco_radar.report.effektivpreis import (
    VERGLEICHSMONATE, phasensumme, rechne, regression,
)
from telco_radar.tarif_model import Preisphase, Tarif


def _tarif(**kw) -> Tarif:
    t = Tarif(anbieter="Telekom", name="Testtarif", laufzeit_monate=24)
    for k, v in kw.items():
        setattr(t, k, v)
    if not t.preisphasen and t.grundgebuehr is not None:
        t.preisphasen = [Preisphase(1, None, t.grundgebuehr)]
    return t


# --------------------------------------------------------------------------- #
# Der Fall, wegen dem es dieses Modul gibt
# --------------------------------------------------------------------------- #

def test_rabattphasen_ergeben_den_durchschnitt():
    """"6 Monate 9,99 €, danach 29,99 €" ist weder 9,99 € noch 29,99 €.

    (6 x 9,99 + 18 x 29,99) / 24 = 599,76 / 24 = 24,99.
    Genau dieser Aufbau macht die Angebote dieses Marktes unvergleichbar.
    """
    t = _tarif(grundgebuehr=29.99, preisphasen=[
        Preisphase(1, 6, 9.99), Preisphase(7, None, 29.99)])
    e = rechne(t, cashback=0, wechselbonus=0)
    assert e.monatlich == 24.99


def test_phasensumme_rechnet_gewichtet():
    assert phasensumme([Preisphase(1, 6, 9.99),
                        Preisphase(7, None, 29.99)], 24) == 599.76


def test_beworbener_preis_ist_nicht_der_effektivpreis():
    """Absicherung gegen die naheliegende Abkuerzung: die erste Phase nehmen."""
    t = _tarif(grundgebuehr=29.99, preisphasen=[
        Preisphase(1, 6, 9.99), Preisphase(7, None, 29.99)])
    e = rechne(t, cashback=0, wechselbonus=0)
    assert e.monatlich != 9.99 and e.monatlich != 29.99


def test_drei_phasen():
    t = _tarif(preisphasen=[Preisphase(1, 3, 0.0), Preisphase(4, 12, 19.99),
                            Preisphase(13, None, 39.99)])
    # 3x0 + 9x19,99 + 12x39,99 = 179,91 + 479,88 = 659,79 -> 27,49
    e = rechne(t, cashback=0, wechselbonus=0)
    assert e.monatlich == 27.49


def test_phase_ueber_den_horizont_hinaus_wird_gekappt():
    assert phasensumme([Preisphase(1, 36, 10.0)], 24) == 240.0


def test_luecke_in_den_phasen_laeuft_zum_letzten_preis_weiter():
    """Eine Phase, die den Horizont nicht ausfuellt: der letzte bekannte
    Preis ist der Normalpreis, nicht der Rabattpreis."""
    assert phasensumme([Preisphase(1, 12, 10.0)], 24) == 240.0


# --------------------------------------------------------------------------- #
# Einmalkosten und der gemeinsame Nenner
# --------------------------------------------------------------------------- #

def test_anschlusspreis_verteilt_sich_auf_den_horizont():
    t = _tarif(grundgebuehr=20.0, anschlusspreis=48.0)
    e = rechne(t, cashback=0, wechselbonus=0)
    assert e.monatlich == 22.0


def test_boni_werden_abgezogen():
    t = _tarif(grundgebuehr=20.0, anschlusspreis=0.0)
    e = rechne(t, cashback=120.0, wechselbonus=0)
    assert e.monatlich == 15.0


def test_geraetezuzahlung_zaehlt_mit():
    t = _tarif(grundgebuehr=20.0, anschlusspreis=0.0)
    e = rechne(t, cashback=0, wechselbonus=0, geraetezuzahlung=240.0)
    assert e.monatlich == 30.0


def test_flex_tarif_rechnet_gegen_denselben_horizont():
    """Nicht weil ein Flex-Tarif 24 Monate laeuft, sondern weil ein Vergleich
    einen gemeinsamen Nenner braucht. Wer den Horizont je Tarif aus der
    Laufzeit nimmt, vergleicht zwei verschiedene Rechnungen."""
    flex = rechne(_tarif(grundgebuehr=20.0, laufzeit_monate=0,
                         anschlusspreis=48.0), cashback=0, wechselbonus=0)
    fest = rechne(_tarif(grundgebuehr=20.0, laufzeit_monate=24,
                         anschlusspreis=48.0), cashback=0, wechselbonus=0)
    assert flex.monatlich == fest.monatlich == 22.0
    assert flex.horizont == VERGLEICHSMONATE


# --------------------------------------------------------------------------- #
# Fehlt etwas, ist es eine Luecke - keine Null
# --------------------------------------------------------------------------- #

def test_fehlender_anschlusspreis_ist_eine_luecke():
    """"Nicht bekannt" und "kostenlos" sind zwei verschiedene Aussagen, und
    nur eine davon ist belegt."""
    e = rechne(_tarif(grundgebuehr=20.0))
    assert "Anschlusspreis" in e.luecken
    assert "Anschlusspreis" not in e.bestandteile


def test_fehlende_boni_sind_eine_luecke():
    e = rechne(_tarif(grundgebuehr=20.0, anschlusspreis=0.0))
    assert "Cashback/Wechselbonus" in e.luecken


def test_ohne_preis_ist_die_zahl_keine_aussage():
    e = rechne(_tarif(grundgebuehr=None, preisphasen=[]))
    assert not e.belastbar
    assert "Grundpreis" in e.luecken


def test_vollstaendiger_tarif_ist_belastbar():
    e = rechne(_tarif(grundgebuehr=20.0, anschlusspreis=0.0),
               cashback=0, wechselbonus=0)
    assert e.belastbar and e.luecken == []


# --------------------------------------------------------------------------- #
# Die drei Werte: der Preis allein reicht nicht
# --------------------------------------------------------------------------- #

def test_preis_je_gb_wird_ausgewiesen():
    e = rechne(_tarif(grundgebuehr=20.0, anschlusspreis=0.0,
                      datenvolumen_gb=10.0), cashback=0, wechselbonus=0)
    assert e.preis_je_gb == 2.0


def test_drosselung_erscheint_als_merkmal():
    """Ohne dieses Merkmal waere eine Rangliste nach Effektivpreis eine
    Rangliste der Drosselung."""
    e = rechne(_tarif(grundgebuehr=10.0, datenvolumen_gb=5.0,
                      drossel_down=64.0))
    drossel = [f for f in e.flags if f.schluessel == "drossel"]
    assert drossel and drossel[0].gut is False
    assert "64 KBit/s" in drossel[0].text


def test_milde_drosselung_gilt_nicht_als_schlecht():
    """Unter 1 MBit/s ist der Unterschied zwischen "langsamer" und "vorbei"."""
    e = rechne(_tarif(grundgebuehr=10.0, drossel_down=2000.0))
    drossel = [f for f in e.flags if f.schluessel == "drossel"][0]
    assert drossel.gut is True and "2 MBit/s" in drossel.text


def test_bindung_und_unbegrenzt_erscheinen_als_merkmal():
    flex = rechne(_tarif(grundgebuehr=10.0, laufzeit_monate=0,
                         datenvolumen_gb=float("inf")))
    texte = [f.text for f in flex.flags]
    assert "Ohne Mindestlaufzeit" in texte
    assert "Unbegrenztes Datenvolumen" in texte


def test_volumenautomatik_erscheint_als_merkmal():
    e = rechne(_tarif(grundgebuehr=10.0,
                      volumen_automatik="Volumen steigt alle 12 Monate um 5 GB"))
    assert any(f.schluessel == "automatik" for f in e.flags)


def test_unbegrenzt_ergibt_preis_je_gb_null():
    e = rechne(_tarif(grundgebuehr=20.0, anschlusspreis=0.0,
                      datenvolumen_gb=float("inf")), cashback=0, wechselbonus=0)
    assert e.preis_je_gb == 0.0


# --------------------------------------------------------------------------- #
# Die Fair-Value-Linie
# --------------------------------------------------------------------------- #

def test_regression_findet_die_gerade():
    a, b = regression([(0.0, 1.0), (1.0, 3.0), (2.0, 5.0)])
    assert round(a, 3) == 1.0 and round(b, 3) == 2.0


def test_regression_braucht_drei_punkte():
    assert regression([(1.0, 2.0), (2.0, 4.0)]) is None


def test_senkrechte_wolke_ergibt_keine_gerade():
    """Alle Tarife mit demselben Volumen: dort gibt es keine Aussage."""
    assert regression([(10.0, 1.0), (10.0, 2.0), (10.0, 3.0)]) is None


def test_regression_ignoriert_unendlich():
    assert regression([(0.0, 1.0), (1.0, 3.0), (2.0, 5.0),
                       (float("inf"), 9.0)]) is not None


# --------------------------------------------------------------------------- #
# Die Seite
# --------------------------------------------------------------------------- #

def _state(tmp_path: Path, saetze: list[dict]) -> Path:
    p = tmp_path / "tarife.jsonl"
    p.write_text("\n".join(json.dumps(s, ensure_ascii=False) for s in saetze),
                 encoding="utf-8")
    return p


def _satz(tid: str, anbieter: str, name: str, preis: float, gb, **kw) -> dict:
    d = {"tarif_id": tid, "anbieter": anbieter, "name": name,
         "grundgebuehr": preis, "datenvolumen_gb": gb, "laufzeit_monate": 24,
         "anschlusspreis": 0.0,
         "preisphasen": [{"von_monat": 1, "bis_monat": None, "betrag": preis}]}
    d.update(kw)
    return d


def test_view_nimmt_den_juengsten_stand(tmp_path):
    p = _state(tmp_path, [_satz("t:a", "Telekom", "A", 20.0, 10.0),
                          _satz("t:a", "Telekom", "A", 25.0, 10.0)])
    view = tarife_view.aufbereiten(p, [])
    assert len(view["zeilen"]) == 1
    assert view["zeilen"][0]["grundgebuehr"] == 25.0


def test_view_sortiert_nach_effektivpreis(tmp_path):
    p = _state(tmp_path, [_satz("t:teuer", "Telekom", "Teuer", 50.0, 20.0),
                          _satz("t:billig", "o2", "Billig", 10.0, 5.0)])
    view = tarife_view.aufbereiten(p, [])
    assert [z["name"] for z in view["zeilen"]] == ["Billig", "Teuer"]


def test_unbegrenzte_tarife_stehen_nicht_in_der_wolke(tmp_path):
    """Ein Tarif ohne Volumengrenze hat auf einer Volumenachse keinen Ort.
    Ihn ans rechte Ende zu setzen waere eine erfundene Zahl - und sie zoege
    die Ausgleichsgerade mit."""
    p = _state(tmp_path, [
        _satz("t:a", "Telekom", "A", 20.0, 10.0),
        _satz("t:b", "o2", "B", 30.0, 20.0),
        _satz("t:c", "Telekom", "C", 40.0, 40.0),
        _satz("t:u", "o2", "Unlimited", 50.0, None, datenvolumen_gb=None),
    ])
    # Unendlich kommt aus JSON nicht heil zurueck - der Extraktor setzt inf,
    # json macht daraus Infinity. Hier direkt gesetzt:
    saetze = json.loads("[" + ",".join(
        p.read_text(encoding="utf-8").splitlines()) + "]")
    saetze[-1]["datenvolumen_gb"] = float("inf")
    p.write_text("\n".join(json.dumps(s) for s in saetze), encoding="utf-8")

    view = tarife_view.aufbereiten(p, [])
    assert len(view["unbegrenzt"]) == 1
    namen = [pt["name"] for pt in view["karte"]["punkte"]]
    assert "Unlimited" not in namen
    assert len(namen) == 3


def test_karte_liefert_koordinaten_im_bild(tmp_path):
    p = _state(tmp_path, [_satz("t:a", "Telekom", "A", 20.0, 10.0),
                          _satz("t:b", "o2", "B", 30.0, 20.0),
                          _satz("t:c", "Telekom", "C", 40.0, 40.0)])
    karte = tarife_view.aufbereiten(p, [])["karte"]
    assert karte["hat_daten"]
    for punkt in karte["punkte"]:
        assert 0 <= punkt["cx"] <= karte["breite"]
        assert 0 <= punkt["cy"] <= karte["hoehe"]


def test_karte_kennzeichnet_den_eigenen_konzern(tmp_path):
    p = _state(tmp_path, [_satz("t:a", "Telekom", "A", 20.0, 10.0),
                          _satz("t:b", "o2", "B", 30.0, 20.0),
                          _satz("t:v", "Vodafone", "V", 40.0, 40.0)])
    karte = tarife_view.aufbereiten(p, [])["karte"]
    eigen = [pt for pt in karte["punkte"] if pt["eigen"]]
    assert [pt["anbieter"] for pt in eigen] == ["Vodafone"]


def test_abstand_zur_fair_value_linie_wird_ausgewiesen(tmp_path):
    p = _state(tmp_path, [_satz("t:a", "Telekom", "A", 10.0, 10.0),
                          _satz("t:b", "o2", "B", 20.0, 20.0),
                          _satz("t:c", "Telekom", "C", 90.0, 30.0)])
    karte = tarife_view.aufbereiten(p, [])["karte"]
    teuerster = max(karte["punkte"], key=lambda pt: pt["effektiv"])
    assert teuerster["ueber_linie"] is not None
    assert teuerster["ueber_linie"] > 0


def test_view_legt_die_vollstaendigkeit_offen(tmp_path):
    """Eine Positionskarte mit zwei von sechs Anbietern ist keine
    Marktuebersicht und darf nicht so aussehen."""
    from telco_radar.collect.tarif_crawler import Quelle
    p = _state(tmp_path, [_satz("t:a", "Telekom", "A", 20.0, 10.0)])
    view = tarife_view.aufbereiten(
        p, [Quelle(anbieter="Telekom", einstieg=["https://x"]),
            Quelle(anbieter="o2", einstieg=["https://y"])])
    assert view["vorhanden"] == ["Telekom"]
    assert view["fehlend"] == ["o2"]
    assert view["bilanz"]["tarife"] == 1


def test_leerer_speicher_ergibt_leere_seite(tmp_path):
    view = tarife_view.aufbereiten(tmp_path / "gibtsnicht.jsonl", [])
    assert view["hat_daten"] is False
    assert view["zeilen"] == [] and view["karte"]["punkte"] == []


def test_kaputte_zeilen_werden_ueberlesen(tmp_path):
    p = tmp_path / "tarife.jsonl"
    p.write_text('{"tarif_id":"a","anbieter":"X","grundgebuehr":10.0}\n'
                 'kaputt\n\n', encoding="utf-8")
    assert len(tarife_view.aufbereiten(p, [])["zeilen"]) == 1


def test_das_kopfdatum_ist_das_des_neuesten_tarifsatzes(tmp_path):
    """QA-Befund F3 (Abnahmekriterium G7): `html.py` reicht das Datum des
    letzten WOCHENBERICHTS als `heute` durch - am 04.09.2026 stand damit
    "Stand 2026-09-02" ueber 44 Saetzen vom 2026-09-04. Der Kopf traegt das
    Datum des neuesten Satzes; `heute` bleibt der Rueckfall ohne Abrufdatum.
    """
    p = _state(tmp_path, [_satz("t:a", "Telekom", "A", 20.0, 10.0,
                                abgerufen_am="2026-09-02"),
                          _satz("o:b", "o2", "B", 25.0, 10.0,
                                abgerufen_am="2026-09-04")])
    assert tarife_view.aufbereiten(p, [], heute="2026-09-02")["stand"] == "2026-09-04"
    (tmp_path / "ohne").mkdir()
    ohne = _state(tmp_path / "ohne", [_satz("t:a", "Telekom", "A", 20.0, 10.0)])
    assert tarife_view.aufbereiten(ohne, [], heute="2026-09-02")["stand"] == "2026-09-02"
