"""O4 (STRATEGIE_GERAETE_OPTIK §3, 15.09.2026): die zwei neuen Exporte und
der EINE zentrale Ort der Export-Links.

  * `geraete-tco.csv` - eine Zeile je Bündel (Modell, Speicher, Anbieter,
    Anbietertyp, Tarif, Band, Zuzahlung, Tarif/Monat, Geräterate, Laufzeit,
    Anschlusspreis, TCO-24, abgerufen_am, Quelle) PLUS die SIM-only-Zeilen
    (die Referenzen aus geraete_tco.json).
  * Radar-Export - TCO UND Händler-Barpreis in EINER Datei; die %-Spalte
    ist KONSUMENT derselben Rechnung aus `wettbewerbsradar.py`, keine
    zweite Rechnung für dieselbe Zahl (CLAUDE.md §6).
  * Export-Links EINMAL zentral: seit P4/D4 (18.09.2026) die FUSSZEILE der
    Geräteseite (.gr-export-fuss) - bis P4 die Kopfzeile (O4), davor je
    Reiter. Die duplizierten Knopfpaare in den Reitern bleiben gefallen.

Doktrin (Modulkopf geraete_export.py): der Export filtert nicht selbst -
er schreibt den Bestand. Diese Datei misst am ECHTEN Bestand.
"""
from __future__ import annotations

import csv
import io
import json
import pathlib
import re

import pytest
from bs4 import BeautifulSoup

from telco_radar.report.html import render_site

WURZEL = pathlib.Path(__file__).resolve().parents[1]

# Die Spalten der Bündel-Zeilen - Auftrag O4, wortgleich. "Art" steht
# davor, weil die Datei Bündel- UND SIM-only-Zeilen trägt; "Zustand" und
# "Bündel/Monat" kommen dazu, weil ein erneuertes Gerät ein anderer Preis
# ist (B1) und 1&1 einen EINEN Monatsbetrag nennt, der nicht in
# Tarif/Monat gehört (§ 13.2 der Strategie). Die Leitzahl-Spalte heißt
# seit A1 wie auf der Seite "Kosten über 24 Monate" (vorher "TCO-24").
# "SKU-ID" steht als LETZTE Spalte, am selben Ort wie in
# geraete-aktuell.csv (die IDs stehen dort auch am Ende): ohne sie
# kollabierten Vodafones Farbvarianten zu byte-identischen Zeilen
# (A4, 20.09.2026: 156 in der Live-Datei) - Modell, Speicher und alle
# Preise sind je Farbe gleich, nur die SKU (Teil des Bündelschlüssels)
# trennt sie. Die Reihenfolge dieser Liste ist die der Datei.
SPALTEN_TCO = [
    "Art", "Modell", "Speicher GB", "Anbieter", "Anbietertyp", "Tarif",
    "Band", "Zustand", "Zuzahlung EUR", "Tarif/Monat EUR", "Geräterate EUR",
    "Bündel/Monat EUR", "Laufzeit Monate", "Anschlusspreis EUR",
    "Kosten über 24 Monate EUR", "Abgerufen am", "Quelle", "SKU-ID",
]


@pytest.fixture(scope="module")
def site(tmp_path_factory) -> pathlib.Path:
    ziel = tmp_path_factory.mktemp("o4-export") / "site"
    render_site(ziel, WURZEL / "data" / "reports")
    return ziel


def _csv(pfad: pathlib.Path) -> tuple[list[str], list[list[str]]]:
    """Die Datei als (Kopfzeile, Zeilen) - BOM weg, Semikolon getrennt."""
    roh = pfad.read_bytes()
    assert roh[:3] == b"\xef\xbb\xbf", f"kein BOM: {pfad.name}"
    text = roh.decode("utf-8-sig")
    zeilen = list(csv.reader(io.StringIO(text), delimiter=";"))
    return zeilen[0], zeilen[1:]


@pytest.fixture(scope="module")
def tco_csv(site) -> tuple[list[str], list[list[str]]]:
    pfad = site / "exporte" / "geraete-tco.csv"
    assert pfad.exists(), "geraete-tco.csv fehlt in site/exporte/"
    return _csv(pfad)


