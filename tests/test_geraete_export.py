"""Der CSV-Gesamtexport (G3.3, 29.08.2026).

Die vierte von den Fachkollegen benannte Luecke: die interne Loesung gibt
Daten nur je Einzelprodukt oder je Marke heraus. Wer den Markt ueberblicken
will, klickt sich durch Dutzende Downloads.

DIE ZWEI ZUSICHERUNGEN, DIE HIER ZAEHLEN, sind keine Formalien, sondern die
Bedingung dafuer, dass die Datei ueberhaupt benutzt wird: sie muss sich in
Excel mit deutschem Gebietsschema per Doppelklick oeffnen. Ohne BOM wird
aus "Groesse" -> "GrÃ¶ÃŸe", mit Komma statt Semikolon landet die ganze Zeile
in Spalte A, und mit Dezimalpunkt liest Excel 1349.90 als Text.
"""
import csv
import io
from pathlib import Path

import pytest

from telco_radar.geraete_model import Geraet, Katalog
from telco_radar.report import geraete_export as ex

_KATALOG = Katalog(geraete=[
    Geraet(hersteller="Apple", modell="iPhone 17 Pro Max", generation=17,
           speicher=[256, 512], segment="flagship"),
])


def _e(anbieter="Vodafone", preis=1349.9, **kw):
    satz = {
        "id": f"{anbieter.lower()}--apple-iphone-17-pro-max-256gb-tiefblau",
        "sku_id": "apple-iphone-17-pro-max-256gb-tiefblau",
        "device_id": "apple-iphone-17-pro-max", "anbieter": anbieter,
        "anbieter_typ": "netzbetreiber", "status": "aktiv",
        "speicher_gb": 256, "farbe_normalisiert": "tiefblau",
        "zustand": "neu", "preis_ohne_vertrag": preis,
        "verfuegbarkeit": "lieferbar",
        "quelle_url": "https://www.vodafone.de/privat/handys/iphone-17-pro-max.html",
        "abgerufen_am": "2026-08-29",
    }
    satz.update(kw)
    return satz


def _p(datum="2026-08-29", preis=1349.9, **kw):
    satz = {"listung_id": "vodafone--apple-iphone-17-pro-max-256gb-tiefblau",
            "sku_id": "apple-iphone-17-pro-max-256gb-tiefblau",
            "device_id": "apple-iphone-17-pro-max", "anbieter": "Vodafone",
            "datum": datum, "preis_ohne_vertrag": preis,
            "verfuegbarkeit": "lieferbar", "quelle_url": "https://v.de/p"}
    satz.update(kw)
    return satz


def _lies(inhalt: str) -> list:
    return list(csv.reader(io.StringIO(inhalt), delimiter=";"))


# ==========================================================================
# Excel im deutschen Gebietsschema
# ==========================================================================

def test_die_datei_traegt_ein_bom(tmp_path):
    angaben = ex.schreibe_exporte(tmp_path, [_e()], [_p()], _KATALOG)
    roh = (tmp_path / "exporte" / "geraete-aktuell.csv").read_bytes()
    assert roh.startswith(b"\xef\xbb\xbf"), \
        "ohne BOM liest Excel UTF-8 als Windows-1252"
    assert angaben["aktuell"]["zeilen"] == 1


def test_semikolon_trennt_die_spalten(tmp_path):
    ex.schreibe_exporte(tmp_path, [_e()], [_p()], _KATALOG)
    text = (tmp_path / "exporte" / "geraete-aktuell.csv").read_text(
        encoding="utf-8-sig")
    kopf = text.splitlines()[0]
    assert kopf.count(";") >= 10
    assert "," not in kopf, "das Komma ist im deutschen Excel der Dezimaltrenner"


def test_preise_tragen_ein_dezimalkomma(tmp_path):
    ex.schreibe_exporte(tmp_path, [_e(preis=1349.9)], [_p()], _KATALOG)
    text = (tmp_path / "exporte" / "geraete-aktuell.csv").read_text(
        encoding="utf-8-sig")
    zeilen = _lies(text)
    spalte = zeilen[0].index("Preis EUR")
    assert zeilen[1][spalte] == "1349,90"


def test_umlaute_ueberleben_den_umweg(tmp_path):
    ex.schreibe_exporte(tmp_path, [_e(farbe_normalisiert="grün")], [_p()],
                        _KATALOG)
    text = (tmp_path / "exporte" / "geraete-aktuell.csv").read_text(
        encoding="utf-8-sig")
    assert "grün" in text


# ==========================================================================
# Der Inhalt
# ==========================================================================

def test_der_aktuelle_export_traegt_alle_geforderten_spalten(tmp_path):
    ex.schreibe_exporte(tmp_path, [_e()], [_p()], _KATALOG)
    kopf = _lies((tmp_path / "exporte" / "geraete-aktuell.csv").read_text(
        encoding="utf-8-sig"))[0]
    for spalte in ("Anbieter", "Modell", "Speicher GB", "Farbe", "Preis EUR",
                   "Preisart", "Tarifreferenz", "Verfuegbarkeit", "Quelle",
                   "Abgerufen am"):
        assert spalte in kopf, spalte


