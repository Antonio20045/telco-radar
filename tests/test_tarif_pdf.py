"""Tarif-Extraktor: gemessen an vier ECHTEN Produktinformationsblaettern.

Die Fixtures sind Originaldokumente vom 08.08.2026 - zwei von der Telekom
(MagentaMobil Basic und L), zwei von o2 (Mobile Unlimited M Flex, Home L
Flex). Sie liegen als PDF **und** als extrahierter Text bei, und die
Erwartungen unten sind an ihnen gemessen, nicht angenommen.

Warum die Logik gegen TEXT und nicht gegen PDF geprueft wird
------------------------------------------------------------
`pdftotext` ist ein externes Binary (poppler-utils) und auf einem frischen
Runner nicht installiert. Haengt die Extraktionslogik daran, faellt die halbe
Suite aus, sobald jemand sie woanders laufen laesst. Deshalb: die Logik
arbeitet auf Text, und nur der eine Test, der die PDF-Schale prueft,
ueberspringt sich ohne poppler.
"""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from telco_radar.collect import tarif_pdf
from telco_radar.collect.tarif_pdf import (
    PDFNichtLesbar, dokument_hash, ist_tarifdokument, lies_pdf, lies_text,
)
from telco_radar.tarif_model import HOCH, Preisphase, Tarif, normalisiere, zahl

FIX = Path(__file__).parent / "fixtures" / "tarif_pdfs"


def text(name: str) -> str:
    return (FIX / f"{name}.txt").read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def basic() -> Tarif:
    return lies_text(text("telekom_magentamobil_basic"))


@pytest.fixture(scope="module")
def gross() -> Tarif:
    return lies_text(text("telekom_magentamobil_l"))


@pytest.fixture(scope="module")
def unlimited() -> Tarif:
    return lies_text(text("o2_mobile_unlimited_m_flex"))


@pytest.fixture(scope="module")
def festnetz() -> Tarif:
    return lies_text(text("o2_home_l_flex"))


# --------------------------------------------------------------------------- #
# Telekom MagentaMobil Basic - der vollstaendige Fall
# --------------------------------------------------------------------------- #

def test_basic_anbieter_und_name(basic):
    assert basic.anbieter == "Telekom"
    assert basic.name == "MagentaMobil Basic"
    assert basic.art == "mobilfunk"


def test_basic_preis_ist_die_stufe_ohne_geraet(basic):
    """Die Grundgebuehr ist der KLEINSTE Wert der Staffel.

    "ohne Smartphone" ist der Tarifpreis; jede Stufe darueber enthaelt eine
    Geraetefinanzierung. Wer den ersten Wert der Tabellenzeile nimmt, hat
    meistens recht und manchmal einen um 40 € zu hohen Preis in der Datenbank.
    """
    assert basic.grundgebuehr == 24.95


def test_basic_geraetestaffel_vollstaendig(basic):
    """Fuenf Stufen, und jede traegt ihre Kategorie.

    Die Kategorien stehen im PDF ueber drei Zeilen SPALTENWEISE. Wer die
    Zeilen verkettet und mit einem Regex durchsucht, bekommt
    "mit Premium- mit Premium- Smartphone" - zwei Spalten zu einer
    Ueberschrift verschmolzen.
    """
    assert [(g.kategorie, g.betrag) for g in basic.geraetepreisstaffel] == [
        ("ohne Smartphone", 24.95),
        ("mit Smartphone", 34.95),
        ("mit Top-Smartphone", 44.95),
        ("mit Premium-Smartphone", 54.95),
        ("mit Premium-Plus-Smartphone", 64.95),
    ]


def test_basic_volumen_und_drossel(basic):
    assert basic.datenvolumen_gb == 5.0
    assert basic.drossel_down == 64.0
    assert basic.drossel_up == 16.0


def test_basic_geschwindigkeit(basic):
    assert basic.speed_down_max == 300.0
    assert basic.speed_up_max == 50.0


def test_basic_vertrag(basic):
    """"Kündigungsfrist ein Monat" - als WORT, nicht als Ziffer."""
    assert basic.laufzeit_monate == 24
    assert basic.kuendigungsfrist_monate == 1


def test_basic_versionsstand(basic):
    assert basic.versionsstand == "01.08.2024"


def test_basic_ist_keine_quarantaene(basic):
    assert not basic.ist_quarantaene


# --------------------------------------------------------------------------- #
# MagentaMobil L - dasselbe Layout, andere Zahlen. Faengt Ueberanpassung ab.
# --------------------------------------------------------------------------- #

def test_l_zahlen(gross):
    assert gross.grundgebuehr == 59.95
    assert gross.datenvolumen_gb == 80.0
    assert gross.laufzeit_monate == 24