@pytest.fixture(scope="module")
def radar_csv(site) -> tuple[list[str], list[list[str]]]:
    pfad = site / "exporte" / "wettbewerbsradar.csv"
    assert pfad.exists(), "wettbewerbsradar.csv fehlt in site/exporte/"
    return _csv(pfad)


@pytest.fixture(scope="module")
def geraete(site) -> BeautifulSoup:
    return BeautifulSoup((site / "geraete.html").read_text(encoding="utf-8"),
                         "html.parser")


@pytest.fixture(scope="module")
def radar(site) -> BeautifulSoup:
    """Die Radar-TAFEL von geraete.html - seit E3 Schritt 3 (17.09.2026)
    ist der Radar der Reiter „Radar" der EINEN Geräteseite; die Alt-URL
    wettbewerbsradar.html ist eine Weiterleitung ohne Inhalt. Der Export-
    Knopf des Radars steht in der FUSSZEILE der Seite (P4/D4, 18.09.2026:
    EINE Stelle für alle Reiter - bis dahin in der Kopfzeile, nie je
    Reiter, und auch die Fußzeile nie ZUSÄTZLICH in einer Tafel)."""
    suppe = BeautifulSoup((site / "geraete.html").read_text(encoding="utf-8"),
                          "html.parser")
    tafel = suppe.select_one("#tafel-radar")
    assert tafel is not None, "#tafel-radar fehlt - die Fixture prüft nichts"
    return BeautifulSoup(str(tafel), "html.parser")


@pytest.fixture(scope="module")
def store() -> dict:
    return json.loads(
        (WURZEL / "data" / "state" / "geraete_tco.json").read_text())


# --------------------------------------------------------------------------
# geraete-tco.csv: Form
# --------------------------------------------------------------------------

def test_die_spalten_stehen_wie_im_auftrag(tco_csv):
    kopf, _ = tco_csv
    assert kopf == SPALTEN_TCO, kopf


def test_jede_zeile_hat_alle_spalten(tco_csv):
    kopf, zeilen = tco_csv
    for z in zeilen:
        assert len(z) == len(kopf), z


def test_preise_tragen_ein_dezimalkomma(tco_csv):
    _, zeilen = tco_csv
    idx = {"Kosten über 24 Monate EUR": 14, "Zuzahlung EUR": 8}
    werte = [z[idx["Kosten über 24 Monate EUR"]] for z in zeilen
             if z[idx["Kosten über 24 Monate EUR"]]]
    assert werte, "keine einzige Leitzahl in der Datei"
    for w in werte:
        assert re.fullmatch(r"-?\d+,\d{2}", w), w


# --------------------------------------------------------------------------
# geraete-tco.csv: Menge - der Export filtert nicht selbst
# --------------------------------------------------------------------------

def test_eine_zeile_je_buendel_des_bestands(tco_csv, store):
    """Der Bestand aus geraete_tco.json steht GANZ in der Datei - auch
    Bündel ohne Tarifband und ohne auflösbare Zuordnung. Der Export
    entscheidet nicht, was drinsteht (Doktrin des Modulkopfs)."""
    _, zeilen = tco_csv
    buendel = [z for z in zeilen if z[0] == "Bündel"]
    assert len(buendel) == len(store["buendel"]), (
        f"{len(buendel)} Bündel-Zeilen, Bestand {len(store['buendel'])}")


def test_die_sim_only_referenzen_stehen_darin(tco_csv, store):
    _, zeilen = tco_csv
    sim = [z for z in zeilen if z[0] == "SIM-only"]
    assert len(sim) == len(store["sim_only"]), (
        f"{len(sim)} SIM-only-Zeilen, Bestand {len(store['sim_only'])}")


def test_die_datei_zaehlt_buendel_plus_sim_only(tco_csv, store):
    """A4-Gegenprobe: die Datei ist die SUMME ihrer zwei Arten - jede
    Zeile ist ein Bündel ODER eine Referenz, nichts fällt zusammen und
    nichts kommt dazu (der Export filtert nicht selbst)."""
    _, zeilen = tco_csv
    assert len(zeilen) == len(store["buendel"]) + len(store["sim_only"]), (
        f"{len(zeilen)} Zeilen, Bestand {len(store['buendel'])} Bündel "
        f"+ {len(store['sim_only'])} SIM-only")


