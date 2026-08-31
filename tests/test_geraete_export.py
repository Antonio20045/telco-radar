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
from telco_radar.report import geraete_bereinigung, geraete_pruefung
from telco_radar.report import geraete_export as ex
from telco_radar.report import geraete_view

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


def test_der_export_waehlt_nicht_selbst_aus(tmp_path):
    """Geschrieben wird GENAU die uebergebene Menge - keine Zeile weniger.

    Bis zum 31.08.2026 filterte `aktuell_csv` hier selbst nach `status`,
    waehrend die Seite ihren Bestand durch `geraete_pruefung.pruefe()`
    schickte. Zwei Rechnungen fuer dieselbe Menge sind zwei Mengen: die zwei
    o2-Gebrauchtzeilen fielen auf der Seite heraus und standen im Export mit
    `Zustand = neu`.

    Die Auswahl faellt seitdem einmal, in `geraete_view.aufbereiten()` - der
    Export darf sie deshalb nicht wiederholen, auch nicht "sicherheitshalber".
    Der Fall wird hier mit einer AUSGELISTETEN Zeile gestellt, weil sie genau
    die Bedingung traegt, die frueher hier stand; dass sie den Export nie
    erreicht, misst `test_geraete_seite.py` an der gerenderten Seite.
    """
    angaben = ex.schreibe_exporte(
        tmp_path, [_e(), _e(anbieter="o2", status="ausgelistet",
                            id="o2--x")], [], _KATALOG)
    assert angaben["aktuell"]["zeilen"] == 2


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


# ==========================================================================
# DIE VERKETTUNG: Seite und Export lesen denselben Bestand
# ==========================================================================
# Der Fehler, wegen dem es diesen Abschnitt gibt: `/geraete.html` schickte
# seinen Bestand durch die Plausibilitaetspruefung, `geraete-aktuell.csv`
# nicht. Zwei o2-Listungen, deren Rohfelder sie als gebraucht ausweisen,
# standen deshalb im Export mit `Zustand = neu` - wer die Datei in Excel auf
# "neu" filtert, bekam zwei Gebrauchtpreise als Neupreise.
#
# Seit dem 31.08.2026 sind es ZWEI Mengen, und der Export liest die groessere
# (`geraete_view.bestand_und_belastbar`): den Bestand, nicht die geprueften
# Zeilen. Die Pruefung entscheidet, was gegeneinander gerechnet werden darf,
# nicht was es gibt - die Ueberkorrektur hatte das o2-Doppelpreispaar aus der
# Datei genommen, auf die der Pruefbericht namentlich verweist. Die
# Zusicherung dieses Abschnitts ist deshalb enger geworden: nicht "die
# Giftzeile fehlt", sondern "die Giftzeile sagt, was sie ist".

def _gebraucht_aber_als_neu_gespeichert():
    """Die Giftzeile aus dem echten Bestand, nachgebaut - OHNE ihren Zwilling.

    Das Kennzeichen steht AUSSCHLIESSLICH in der Farbe - so schreibt o2 es
    (siehe `geraete_model.zustand_aus_feldern`), und nur so haengt die
    Reihenfolge der zwei Stufen ueberhaupt an etwas: die Bereinigung raeumt
    das Wort aus der Farbe, die Pruefung findet es nur dort.

    DER FALL IST KONSTRUIERT, UND DAS GEHOERT DAZUGESAGT. Im echten Bestand
    stehen die zwei o2-Giftzeilen jeweils NEBEN ihrem Zwilling - derselbe
    Artikel unter der neuen Farbschreibweise -, und ein Zwillingspaar fasst
    `bereinige()` in beiden Reihenfolgen zusammen. Nachgemessen am Bestand
    vom 31.08.2026 liefern deshalb beide Reihenfolgen dieselben 358 Zeilen,
    Zeile fuer Zeile; was sich unterscheidet, ist der Pruefbericht
    (`zustand_veraltet` 2 gegen 0).

    Eine Giftzeile ohne Zwilling ist der Fall, in dem die Reihenfolge auch
    die MENGE aendert. Er kommt heute nicht vor - eine Zusicherung, die nur
    fuer die heutige Datenlage gilt, ist aber keine, und deshalb steht er
    hier.
    """
    return _e(anbieter="o2", preis=577.0,
              id="o2--apple-iphone-17-pro-max-256gb-erneuert",
              sku_id="apple-iphone-17-pro-max-256gb-space-schwarz-refurbished",
              farbe_roh="Space Schwarz erneuert",
              farbe_normalisiert="space schwarz erneuert",
              zustand="neu")


