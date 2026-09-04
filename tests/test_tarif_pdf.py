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


# --------------------------------------------------------------------------- #
# Die senkrechte Tabellenform: Vodafone und congstar
#
# Nachgetragen am 04.09.2026. Die drei Fixtures sind Originaldokumente
# desselben Tages: zwei von Vodafone (Mobil M ohne und mit Smartphone), eins
# von congstar (Allnet Flat L). Bis dahin las der Extraktor bei BEIDEN
# Anbietern keinen einzigen Preis - Vodafone, weil seine Preistabelle
# senkrecht steht und keinen Bezeichner "Entgelt fuer das Komplettprodukt"
# traegt; congstar, weil sein Bezeichner den Produktnamen enthaelt
# ("Entgelt Allnet Flat L (ohne Endgeraet)").
# --------------------------------------------------------------------------- #

@pytest.fixture(scope="module")
def vodafone_m() -> Tarif:
    return lies_text(text("vodafone_mobil_m"))


@pytest.fixture(scope="module")
def vodafone_m_smartphone() -> Tarif:
    return lies_text(text("vodafone_mobil_m_mit_smartphone"))


@pytest.fixture(scope="module")
def congstar_l() -> Tarif:
    return lies_text(text("congstar_allnet_flat_l"))


def test_vodafone_grundgebuehr_ist_die_stufe_ohne_zusatz(vodafone_m):
    """49,95 EUR, nicht 51,95 EUR.

    Die Tabelle fuehrt "ohne 5 Jahresversprechen" (49,95) und "mit 5
    Jahresversprechen" (51,95). Wer die erste Betragszeile nimmt, hat hier
    zufaellig recht; wer die letzte nimmt, traegt zwei Euro zu viel ein.
    Deshalb gilt dieselbe Regel wie bei der waagerechten Telekom-Staffel:
    der kleinste Betrag der ersten Spalte ist der Tarifpreis.
    """
    assert vodafone_m.grundgebuehr == 49.95
    assert vodafone_m.confidence["grundgebuehr"] == HOCH


def test_vodafone_traegt_die_zwei_preisphasen_des_dokuments(vodafone_m):
    """"Monat 1-24" und "ab Monat 25" sind zwei Spaltenueberschriften.

    Das ist die einzige Stelle im Bestand, an der ein Anbieter seine
    Preisphasen selbst auszeichnet. Bis zum 04.09.2026 stand in JEDEM
    Datensatz dieses Projekts die Ersatzphase "1 bis Vertragsende" - eine
    Annahme, kein Messwert.
    """
    assert vodafone_m.preisphasen == [
        Preisphase(von_monat=1, bis_monat=24, betrag=49.95),
        Preisphase(von_monat=25, bis_monat=None, betrag=49.95),
    ]


def test_das_offene_ende_ist_none_und_nicht_die_laufzeit(vodafone_m):
    """"ab Monat 25" hat kein Enddatum - der Vertrag laeuft weiter.

    Als `bis_monat=24` (die Mindestlaufzeit) waere die Phase leer, und der
    Effektivpreis ueber einen laengeren Horizont fiele stillschweigend auf
    null Monate zurueck.
    """
    letzte = vodafone_m.preisphasen[-1]
    assert letzte.bis_monat is None
    assert letzte.monate(36) == 12


def test_vodafone_geraetestaffel_kommt_aus_den_zeilen(vodafone_m_smartphone):
    """Sechs Stufen, senkrecht gelesen - dieselbe Auskunft wie bei Telekom."""
    staffel = {g.kategorie: g.betrag
               for g in vodafone_m_smartphone.geraetepreisstaffel}
    assert staffel["ohne Smartphone"] == 49.95
    assert staffel["mit Top Smartphone"] == 89.95
    assert len(staffel) == 6


def test_eine_tarifoption_ist_keine_geraetestufe(vodafone_m):
    """"mit 5 Jahresversprechen" ist kein Telefon.

    Vodafone stellt Tarifoptionen in dieselbe Tabellenform wie die
    Geraetestaffel. Sie als Geraetepreis abzulegen waere eine
    Falschaussage: fuer die zwei Euro bekommt niemand ein Geraet, und die
    TCO zoege daraus einen Geraeteanteil, den es nicht gibt.
    """
    assert vodafone_m.geraetepreisstaffel == []
    assert "5 Jahresversprechen" in vodafone_m.rohtext