def test_keine_zwei_datenzeilen_sind_identisch(tco_csv):
    """A4: ohne die SKU-Spalte kollabierten Vodafones Farbvarianten zu
    byte-identischen Zeilen (live am 20.09.2026: 156 Stück) - in Excel
    sieht eine doppelte Zeile aus wie ein Fehler der Datei, und Sortieren
    oder Pivotieren verschiebt sie still. Verglichen wird die GANZE
    Zeile als Tupel; identische Tupel sind byte-identisch."""
    _, zeilen = tco_csv
    tuples = [tuple(z) for z in zeilen]
    assert len(set(tuples)) == len(tuples), (
        f"{len(tuples) - len(set(tuples))} byte-identische Datenzeilen")


def test_die_band_spalte_ist_gefuellt_wo_ein_band_ist(tco_csv, store):
    """Band kommt aus demselben Tarifbestand wie die Seite
    (`geraete_tco_band.tarif_baender`) - dieselbe Quelle, keine zweite
    Gruppierung. Ein Bündel ohne Band trägt eine leere Zelle, keins eine
    geratene."""
    from telco_radar.report import geraete_tco_band
    from telco_radar.tarif_bezug import Tarifbestand
    bands = geraete_tco_band.tarif_baender(
        Tarifbestand.aus_datei(
            WURZEL / "data" / "state" / "tarife.jsonl").je_id)
    erwartet_mit_band = sum(1 for b in store["buendel"]
                            if bands.get(b.get("tarif_id")))
    _, zeilen = tco_csv
    mit_band = sum(1 for z in zeilen
                   if z[0] == "Bündel" and z[6])
    assert mit_band == erwartet_mit_band, (
        f"{mit_band} Bündel mit Band, erwartet {erwartet_mit_band}")


def test_die_tco24_einer_zeile_ist_gerechnet_nach_geraten(tco_csv, store):
    """Stichprobe: die Leitzahl-Spalte trägt `tco_model.tco_24()` - dieselbe
    Funktion wie Karte, Graph und Radar, keine Export-Sonderrechnung."""
    from telco_radar.tco_model import Buendel, tco_24
    kopf, zeilen = tco_csv
    idx = {name: i for i, name in enumerate(kopf)}
    probe = next(z for z in zeilen
                 if z[0] == "Bündel" and z[idx["Kosten über 24 Monate EUR"]])

    def _zahl(zelle: str):
        return (float(zelle.replace(".", "").replace(",", "."))
                if zelle else None)

    # Der Store-Satz, der zu ALLEN Beträgen der Zeile passt - (Anbieter,
    # Tarif) allein trägt mehrere Varianten desselben Geräts.
    kandidaten = [b for b in store["buendel"]
                  if b["anbieter"] == probe[idx["Anbieter"]]
                  and b["tarif_name"] == probe[idx["Tarif"]]
                  and b.get("geraet_zuzahlung") == _zahl(
                      probe[idx["Zuzahlung EUR"]])
                  and b.get("tarif_monatlich") == _zahl(
                      probe[idx["Tarif/Monat EUR"]])
                  and b.get("geraet_monatsrate") == _zahl(
                      probe[idx["Geräterate EUR"]])
                  and b.get("buendel_monatlich") == _zahl(
                      probe[idx["Bündel/Monat EUR"]])]
    # 1&1 führt denselben Tarif mit denselben Beträgen zu MEHREREN
    # Geräten - die Zeile ist über die Beträge nicht eindeutig, aber alle
    # Kandidaten rechnen dieselbe TCO (gleiche Preisfelder). Verlangt wird
    # genau das: EIN Wert über alle Kandidaten, und der in der Zelle.
    assert kandidaten, "Stichprobe trifft keinen Satz des Stores"
    werte = set()
    for satz in kandidaten:
        erg = tco_24(Buendel(**{
            k: v for k, v in satz.items()
            if k in Buendel.__dataclass_fields__}))
        assert erg.belastbar, (
            f"Stichprobe {probe} trägt eine Zahl, obwohl tco_24 "
            "unbelastbar ist")
        werte.add(erg.gesamt)
    assert len(werte) == 1, (
        f"Kandidaten der Stichprobe rechnen verschiedene TCO: {werte}")
    assert float(probe[idx["Kosten über 24 Monate EUR"]].replace(".", "")
                 .replace(",", ".")) == pytest.approx(
        werte.pop(), abs=0.005), (
        f"Leitzahl der Stichprobe {probe} stimmt nicht mit tco_24() überein")