def test_l_staffel_trotz_anderer_einrueckung(gross):
    """Dieselbe Tabelle, um ein Zeichen anders eingerueckt.

    Genau daran ist die erste Fassung gescheitert: mit fester Toleranz stand
    "Hardware" aus der Zeilenbeschriftung einmal 15 und einmal 14 Zeichen von
    der ersten Spalte entfernt - in einem Dokument sauber, im anderen als
    "ohne Smartphone Hardware". Die Spaltenbreite wird deshalb gemessen.
    """
    assert [g.kategorie for g in gross.geraetepreisstaffel] == [
        "ohne Smartphone", "mit Smartphone", "mit Top-Smartphone",
        "mit Premium-Smartphone", "mit Premium-Plus-Smartphone",
    ]
    assert [g.betrag for g in gross.geraetepreisstaffel] == [
        59.95, 69.95, 79.95, 89.95, 99.95]


def test_basic_und_l_unterscheiden_sich_wirklich(basic, gross):
    """Absicherung gegen einen Extraktor, der Konstanten zurueckgibt."""
    assert basic.grundgebuehr != gross.grundgebuehr
    assert basic.datenvolumen_gb != gross.datenvolumen_gb


# --------------------------------------------------------------------------- #
# o2 Mobile Unlimited M Flex - kein Volumen, keine Bindung, keine Staffel
# --------------------------------------------------------------------------- #

def test_unlimited_preis_und_name(unlimited):
    assert unlimited.anbieter == "o2"
    assert unlimited.grundgebuehr == 39.99
    assert unlimited.art == "mobilfunk"


def test_flex_hat_laufzeit_null_nicht_none(unlimited):
    """"Keine Mindestlaufzeit" ist eine AUSSAGE, kein fehlender Wert.

    Als None faellt der Tarif in die Quarantaene und aus jeder Rechnung; der
    Effektivpreis rechnete gegen 24 Monate, die es nicht gibt.
    """
    assert unlimited.laufzeit_monate == 0
    assert unlimited.kuendigungsfrist_monate == 1
    assert not unlimited.ist_quarantaene


def test_unlimited_volumen_ist_unendlich(unlimited):
    """Unlimited ist eine Aussage. Als None waere der Tarif aus der
    Positionskarte gefallen, und dort gehoert er hin."""
    assert unlimited.datenvolumen_gb == float("inf")
    assert unlimited.preis_je_gb == 0.0


def test_unlimited_hat_keine_geraetestaffel(unlimited):
    assert unlimited.geraetepreisstaffel == []


# --------------------------------------------------------------------------- #
# o2 Home L Flex - drei Produktvarianten in EINEM Dokument
# --------------------------------------------------------------------------- #

def test_festnetz_nimmt_den_groessten_maximalwert(festnetz):
    """Das Dokument beschreibt 175/250/300 in einem PDF.

    Der erste Treffer waere 175 - und die Positionskarte zeigte den Anbieter
    dauerhaft zu schwach.
    """
    assert festnetz.speed_down_max == 300.0
    assert festnetz.speed_up_max == 150.0


def test_festnetz_preis_und_art(festnetz):
    assert festnetz.grundgebuehr == 44.99
    assert festnetz.art == "festnetz"


def test_festnetz_zero_width_space_bricht_die_laufzeit_nicht(festnetz):
    """o2 setzt ein U+200B hinter "Keine Mindestlaufzeit".

    Unsichtbar, also unauffindbar, wenn man es nicht kennt - und ohne
    Normalisierung trifft kein Wortgrenzen-Regex.
    """
    assert festnetz.laufzeit_monate == 0


def test_festnetz_erkennt_telefonie_flat(festnetz):
    assert festnetz.allnet_flat is True


# --------------------------------------------------------------------------- #
# Die Regel, die das Modell traegt: kein Wert ohne Beleg
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("name", [
    "telekom_magentamobil_basic", "telekom_magentamobil_l",
    "o2_mobile_unlimited_m_flex", "o2_home_l_flex",
])
def test_jeder_wert_hat_eine_fundstelle_im_rohtext(name):
    """Die zentrale Zusage dieses Moduls, gegen alle vier Dokumente."""
    t = lies_text(text(name))
    assert t.fehlende_belege() == []
    t.pruefe_belege()


def test_gesetzte_felder_tragen_confidence(basic):
    for feld in ("grundgebuehr", "laufzeit_monate", "datenvolumen_gb"):
        assert basic.confidence[feld] == HOCH
        assert basic.fundstellen[feld]


def test_erfundene_fundstelle_faellt_auf():
    t = Tarif(rohtext="Entgelt 24,95 €")
    t.setze("grundgebuehr", 24.95, "Entgelt 24,95 €")
    assert t.fehlende_belege() == []
    t.fundstellen["grundgebuehr"] = "Entgelt 99,99 €"
    assert t.fehlende_belege() == ["grundgebuehr"]
    with pytest.raises(ValueError, match="ohne Fundstelle"):
        t.pruefe_belege()