def _ids(eintraege) -> set:
    return {e["id"] for e in eintraege}


def test_die_pruefung_laeuft_vor_der_bereinigung():
    """Die Reihenfolge IST die Zusicherung - vertauscht ueberlebt die Zeile.

    `pruefe()` erkennt die falsch gespeicherte Zustandsangabe an genau dem
    Wort, das `bereinige()` aus der Farbe raeumt. Wer die zwei Stufen
    vertauscht, schaltet die Erkennung ab: die Zeile faellt nicht mehr aus
    der belastbaren Menge, und der Befund wird nicht mehr gemeldet
    (`zustand_veraltet` faellt von 2 auf 0, am echten Bestand gemessen).

    NACHGEMESSEN, und darum praeziser als die fruehere Begruendung: dass
    "die zwei o2-Gebrauchtpreise wieder als Neupreise in geraete-aktuell.csv
    stuenden", stimmt NICHT - sie sind Zwillinge und fallen in beiden
    Reihenfolgen. Was die Reihenfolge sicher aendert, ist der Pruefbericht;
    was sie beim naechsten Datensatz aendern kann, ist die Menge, und dafuer
    braucht es genau den Fall, den diese Fixture baut: eine Giftzeile OHNE
    Zwilling (siehe `_gebraucht_aber_als_neu_gespeichert`).

    Die Gegenprobe steht im selben Test, in zwei Fassungen: einmal mit der
    echten Bereinigung vorweg, einmal mit einer von Hand gesaeuberten Farbe.
    Die zweite haengt an keiner fremden Umsetzung - sie zeigt die Mechanik
    auch dann noch, wenn `bereinige()` sein Vorgehen aendert.
    """
    gift = _gebraucht_aber_als_neu_gespeichert()
    gesund = _e()

    _pruefung, _bestand, belastbar = geraete_view.bestand_und_belastbar(
        [gesund, gift], _KATALOG)
    assert gift["id"] not in _ids(belastbar), \
        "der Gebrauchtpreis haette aus der belastbaren Menge fallen muessen"
    assert gesund["id"] in _ids(belastbar), \
        "die gesunde Zeile darf die Pruefung nicht mitnehmen"

    # In der richtigen Reihenfolge wird der Befund auch GEMELDET - er steht
    # als Zeile im Pruefbericht auf /geraete-quellen.html.
    assert _pruefung["zahlen"]["zustand_veraltet"] >= 1

    # Gegenprobe 1: vertauscht - erst bereinigen, dann pruefen.
    andersherum = geraete_pruefung.pruefe(
        geraete_bereinigung.bereinige([gesund, gift]), _KATALOG)
    assert gift["id"] in _ids(andersherum["sauber"]), \
        ("in dieser Reihenfolge findet die Pruefung das Zustandswort nicht "
         "mehr - genau deshalb steht sie vorne")
    assert andersherum["zahlen"]["zustand_veraltet"] == 0, \
        ("und sie meldet den Befund nicht mehr: ein Fehler, den niemand "
         "meldet, ist der Fehler, den beim naechsten Mal niemand findet")

    # Gegenprobe 2: ohne das Wort in der Farbe laesst die Pruefung die Zeile
    # stehen. Sie entfernt sie also wirklich WEGEN des Wortes, und nicht aus
    # einem anderen Grund, den dieser Fall zufaellig mittraegt.
    ohne_wort = dict(gift, farbe_roh="Space Schwarz",
                     farbe_normalisiert="space schwarz")
    stehen_geblieben = geraete_pruefung.pruefe([gesund, ohne_wort],
                                               _KATALOG)["sauber"]
    assert gift["id"] in _ids(stehen_geblieben)