def test_die_tco24_einer_simonly_zeile_ist_gerechnet_nach_geraten(
        tco_csv, store):
    """A4: derselbe Kreuzcheck wie bei den Bündeln, fuer die zweite
    Zeilenart - die Leitzahl einer SIM-only-Zeile ist `tco_24` ueber
    `SimOnlyReferenz.als_buendel()` (Clean Code 1: EINE Rechnung), nicht
    tarif * 24. Bis A4 fehlte der Anschlusspreis in der Zelle; am
    Bestand vom 20.09.2026 tragen 19 von 45 Referenzen einen, die Probe
    waehlt deshalb eine MIT Anschlusspreis - nur dort unterscheiden sich
    alte und neue Rechnung ueberhaupt."""
    from telco_radar.tco_model import SimOnlyReferenz, tco_24
    kopf, zeilen = tco_csv
    idx = {name: i for i, name in enumerate(kopf)}

    def _zahl(zelle: str):
        return (float(zelle.replace(".", "").replace(",", "."))
                if zelle else None)

    satz = next((s for s in store["sim_only"]
                 if s.get("anschlusspreis") is not None
                 and s.get("tarif_sim_only_monatlich") is not None), None)
    assert satz is not None, (
        "keine Referenz mit Anschlusspreis im Bestand - der Test prueft "
        "nichts")

    # Die Zeile, die zu ALLEN Beträgen dieses Satzes passt - dieselbe
    # Zuordnung wie beim Bündel-Kreuzcheck; mehrere Referenzen mit
    # denselben Beträgen muessen dieselbe Leitzahl rechnen.
    kandidaten = [s for s in store["sim_only"]
                  if s["anbieter"] == satz["anbieter"]
                  and s["tarif_name"] == satz["tarif_name"]
                  and s.get("tarif_sim_only_monatlich")
                  == satz["tarif_sim_only_monatlich"]
                  and s.get("anschlusspreis") == satz["anschlusspreis"]]
    assert kandidaten, "Stichprobe trifft keinen Satz des Stores"
    probe = next(z for z in zeilen
                 if z[0] == "SIM-only"
                 and z[idx["Anbieter"]] == satz["anbieter"]
                 and z[idx["Tarif"]] == satz["tarif_name"]
                 and _zahl(z[idx["Tarif/Monat EUR"]])
                 == satz["tarif_sim_only_monatlich"]
                 and _zahl(z[idx["Anschlusspreis EUR"]])
                 == satz["anschlusspreis"])
    werte = set()
    for s in kandidaten:
        ref = SimOnlyReferenz(**{
            k: v for k, v in s.items()
            if k in SimOnlyReferenz.__dataclass_fields__})
        erg = tco_24(ref.als_buendel())
        assert erg.belastbar, (
            f"Stichprobe {probe} trägt eine Zahl, obwohl tco_24 "
            "unbelastbar ist")
        werte.add(erg.gesamt)
    assert len(werte) == 1, (
        f"Kandidaten der Stichprobe rechnen verschiedene TCO: {werte}")
    assert float(probe[idx["Kosten über 24 Monate EUR"]].replace(".", "")
                 .replace(",", ".")) == pytest.approx(
        werte.pop(), abs=0.005), (
        f"Leitzahl der SIM-only-Stichprobe {probe} stimmt nicht mit "
        "tco_24() überein")


