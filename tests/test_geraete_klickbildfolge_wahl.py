"""Bildfolge, Nachbesserung 09.11.2026 (Prüfung PR 78), ohne Netz.

A1: ein Schrittbild gilt nur, wenn die gewählte Kachel ganz im Ausschnitt liegt.
A2: eine Seite ohne Markierung gilt nur, wenn die Kachel den gemessenen Wert nennt.
A3: der Preistext nennt die Zahl, die das Bild hervorhebt, nur mit Beträgen im Bild.
Die Seite ``beispiel_kacheln.html`` ist ein BEISPIEL, kein Anbieter.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from belegbau import ZEIT, karte, png, quelle

from telco_radar.collect.geraete.klickbeleg import baue_beleg
from telco_radar.collect.geraete.klickbildfolge import (
    PREIS,
    SCHRITTE,
    Folgebild,
    lies_folge,
    schritttext,
)
from telco_radar.collect.geraete.klickecho import Variante
from telco_radar.collect.geraete.klickkarte import (
    KlickkartenFehler,
    klickkarte_aus_daten,
)
from telco_radar.collect.geraete.klickpreistext import TEXT_OHNE_BETRAG
from telco_radar.collect.geraete.klicktext import Preiswerte, betraege_im_text
from telco_radar.tarif_model import Preisphase

WURZEL = Path(__file__).parent.parent
FIXTURES = Path(__file__).parent / "fixtures" / "klickcrawler"
SEITE = (FIXTURES / "beispiel_kacheln.html").read_text("utf-8")
NICHT_DRIN = "gewählte Kachel nicht vollständig im Ausschnitt"


def _karte(tarif, bildfolge=None, *, gewaehlt=None):
    daten = yaml.safe_load((FIXTURES / "beispiel_karte.yaml").read_text("utf-8"))
    daten["knoepfe"]["speicher"] = {"fest": "128"}
    daten["knoepfe"]["laufzeit"] = {"fest": "24"}
    daten["knoepfe"]["tarif"] = {"wert": "data-wert", **tarif}
    if gewaehlt is not None:
        daten["knoepfe"]["tarif"]["gewaehlt"] = gewaehlt
    daten["bildfolge"] = {"tarif": bildfolge} if bildfolge is not None else {}
    return klickkarte_aus_daten(daten, "Kachelkarte")


def _lies(chromium, karte, tarif):
    ziel = {"speicher": "128", "tarif": tarif, "laufzeit": "24"}
    seite = chromium.new_page(viewport={"width": 1280, "height": 900})
    try:
        seite.set_content(SEITE)
        return lies_folge(seite, karte, ziel, 5000)
    finally:
        seite.close()


def _gruppe(gruppe, wert, **karte):
    return _karte({"selektor": f"#{gruppe} .kachel"}, **karte), wert


def test_gewaehlte_kachel_im_ausschnitt_gibt_das_bild(chromium):
    karte, wert = _gruppe("ok", "B")

    bilder, luecken = _lies(chromium, karte, wert)

    assert "tarif" in bilder
    assert "tarif" not in luecken


@pytest.mark.parametrize(
    ("gruppe", "wert"),
    [("hoch", "9"), ("viele", "13")],
    ids=["ueber_der_hoehengrenze", "hinter_der_optionsgrenze"],
)
def test_gewaehlte_kachel_ausserhalb_des_ausschnitts_gibt_kein_bild(
    chromium, gruppe, wert
):
    karte, _ = _gruppe(gruppe, wert)

    bilder, luecken = _lies(chromium, karte, wert)

    assert "tarif" not in bilder
    assert luecken["tarif"] == NICHT_DRIN


def test_selektor_ohne_die_gewaehlte_kachel_gibt_kein_bild(chromium):
    karte = _karte({"selektor": "#ok .kachel"}, '#ok .kachel[data-wert="A"]')

    bilder, luecken = _lies(chromium, karte, "B")

    assert "tarif" not in bilder
    assert luecken["tarif"] == NICHT_DRIN


def test_verborgene_gewaehlte_kachel_gibt_kein_bild(chromium):
    karte, wert = _gruppe("verborgen", "B")

    bilder, luecken = _lies(chromium, karte, wert)

    assert "tarif" not in bilder
    assert luecken["tarif"] == "gewählte Kachel nicht sichtbar"


def test_fehlt_das_element_des_bildes_gibt_es_kein_bild_mit_grund(chromium):
    karte = _karte({"selektor": "#ok .kachel"}, "#gibt-es-nicht .kachel")

    bilder, luecken = _lies(chromium, karte, "B")

    assert "tarif" not in bilder
    assert luecken["tarif"] == "Optionen nicht sichtbar"


def _einzige(gruppe, *, zeigt_wert=True):
    """Eine Seite ohne Markierung: die einzige Kachel, ihr Wert steht im Attribut."""
    return _karte(
        {"selektor": f"#{gruppe} .name", "wert": "data-name"},
        {"selektor": f"#{gruppe} .kachel", "zeigt_wert": zeigt_wert},
        gewaehlt={"einzige": True},
    )


def test_kachel_mit_dem_gemessenen_namen_gibt_das_bild(chromium):
    bilder, luecken = _lies(chromium, _einzige("einzig-m"), "MagentaMobil M")

    assert "tarif" in bilder
    assert "tarif" not in luecken


@pytest.mark.parametrize("gruppe", ["einzig-s", "einzig-max"])
def test_kachel_mit_anderem_namen_gibt_kein_bild(chromium, gruppe):
    bilder, luecken = _lies(chromium, _einzige(gruppe), "MagentaMobil M")

    assert "tarif" not in bilder
    assert luecken["tarif"] == "Bild nennt MagentaMobil M nicht"


def test_ohne_zeigt_wert_prueft_die_karte_den_namen_nicht(chromium):
    karte = _einzige("einzig-s", zeigt_wert=False)

    bilder, _ = _lies(chromium, karte, "MagentaMobil M")

    assert "tarif" in bilder


def test_einzige_gilt_nur_bei_genau_einer_kachel(chromium):
    karte = _karte({"selektor": "#ok .kachel"}, gewaehlt={"einzige": True})

    bilder, luecken = _lies(chromium, karte, "B")

    assert "tarif" not in bilder
    assert "Seite markiert nichts statt B" in luecken["tarif"]


def test_ohne_gemessenen_wert_zeigt_das_bild_ihn_nicht(chromium):
    karte = _karte(
        {"selektor": "#einzig-m .kachel", "wert": "data-fehlt"},
        {"selektor": "#einzig-m .kachel", "zeigt_wert": True},
        gewaehlt={"einzige": True},
    )

    bilder, luecken = _lies(chromium, karte, None)

    assert "tarif" not in bilder
    assert "unbekannt" in luecken["tarif"]


def test_beleg_nennt_den_tarif_nur_mit_dem_bild_des_tarifs():
    folge = {s: Folgebild(s, png((n * 40, 20, 20))) for n, s in enumerate(SCHRITTE[:3])}
    del folge["tarif"]
    grund = {"tarif": "Bild nennt S nicht"}

    fertig, _ = baue_beleg(quelle(folge=folge, folge_fehlt=grund), karte(), ZEIT)

    texte = [b.text for b in fertig.beleg.bildfolge]
    assert not any(t.startswith("Tarif gewählt") for t in texte)
    assert fertig.beleg.bildfolge_fehlt == ("tarif: Bild nennt S nicht",)


@pytest.mark.parametrize(
    "marke",
    [
        {"einzige": False},
        {"einzige": "ja"},
        {"einzige": True, "passt": "*"},
    ],
)
def test_karte_lehnt_kaputte_einzige_ab(marke):
    with pytest.raises(KlickkartenFehler):
        _karte({"selektor": "#ok .kachel"}, gewaehlt=marke)


@pytest.mark.parametrize(
    "bildfolge",
    [
        {"selektor": "#x", "zeigt_wert": "ja"},
        {"zeigt_wert": True},
        {"selektor": "#x", "zeigt": True},
    ],
)
def test_karte_lehnt_kaputtes_zeigt_wert_ab(bildfolge):
    with pytest.raises(KlickkartenFehler):
        _karte({"selektor": "#ok .kachel"}, bildfolge)


def test_telekom_karte_prueft_den_tarifnamen_statt_alle_kacheln_zu_nehmen():
    pfad = WURZEL / "config" / "klickkarten" / "telekom.yaml"
    roh = pfad.read_text("utf-8")
    karte = klickkarte_aus_daten(yaml.safe_load(roh), "telekom")

    assert karte.bildfolge_zeigt == {"tarif"}
    assert karte.bildfolge["tarif"] == "#step1"
    assert karte.marke("tarif").einzige
    assert '"*"' not in roh


O2_BILD = (
    "Gesamtpreis\nGerät monatlich:\n65,00\xa0€\nRatenzahlung: 24 Monate\n"
    "Gesamtpreis Gerät: 1.567,00\xa0€\nTarif monatlich:\n24,99\xa0€\n"
    "(Mindestlaufzeit 24 Monate):\nmonatlich gesamt:\n89,99\xa0€\n"
    "Gerät Anzahlung:\n7,00\xa0€\neinmaliger Anschlusspreis\n0,00\xa0€\n"
    "Versandkosten:\n6,99\xa0€\neinmalig gesamt:\n13,99\xa0€\nIn den Warenkorb"
)
O2 = Preiswerte(
    anzahlung=7.0,
    rate=65.0,
    ratenzahl=24,
    anschluss=0.0,
    tarifphasen=(Preisphase(1, None, 24.99),),
)
VARIANTE = Variante("256 GB", "M", 24)


def _preis(werte, bildtext):
    return schritttext(PREIS, VARIANTE, None, werte, None, bildtext)


def test_preistext_nennt_die_gesamtzahl_des_bildes_und_das_geraet_getrennt():
    text = _preis(O2, O2_BILD)

    assert text == (
        "Im Bild: einmalig gesamt 13,99 € inkl. 6,99 € Versand; davon Gerät 7,00 € · "
        "monatlich 89,99 € (Gerät und Tarif zusammen) · Monatsrate 65,00 €"
    )
    assert betraege_im_text(text) <= betraege_im_text(O2_BILD)


def test_preistext_nennt_das_geraet_nicht_als_einmalige_summe():
    assert "einmalig 7,00" not in _preis(O2, O2_BILD)


def test_preistext_nennt_versand_nur_wenn_die_summe_aufgeht():
    bild = O2_BILD.replace("13,99", "14,50")

    text = _preis(O2, bild)

    assert "einmalig gesamt 14,50 €; davon Gerät 7,00 €" in text
    assert "Versand" not in text
    assert betraege_im_text(text) <= betraege_im_text(bild)


def test_preistext_laesst_eine_zahl_weg_die_das_bild_nicht_nennt():
    bild = O2_BILD.replace("Gerät Anzahlung:\n7,00\xa0€\n", "")

    text = _preis(O2, bild)

    assert "davon Gerät" not in text
    assert betraege_im_text(text) <= betraege_im_text(bild)
    assert text != TEXT_OHNE_BETRAG