def test_congstar_preis_haengt_an_der_monatsangabe(congstar_l):
    """"Entgelt Allnet Flat L (ohne Endgerät) 29,00 € / Monat".

    Der Bezeichner traegt den Produktnamen statt des Wortes
    "Komplettprodukt". Erkannt wird die Zeile deshalb an der Monatsangabe
    HINTER dem Betrag - sie unterscheidet den Grundpreis von einem
    einmaligen Entgelt.
    """
    assert congstar_l.grundgebuehr == 29.0
    assert congstar_l.laufzeit_monate == 24
    assert not congstar_l.ist_quarantaene


def test_congstar_ist_nicht_die_telekom(congstar_l):
    """Der Fuss des Dokuments lautet "congstar - eine Marke der Telekom
    Deutschland GmbH".

    Ohne den congstar-Eintrag VOR dem Telekom-Eintrag haengt das Ergebnis
    daran, ob dieser Satz umbrochen ist. Eine Marke ist nicht ihr
    Mutterkonzern - congstar verkauft eigene Tarife zu eigenen Preisen
    (29,00 EUR gegen 59,95 EUR bei MagentaMobil L).
    """
    assert congstar_l.anbieter == "congstar"


def test_die_neuen_fixtures_belegen_jeden_wert(vodafone_m, vodafone_m_smartphone,
                                               congstar_l):
    """Kein Feldwert ohne Fundstelle im Rohtext - die Regel des Modells.

    Sie greift hier besonders: der Beleg der Grundgebuehr ist die
    Tabellenzeile, und die wird aus dem Dokument uebernommen und nicht aus
    Etikett und Betrag zurueckformatiert.
    """
    for tarif in (vodafone_m, vodafone_m_smartphone, congstar_l):
        assert tarif.fehlende_belege() == []


def test_eine_geratene_phasenzuordnung_wird_nicht_abgelegt():
    """Drei Spalten, zwei Betraege: dann gibt es keine Preisphasen.

    Das Layout stammt aus dem echten Vodafone-Dokument, die dritte Spalte
    ist hinzugefuegt. Passen Spaltenzahl und Betragszahl nicht zusammen,
    ist jede Zuordnung geraten - und eine geratene Phase ist schlimmer als
    keine, weil sie aussieht wie eine Messung.
    """
    roh = ("Produktinformationsblatt gemäß § 1 TK-Transparenzverordnung\n"
           "Vodafone Mobil M\n"
           "Vertragslaufzeiten 24 Monate\n"
           "Listenpreis inkl. MwSt. Monat 1-6 Monat 7-24 ab Monat 25\n"
           "ohne Smartphone 49,95 € 49,95 €\n"
           "Vodafone GmbH • Ferdinand-Braun-Platz 1 • 40549 Düsseldorf\n")
    t = lies_text(roh)
    assert t.grundgebuehr == 49.95
    # Die Ersatzphase aus `lies_text` - eine Phase ueber die ganze Laufzeit,
    # nicht drei erfundene.
    assert t.preisphasen == [Preisphase(von_monat=1, bis_monat=None,
                                        betrag=49.95)]


def test_eine_gestaffelte_tabelle_ergibt_verschieden_hohe_phasen():
    """Der Aufbau, mit dem eine echte Rabattphase ankaeme.

    ACHTUNG, damit hier niemand eine Marktaussage herausliest: bei ALLEN
    elf am 04.09.2026 vermarkteten Vodafone-Mobilfunktarifen tragen "Monat
    1-24" und "ab Monat 25" DENSELBEN Betrag - eine gestaffelte Tabelle
    steht heute in keinem Dokument des Bestands. Dieser Test prueft
    deshalb die LESEART und nicht einen Tarif: die Betraege unten sind
    veraendert, das Layout ist das gemessene.
    """
    roh = ("Produktinformationsblatt gemäß § 1 TK-Transparenzverordnung\n"
           "Vodafone Mobil M\n"
           "Vertragslaufzeiten 24 Monate\n"
           "Listenpreis inkl. MwSt. Monat 1-6 ab Monat 7\n"
           "ohne Smartphone 19,95 € 49,95 €\n"
           "Vodafone GmbH • Ferdinand-Braun-Platz 1 • 40549 Düsseldorf\n")
    t = lies_text(roh)
    assert t.preisphasen == [
        Preisphase(von_monat=1, bis_monat=6, betrag=19.95),
        Preisphase(von_monat=7, bis_monat=None, betrag=49.95),
    ]
    # Die Grundgebuehr ist der Preis der ERSTEN Phase, nicht der hoechste
    # und nicht der Durchschnitt. Was ueber die Laufzeit daraus wird,
    # rechnet `report/effektivpreis.py` - an EINER Stelle.
    assert t.grundgebuehr == 19.95