def test_zwei_farbvarianten_bleiben_zwei_zeilen():
    """A4 am GESTELLTEN Bestand - dieselbe Kollision wie live: zwei
    Vodafone-Bündel, die sich in keiner exportierten Spalte unterscheiden
    bis auf die SKU (Farbvariante), plus eine SIM-only-Referenz MIT
    Anschlusspreis. Ohne die SKU-Spalte kollabierte das Paar zu einer
    byte-identischen Doppelzeile; die SIM-only-Leitzahl stand ohne
    Anschlusspreis in der Datei. Fixtures setzen ihr Datum selbst
    (harte Regel 11)."""
    from telco_radar.geraete_model import Geraet, Katalog
    from telco_radar.report.geraete_export import tco_csv
    from telco_radar.report.geraete_tco_view import aufbereiten
    from telco_radar.tco_model import Buendel, SimOnlyReferenz

    def _buendel(sku: str) -> Buendel:
        return Buendel(
            sku_id=sku, anbieter="Vodafone", tarif_name="Mobil M",
            tarif_monatlich=51.95, geraet_zuzahlung=1.0,
            geraet_monatsrate=43.5, laufzeit_monate=24,
            anschlusspreis=0.0,
            quelle_url="https://www.vodafone.de/privat/handys/x.html",
            abgerufen_am="2026-09-20")

    blau = _buendel("apple-iphone-air-256gb-himmelblau")
    weiss = _buendel("apple-iphone-air-256gb-weiss")
    referenz = SimOnlyReferenz(
        anbieter="Vodafone", tarif_name="Mobil M",
        tarif_sim_only_monatlich=39.99, anschlusspreis=29.99,
        quelle_url="https://www.vodafone.de/mobil-m",
        abgerufen_am="2026-09-20")
    # Der Katalog bildet BEIDE SKUs auf dasselbe Modell ab - nur so ist
    # die Modellspalte fuer das Paar identisch und die SKU das einzige
    # Unterscheidungsmerkmal (live ist das bei jeder Farbvariante so).
    katalog = Katalog([Geraet(hersteller="Apple", modell="iPhone Air")])

    d = aufbereiten([blau, weiss], [referenz], [], katalog)
    inhalt, zahl = tco_csv(d["export"])

    # Anzahl Zeilen == Anzahl Bündel + SIM-only im Testbestand.
    assert zahl == 3, zahl
    zeilen = list(csv.reader(io.StringIO(inhalt), delimiter=";"))[1:]
    assert len(zeilen) == 3, zeilen
    # Gegenprobe: keine zwei Datenzeilen identisch.
    assert len({tuple(z) for z in zeilen}) == 3, zeilen

    idx = {name: i for i, name in enumerate(SPALTEN_TCO)}
    pa = [z for z in zeilen if z[0] == "Bündel"]
    assert len(pa) == 2, zeilen
    assert {z[idx["SKU-ID"]] for z in pa} == {blau.sku_id, weiss.sku_id}
    # Alle ÜBRIGEN Spalten sind identisch - die SKU ist das einzige
    # Unterscheidungsmerkmal, genau die Live-Lage der Farbvarianten.
    ohne_sku = [tuple(c for i, c in enumerate(z) if i != idx["SKU-ID"])
                for z in pa]
    assert ohne_sku[0] == ohne_sku[1], ohne_sku

    # SIM-only über dieselbe Rechnung wie die Bündel-Leitzahl:
    # 39,99 EUR/Monat * 24 + 29,99 EUR Anschlusspreis = 989,75 EUR
    # (die alte Exportzahl ohne Anschlusspreis: 959,76 EUR).
    sim = next(z for z in zeilen if z[0] == "SIM-only")
    assert sim[idx["Kosten über 24 Monate EUR"]] == "989,75", sim
    assert sim[idx["SKU-ID"]] == "", sim


def test_erneuerte_buendel_stehen_mit_ihrem_zustand_darin(tco_csv, store):
    """Zustand ist eine Preisdimension (B1): 8 erneuerte Bündel stehen im
    Bestand und müssen mit ihrem Zustand in der Datei stehen - nicht als
    'neu' (derselbe Fehlertyp wie der alte CSV-Zustandsfehler)."""
    zustand_index = SPALTEN_TCO.index("Zustand")
    _, zeilen = tco_csv
    erneuert = [z for z in zeilen
                if z[0] == "Bündel" and z[zustand_index]
                and z[zustand_index] != "neu"]
    erwartet = sum(1 for b in store["buendel"]
                   if b.get("zustand") and b["zustand"] != "neu")
    assert len(erneuert) == erwartet, (
        f"{len(erneuert)} Zeilen mit Zustand != neu, "
        f"Bestand {erwartet}")