def test_kein_gebrauchtpreis_steht_als_neupreis_in_der_datei(tmp_path):
    """Der Befund selbst, gegen die geschriebene Datei gemessen.

    Die Datei bekommt seit dem 31.08.2026 den BESTAND, nicht die geprueften
    Zeilen - der Gebrauchtpreis steht also darin, und das ist richtig so:
    die Pruefung entscheidet, was gegeneinander gerechnet werden darf, nicht
    was es gibt. Was NICHT darin stehen darf, ist die Behauptung "Zustand =
    neu" ueber ihn; wer die Datei in Excel auf "neu" filtert, bekaeme sonst
    einen Gebrauchtpreis als Neupreis.

    Die Zusicherung haengt deshalb nicht mehr an `pruefe()`, sondern an der
    Zustandsspalte: `aktuell_csv` leitet sie ab
    (`geraete_bereinigung.zustand_der_zeile`), statt dem Store zu glauben.
    Beide Mengen werden gemessen - in der belastbaren faellt die Zeile ganz
    heraus, im Bestand steht sie mit "refurbished".

    Die gesunde Zeile wird MITgeprueft: eine leere Datei erfuellt die
    Bedingung "kein Neupreis auf Gebrauchtdaten" auch, und dieser Test soll
    den Unterschied zwischen "richtig ausgewiesen" und "nichts geschrieben"
    merken.
    """
    gift = _gebraucht_aber_als_neu_gespeichert()
    gesund = _e()
    _pruefung, bestand, belastbar = geraete_view.bestand_und_belastbar(
        [gesund, gift], _KATALOG)

    # 1. Der Bestand: beide Zeilen, und die Giftzeile sagt, was sie ist.
    angaben = ex.schreibe_exporte(tmp_path, bestand, [], _KATALOG)
    assert angaben["aktuell"]["zeilen"] == 2
    zeilen = _lies((tmp_path / "exporte" / "geraete-aktuell.csv").read_text(
        encoding="utf-8-sig"))
    kopf = zeilen[0]
    assert {z[kopf.index("Listungs-ID")] for z in zeilen[1:]} == {
        gesund["id"], gift["id"]}
    for zeile in zeilen[1:]:
        if zeile[kopf.index("Preis EUR")] == "577,00":
            assert zeile[kopf.index("Zustand")] == "refurbished", zeile
            # Und das Kennzeichen steht nicht mehr in der Farbspalte.
            assert "erneuert" not in zeile[kopf.index("Farbe")].lower()
            break
    else:
        raise AssertionError("die Giftzeile fehlt in der Datei")

    # 2. Die belastbare Menge: die Giftzeile ist gar nicht darin.
    angaben = ex.schreibe_exporte(tmp_path, belastbar, [], _KATALOG)
    assert angaben["aktuell"]["zeilen"] == 1
    zeilen = _lies((tmp_path / "exporte" / "geraete-aktuell.csv").read_text(
        encoding="utf-8-sig"))
    kopf = zeilen[0]
    assert {z[kopf.index("Listungs-ID")] for z in zeilen[1:]} == {gesund["id"]}
    for zeile in zeilen[1:]:
        assert zeile[kopf.index("Preis EUR")] != "577,00"


def test_die_historie_fuehrt_nur_listungen_des_bestands(tmp_path):
    """Sonst widersprechen sich die zwei Dateien.

    Eine Kurve in `geraete-historie.csv` zu einer Listung, die in
    `geraete-aktuell.csv` nicht vorkommt, ist ein Preis ohne Zeile dazu - und
    der Leser, der beide nebeneinanderlegt, haelt die eine Datei fuer
    unvollstaendig.
    """
    fremd = _p(listung_id="o2--laengst-weg", anbieter="o2")
    angaben = ex.schreibe_exporte(tmp_path, [_e()], [_p(), fremd], _KATALOG)
    assert angaben["historie"]["zeilen"] == 1

    zeilen = _lies((tmp_path / "exporte" / "geraete-historie.csv").read_text(
        encoding="utf-8-sig"))
    kopf = zeilen[0]
    gefuehrt = {z[kopf.index("Listungs-ID")] for z in zeilen[1:]}
    assert gefuehrt == {_e()["id"]}