def test_setze_ohne_beleg_setzt_nichts():
    """Lieber ein fehlendes Feld als eine Zahl, die niemand nachschlagen kann."""
    t = Tarif(rohtext="egal")
    t.setze("grundgebuehr", 24.95, "")
    assert t.grundgebuehr is None
    assert "grundgebuehr" not in t.confidence


# --------------------------------------------------------------------------- #
# Quarantaene statt falscher Zahlen
# --------------------------------------------------------------------------- #

def test_unbekanntes_layout_geht_in_quarantaene():
    t = lies_text("Irgendein Flyer ohne jede Tarifangabe.\nRuf uns an!")
    assert t.ist_quarantaene
    assert t.grundgebuehr is None


def test_leeres_dokument_stuerzt_nicht_ab():
    t = lies_text("")
    assert t.ist_quarantaene and t.rohtext == ""


def test_ein_pflichtfeld_reicht_gegen_quarantaene():
    """Ein Flex-Tarif hat zu Recht keine Mindestlaufzeit - das darf ihn nicht
    in die Quarantaene schicken."""
    t = lies_text("Produktinformationsblatt\nEntgelt für das Komplettprodukt\n"
                  "39,99 €")
    assert t.grundgebuehr == 39.99
    assert not t.ist_quarantaene


def test_kennzeichen_erkennt_tarifdokumente(basic):
    assert ist_tarifdokument(text("telekom_magentamobil_basic"))
    assert ist_tarifdokument("Vertragszusammenfassung nach EU-Verordnung")
    assert not ist_tarifdokument("Allgemeine Geschäftsbedingungen")


# --------------------------------------------------------------------------- #
# Hilfsteile
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("roh,erwartet", [
    ("24,95", 24.95), ("1.234,56", 1234.56), ("39,99 €", 39.99),
    ("100", 100.0), ("", None), ("keine", None), (None, None),
])
def test_zahl_liest_deutsche_schreibweise(roh, erwartet):
    assert zahl(roh) == erwartet


def test_normalisiere_entfernt_unsichtbare_zeichen():
    assert "​" not in normalisiere("Keine Mindestlaufzeit​")
    assert normalisiere("a     b\n\n  c  ") == "a b\nc"


def test_dokument_hash_haengt_am_inhalt():
    assert dokument_hash(b"abc") == dokument_hash("abc")
    assert dokument_hash("abc") != dokument_hash("abd")


def test_preisphase_zaehlt_monate():
    assert Preisphase(1, 6, 9.99).monate(24) == 6
    assert Preisphase(7, None, 29.99).monate(24) == 18
    # Eine Phase, die ueber das Vertragsende hinausreicht, wird gekappt.
    assert Preisphase(1, 36, 10.0).monate(24) == 24


def test_listenpreis_wird_zu_einer_phase(basic):
    """Ein PIB nennt keinen Rabatt. Eine Phase ueber die ganze Laufzeit ist
    die ehrliche Darstellung - und der Effektivpreis rechnet ohne Sonderfall."""
    assert basic.preisphasen == [Preisphase(1, None, 24.95)]


def test_als_dict_laesst_den_rohtext_weg(basic):
    d = basic.als_dict()
    assert "rohtext" not in d
    assert d["grundgebuehr"] == 24.95
    assert d["fundstellen"]["grundgebuehr"]


# --------------------------------------------------------------------------- #
# Die PDF-Schale
# --------------------------------------------------------------------------- #

@pytest.mark.skipif(not shutil.which("pdftotext"),
                    reason="poppler-utils nicht installiert")
def test_pdf_pfad_liefert_dieselben_werte_wie_der_text():
    """Die Schale muss dasselbe ergeben wie das Textfixture - sonst laufen
    Tests und Wirklichkeit auseinander."""
    aus_pdf = lies_pdf(FIX / "telekom_magentamobil_basic.pdf")
    assert aus_pdf.grundgebuehr == 24.95
    assert aus_pdf.datenvolumen_gb == 5.0
    assert len(aus_pdf.geraetepreisstaffel) == 5
    assert aus_pdf.dokument_hash


def test_fehlendes_pdftotext_wirft_klar(monkeypatch, tmp_path):
    """Ein fehlendes Binary darf nicht wie ein leeres Dokument aussehen."""
    monkeypatch.setattr(tarif_pdf.shutil, "which", lambda _: None)
    with pytest.raises(PDFNichtLesbar, match="poppler"):
        tarif_pdf.text_aus_pdf(tmp_path / "x.pdf")