# --------------------------------------------------------------------------
# Radar-Export: ein Konsument der Radar-Rechnung
# --------------------------------------------------------------------------

def test_der_radar_export_traegt_tco_und_haendlerzeilen(radar_csv):
    """EINE Datei, alle Abschnitte: Preis-Alarme, Netzbetreiber (Kosten
    über 24 Monate) und Händler (Gerätepreis) - getrennt über die Art-
    Spalte, nicht über drei Dateien. E5 hat die Alarme dazu gebracht;
    vorher deckte die Datei zwei der drei Sektionen des Radar-Reiters."""
    kopf, zeilen = radar_csv
    art_index = kopf.index("Art")
    arten = {z[art_index] for z in zeilen}
    assert arten == {"Preis-Alarm", "Netzbetreiber Kosten über 24 Monate",
                     "Händler Barpreis"}, arten


def test_die_prozentzahl_ist_die_der_seite(radar_csv, radar):
    """Die %-Spalte ist KONSUMENT derselben Rechnung: die Zahl der
    vergleichbaren Zeilen in der Datei ist die Zahl der vergleichbaren
    Zeilen auf der Seite (`wr-status--vergleichbar`) - keine zweite
    Rechnung für dieselbe Zahl. Seit E3 Schritt 3 stehen die Zeilen in
    den Detailzeilen der Modell-Liste (bis dahin in den `.wr-gruppe`-
    Blöcken der Schwesterseite; die Klasse `.wr-zeile` tragen seit S2 nur
    noch die Händler-Zeilen)."""
    kopf, zeilen = radar_csv
    idx = {name: i for i, name in enumerate(kopf)}
    datei = sum(1 for z in zeilen
                if z[idx["Art"]] == "Netzbetreiber Kosten über 24 Monate"
                and z[idx["Abweichung %"]])
    seite = len(radar.select("#wr-abweichung tr.wr-status--vergleichbar"))
    assert seite > 0, "die Radar-Tafel zeigt keine vergleichbare Zeile"
    assert datei == seite, (
        f"{datei} Zeilen mit Abweichung in der Datei, {seite} auf der Seite")


def test_haendlerzeilen_ennen_den_barpreis_beider_seiten(radar_csv):
    kopf, zeilen = radar_csv
    idx = {name: i for i, name in enumerate(kopf)}
    haendler = [z for z in zeilen if z[idx["Art"]] == "Händler Barpreis"]
    assert haendler, "keine Händlerzeile im Radar-Export"
    for z in haendler:
        assert z[idx["Wettbewerber-Preis EUR"]], z
        assert z[idx["Vodafone-Preis EUR"]], z
        assert re.fullmatch(r"-?\d+,\d", z[idx["Abweichung %"]]), z


def test_die_nicht_vergleichbaren_zeilen_stehen_mit_status_darin(
        radar_csv, radar):
    """Auch Band-Mismatch und kein Bündel stehen in der Datei - mit Status
    statt %-Zahl. Der Export schreibt den Bestand, die Ansicht kappt."""
    kopf, zeilen = radar_csv
    idx = {name: i for i, name in enumerate(kopf)}
    ohne_zahl = sum(1 for z in zeilen
                    if z[idx["Art"]] == "Netzbetreiber Kosten über 24 Monate"
                    and not z[idx["Abweichung %"]])
    assert ohne_zahl > 0
    statuswerte = {z[idx["Status"]] for z in zeilen}
    assert "band_mismatch" in statuswerte or "kein_buendel" in statuswerte