def test_der_tabellenfuss_wird_nicht_als_preis_gelesen():
    """Die Zeile nach der Tabelle traegt eine Hausnummer, keinen Betrag.

    Im normalisierten Text sind die Leerzeilen weg; ohne den Abbruch bei
    der ersten betragslosen Zeile liefe der Leser in den Dokumentfuss.
    """
    roh = ("Produktinformationsblatt gemäß § 1 TK-Transparenzverordnung\n"
           "Vodafone Mobil M\n"
           "Listenpreis inkl. MwSt. Monat 1-24 ab Monat 25\n"
           "ohne Smartphone 49,95 € 49,95 €\n"
           "Vodafone GmbH • Ferdinand-Braun-Platz 1 • 40549 Düsseldorf\n"
           "mit Top Smartphone 89,95 € 89,95 €\n")
    t = lies_text(roh)
    assert t.grundgebuehr == 49.95
    assert t.geraetepreisstaffel == []


@pytest.mark.skipif(not shutil.which("pdftotext"),
                    reason="poppler-utils nicht installiert")
def test_die_neuen_fixtures_kommen_aus_ihrem_pdf():
    """Text und PDF derselben Fixture muessen dasselbe ergeben.

    Die Gegenprobe zu der Regel, dass die Logik auf TEXT arbeitet: laufen
    die zwei auseinander, prueft die Suite eine Datei, die mit dem
    Originaldokument nichts mehr zu tun hat. Genau diese Falle hat am
    11.08.2026 ein Bau-Subagent aufgestellt, der seine Fixture erfand.
    """
    for name, grundgebuehr in (("vodafone_mobil_m", 49.95),
                               ("congstar_allnet_flat_l", 29.0)):
        aus_pdf = lies_pdf(FIX / f"{name}.pdf")
        assert aus_pdf.grundgebuehr == grundgebuehr, name
        assert aus_pdf.als_dict() | {"dokument_hash": "", "abgerufen_am": ""} \
            == lies_text(text(name)).als_dict() | {"dokument_hash": "",
                                                   "abgerufen_am": ""}


def test_ein_vierwochenpreis_ist_kein_monatspreis():
    """Vodafones CallYa: "Listenpreis inkl. MwSt. 14,99 €", vier Wochen.

    `Tarif.grundgebuehr` meint einen Monatspreis - `Preisphase` rechnet in
    Monaten und `tco_24` ueber 24 davon. Dreizehn Zyklen im Jahr in zwoelf
    Monate umzurechnen waere eine Rechnung dieses Projekts und keine Angabe
    des Anbieters. Ohne diese Sperre stand CallYa Allnet Flat M mit 14,99
    EUR als Monatspreis im Bestand - gemessen am 04.09.2026, bevor die
    Sperre stand.
    """
    roh = ("Produktinformationsblatt gem. §1 TK-Transparenzverordnung\n"
           "CallYa Allnet Flat M\n"
           "Vertragslaufszeiten 4 Wochen, Kündigungsfrist 1 Monat\n"
           "Listenpreis inkl. MwSt. 14,99 € / 4 Wochen\n")
    t = lies_text(roh)
    assert t.grundgebuehr is None
    # Ohne Preis UND ohne Laufzeit ist es fuer dieses Modell kein Tarif -
    # es faellt in die Quarantaene statt mit einer Monatszahl in die
    # Datenbank, die keine ist.
    assert t.ist_quarantaene


def test_ein_einzelner_listenpreis_ohne_zeitachse_wird_gelesen():
    """Die Gegenprobe: dieselbe Zeile OHNE Wochenangabe ist ein Preis.

    Ohne diesen Test bewiese der Test darueber nur, dass irgendetwas nicht
    gelesen wird - nicht, dass die Wochenangabe der Grund ist.
    """
    roh = ("Produktinformationsblatt gem. §1 TK-Transparenzverordnung\n"
           "Ein Tarif\n"
           "Mindestvertragslaufzeit 24 Monate\n"
           "Listenpreis inkl. MwSt. 14,99 €\n")
    t = lies_text(roh)
    assert t.grundgebuehr == 14.99