def test_die_preisart_steht_in_einer_eigenen_spalte(tmp_path):
    """Wer eine Tabelle nach Preis sortiert, in der 49,95 Zuzahlung neben
    1349,90 Ladenpreis steht, bekommt eine Rangliste, die nichts bedeutet."""
    ex.schreibe_exporte(tmp_path, [
        _e(),
        _e(anbieter="o2", preis=None, preis_ohne_vertrag=None, zuzahlung=49.95,
           tarif_referenz="o2 Mobile M",
           id="o2--apple-iphone-17-pro-max-256gb-tiefblau"),
    ], [], _KATALOG)
    zeilen = _lies((tmp_path / "exporte" / "geraete-aktuell.csv").read_text(
        encoding="utf-8-sig"))
    kopf = zeilen[0]
    arten = {z[kopf.index("Anbieter")]: (z[kopf.index("Preis EUR")],
                                         z[kopf.index("Preisart")],
                                         z[kopf.index("Tarifreferenz")])
             for z in zeilen[1:]}
    assert arten["Vodafone"] == ("1349,90", "ohne Vertrag", "")
    assert arten["o2"] == ("49,95", "Zuzahlung im Tarifbuendel", "o2 Mobile M")


def test_eine_zuzahlung_ohne_tarifreferenz_erscheint_ohne_preis(tmp_path):
    ex.schreibe_exporte(tmp_path, [
        _e(preis=None, preis_ohne_vertrag=None, zuzahlung=49.95,
           tarif_referenz="")], [], _KATALOG)
    zeilen = _lies((tmp_path / "exporte" / "geraete-aktuell.csv").read_text(
        encoding="utf-8-sig"))
    kopf = zeilen[0]
    assert zeilen[1][kopf.index("Preis EUR")] == ""


def test_ausgelistete_geraete_stehen_nicht_im_aktuellen_export(tmp_path):
    angaben = ex.schreibe_exporte(
        tmp_path, [_e(), _e(anbieter="o2", status="ausgelistet",
                            id="o2--x")], [], _KATALOG)
    assert angaben["aktuell"]["zeilen"] == 1


def test_die_historie_nennt_hersteller_und_modell_statt_nur_kennungen(tmp_path):
    """Eine Tabelle mit einer Spalte voller device_ids ist in Excel
    unbrauchbar."""
    ex.schreibe_exporte(tmp_path, [_e()], [_p(), _p(datum="2026-08-21",
                                                   preis=1399.0)], _KATALOG)
    zeilen = _lies((tmp_path / "exporte" / "geraete-historie.csv").read_text(
        encoding="utf-8-sig"))
    kopf = zeilen[0]
    assert zeilen[1][kopf.index("Hersteller")] == "Apple"
    assert zeilen[1][kopf.index("Modell")] == "iPhone 17 Pro Max"
    # Aelteste Messung zuerst - eine Historie liest man vorwaerts.
    assert zeilen[1][kopf.index("Datum")] == "2026-08-21"
    assert zeilen[2][kopf.index("Datum")] == "2026-08-29"


def test_die_zeilenzahl_stimmt_mit_der_datei_ueberein(tmp_path):
    """Die Zahl steht neben dem Link auf der Seite. Sie muss aus der
    wirklich geschriebenen Datei stammen, nicht aus einer Rechnung."""
    angaben = ex.schreibe_exporte(
        tmp_path, [_e(), _e(anbieter="o2", id="o2--x")],
        [_p(), _p(datum="2026-08-21")], _KATALOG)
    for schluessel, name in (("aktuell", "geraete-aktuell.csv"),
                             ("historie", "geraete-historie.csv")):
        text = (tmp_path / "exporte" / name).read_text(encoding="utf-8-sig")
        echte = len(_lies(text)) - 1          # ohne Kopfzeile
        assert angaben[schluessel]["zeilen"] == echte, name


def test_leerer_bestand_erzeugt_trotzdem_gueltige_dateien(tmp_path):
    angaben = ex.schreibe_exporte(tmp_path, [], [], _KATALOG)
    assert angaben["aktuell"]["zeilen"] == 0
    text = (tmp_path / "exporte" / "geraete-aktuell.csv").read_text(
        encoding="utf-8-sig")
    assert _lies(text)[0] == ex.SPALTEN_AKTUELL, "die Kopfzeile bleibt"


def test_ein_semikolon_im_text_zerreisst_die_zeile_nicht(tmp_path):
    ex.schreibe_exporte(tmp_path, [_e(farbe_normalisiert="blau; matt")], [],
                        _KATALOG)
    zeilen = _lies((tmp_path / "exporte" / "geraete-aktuell.csv").read_text(
        encoding="utf-8-sig"))
    assert len(zeilen[1]) == len(ex.SPALTEN_AKTUELL)
    assert zeilen[1][ex.SPALTEN_AKTUELL.index("Farbe")] == "blau; matt"