def test_radar_export_enthaelt_auch_die_alarmtabelle(radar_csv, geraete):
    """E5 (Strategie §7, O4-Evaluator S3): die vierte Zahlensektion ist
    exportierbar - JEDE Alarmzeile der Seite steht in der Datei, Zahl für
    Zahl dieselbe (Zeilenzahl == Seite, kein Lookup ins Leere: die
    Zuordnung wird am Ende auf Vollständigkeit geprüft, CLAUDE.md §6).

    Verglichen wird gegen die data-Attribute der GERENDERTEN Zeilen -
    dieselben Rohwerte, aus denen die Zellen der Seite gesetzt werden -
    und nicht gegen eine zweite Aufbereitung: die Datei ist Konsument
    der Rechnung, nicht ihr zweiter Rechner."""
    kopf, zeilen = radar_csv
    idx = {name: i for i, name in enumerate(kopf)}
    alarm_zeilen = [z for z in zeilen if z[idx["Art"]] == "Preis-Alarm"]
    assert alarm_zeilen, "keine Preis-Alarm-Zeile im Radar-Export"

    seite_zeilen = geraete.select("#wr-alarme tr.gr-a-zeile")
    assert seite_zeilen, "die Alarmtabelle der Seite ist leer - der Test \
würde an einer leeren Ausgabe grün vorbeigehen"

    # (modell, speicher, prozent, wettbewerbspreis, unser preis) ist der
    # Schluessel, unter dem eine Alarmzeile eindeutig ist - am echten
    # Bestand teilen zwei Zeilen dieselbe Zahlenkombination, nur das
    # Geraet unterscheidet sie. Der Laden steht daneben und wird
    # mitgeprüft.
    def _speicher(roh: str) -> str:
        return str(int(float(roh))) if roh else ""

    def _schluessel(z):
        return (z[idx["Modell"]], _speicher(z[idx["Speicher GB"]]),
                z[idx["Abweichung %"]], z[idx["Wettbewerber-Preis EUR"]],
                z[idx["Vodafone-Preis EUR"]])

    def _seitenschluessel(tr):
        return (tr["data-modell"], _speicher(tr.get("data-speicher") or ""),
                f"{float(tr['data-s-prozent']):.1f}".replace(".", ","),
                f"{float(tr['data-s-fremd']):.2f}".replace(".", ","),
                f"{float(tr['data-s-unser']):.2f}".replace(".", ","))

    datei = {_schluessel(z): z for z in alarm_zeilen}
    erwartet = {_seitenschluessel(tr): tr for tr in seite_zeilen}
    assert len(datei) == len(alarm_zeilen), (
        "doppelte Alarmzeile in der Datei")
    assert len(erwartet) == len(seite_zeilen), (
        "doppelte Alarmzeile auf der Seite")
    assert set(datei) == set(erwartet), (
        f"{len(datei)} Alarmzeilen in der Datei, {len(erwartet)} auf der "
        f"Seite; nur in der Datei: {sorted(set(datei) - set(erwartet))[:3]}")

    # Der Laden und die Stufe stehen NAMENTLICH in der Datei - dieselben
    # Wörter wie die Zelle der Seite (S3: ein zweites Wort für dieselbe
    # Sache wäre ein zweites Etikett).
    for schluessel, tr in erwartet.items():
        z = datei[schluessel]
        assert z[idx["Anbieter"]] == tr["data-s-laden"], (z, tr)
        stufe = tr.select_one(".gr-pille")
        assert stufe is not None, "Alarmzeile ohne Einstufungs-Pille"
        assert z[idx["Status"]] == stufe.get_text(strip=True), (z, stufe)
        assert z[idx["Preisart"]] == "Gerätepreis ohne Vertrag", z
        quelle = tr.select_one(".gr-a-quelle")
        assert z[idx["Quelle"]] == (quelle.get("href") if quelle else ""), z


def test_die_alarmzeilen_stehen_als_erster_abschnitt_der_datei(radar_csv):
    """Die Reihenfolge der Arten in der Datei ist die der Sektionen auf
    der Seite: Alarme, dann Abweichung (Netzbetreiber), dann Händler."""
    kopf, zeilen = radar_csv
    idx = kopf.index("Art")
    arten_in_ordnung = [z[idx] for z in zeilen]
    erste = {a: arten_in_ordnung.index(a) for a in set(arten_in_ordnung)}
    assert erste["Preis-Alarm"] < erste[
        "Netzbetreiber Kosten über 24 Monate"] < erste["Händler Barpreis"], \
        erste


# --------------------------------------------------------------------------
# Export-Links: EINMAL zentral, von beiden Seiten
# --------------------------------------------------------------------------

def test_geraete_verlinkt_jede_datei_genau_einmal(geraete):
    links = [a.get("href") for a in geraete.select("a[href^='exporte/']")]
    assert links, "kein Export-Link auf der Geräteseite"
    assert len(links) == len(set(links)), (
        f"doppelter Export-Link auf derselben Seite: {links}")
    assert "exporte/geraete-aktuell.csv" in links
    assert "exporte/geraete-historie.csv" in links
    assert "exporte/geraete-tco.csv" in links


def test_die_export_links_stehen_in_der_fusszeile(geraete):
    """P4/D4 (18.09.2026): die FUSSZEILE (.gr-export-fuss) ist der EINE
    Ort - bis P4 standen die Knöpfe in der Kopfzeile (O4), davor je
    Reiter (`gr-werkzeug`), davor im Hero der Schwesterseite. Der Umzug
    an den Seitenende nahm ihnen den Platz über der Reiter-Steuerung
    (mobil: gequetscht vor jedem ersten Datenelement)."""
    fuss = geraete.select_one("section.gr-export-fuss")
    assert fuss is not None, "keine Export-Fußzeile auf der Geräteseite"
    links = geraete.select("a[href^='exporte/']")
    assert links, "kein Export-Link auf der Geräteseite"
    for a in links:
        assert fuss in a.parents, (
            f"Export-Link außerhalb der Fußzeile: {a.get('href')}")
    hero = geraete.select_one("section.page-hero")
    assert hero is not None
    assert not hero.select("a[href^='exporte/']"), (
        "Export-Knöpfe stehen noch in der Kopfzeile (P4/D4: Fußzeile)")
    assert not geraete.select(".gr-werkzeug a[href^='exporte/']"), (
        "Export-Knöpfe stehen noch in einem Reiter")


def test_der_radar_verlinkt_seinen_export_genau_einmal(geraete):
    """Seit E3 Schritt 3 gehört der Radar-Export zur EINEN Geräteseite -
    sein Knopf steht im Hero neben den drei anderen (bis dahin im Hero der
    Schwesterseite). Genau ein Mal, nie zusätzlich in einem Reiter."""
    links = [a.get("href") for a in geraete.select("a[href^='exporte/']")
             if a.get("href") == "exporte/wettbewerbsradar.csv"]
    assert links == ["exporte/wettbewerbsradar.csv"], links
    radar_tafel = geraete.select_one("#tafel-radar")
    assert radar_tafel is not None
    assert not radar_tafel.select("a[href^='exporte/']"), \
        "der Radar-Export steht zusätzlich IN der Tafel (O4: eine Stelle)"


def test_die_links_nennen_die_zeilenzahl(geraete):
    """Zeilenzahl NEBEN dem Link (Modulkopf geraete_export): ein leerer
    Download ist der teuerste Weg herauszufinden, dass er sich nicht
    lohnt. Seit P4/D4 stehen die Links in der Fußzeile."""
    links = geraete.select("section.gr-export-fuss a[href^='exporte/']")
    assert links, "kein Export-Link in der Fußzeile"
    for a in links:
        assert re.search(r"\d+", a.get_text()), a.get_text()


def test_der_radar_wird_durch_den_export_nicht_hoeher(radar):
    """Bekannte Grenze (O3-Bericht): Radar mobil ~20.400 px. Der Export
    steht als KNOPF in der Kopfzeile, nicht als neue offene Tabelle - keine
    neue Tabellenstruktur mit mehr als zehn Zeilen."""
    for tabelle in radar.select("table"):
        # Nur NEUE Strukturen dieses Auftrags prüfen: der Export darf
        # keine eigene Tabelle auf der Seite aufbauen.
        if "wr-export" in (tabelle.get("class") or []):
            pytest.fail("der Export baut eine offene Tabelle auf der "
                        "Radar-Seite")
