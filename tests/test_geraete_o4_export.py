"""O4 (STRATEGIE_GERAETE_OPTIK §3, 15.09.2026): die zwei neuen Exporte und
der EINE zentrale Ort der Export-Links.

  * `geraete-tco.csv` - eine Zeile je Bündel (Modell, Speicher, Anbieter,
    Anbietertyp, Tarif, Band, Zuzahlung, Tarif/Monat, Geräterate, Laufzeit,
    Anschlusspreis, TCO-24, abgerufen_am, Quelle) PLUS die SIM-only-Zeilen
    (die Referenzen aus geraete_tco.json).
  * Radar-Export - TCO UND Händler-Barpreis in EINER Datei; die %-Spalte
    ist KONSUMENT derselben Rechnung aus `wettbewerbsradar.py`, keine
    zweite Rechnung für dieselbe Zahl (CLAUDE.md §6).
  * Der Export-Link EINMAL zentral: seit dem Neuentwurf (29.09.2026) der
    EINE Link auf geraete-tco.csv im Fuß der Kosten-Rangliste (.kv-fuss).

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
from telco_radar.report.geraete_export import (SPALTE_UEBER_24,
                                               SPALTE_UEBER_LAUFZEIT)
from telco_radar.tco_model import TCO_HORIZONT as _O4_HORIZONT

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
# P0-B-h4 (21.09.2026): "Leitzahl-Zeitraum Monate" kommt dazu -
# `tco_model.Tco.leitzahl_monate`, gelesen und nicht geraten. Ohne sie
# behauptete "Kosten über 24 Monate EUR" ihren Zeitraum fest, auch fuer
# 74 Buendel (1&1, `buendel_monatlich`), die ihre Summe ueber 36 Monate
# tragen - der Spaltenkopf selbst bleibt stehen (Fremdschluessel in
# `tests/test_seiten_zahlen.py`, dort schreibgeschuetzt), aber die Zeile
# traegt ihren echten Zeitraum jetzt daneben.
#
# P0-B-z3 (22.09.2026, Befund 1): eine weitere Spalte GLEICH DAVOR traegt
# dieselbe Zahl NUR dort, wo "Leitzahl-Zeitraum Monate" wirklich
# `TCO_HORIZONT` (24) ist - fuer die 1&1-Zeilen bleibt sie leer, statt
# unter einem 24-Monats-Kopf zu stehen. Der alte Kopf ("Kosten über 24
# Monate EUR") bleibt unveraendert, wortgleich und weiter voll befuellt.
# P0-B (22.09.2026): die Leitzahl steht in EINER von ZWEI Spalten - unter
# "Kosten über 24 Monate EUR", wenn ihr Zeitraum 24 Monate ist, sonst unter
# "Kosten über die Bündellaufzeit EUR". Kein Test schreibt einen der beiden
# Namen ab (Clean Code 7): die Namen kommen aus dem Modul, das sie schreibt,
# und gelesen wird ueber DIESEN einen Weg.
def _o4_leitzahl(zeile, idx):
    return (zeile[idx[SPALTE_UEBER_24]]
            or zeile[idx[SPALTE_UEBER_LAUFZEIT]])


SPALTEN_TCO = [
    "Art", "Modell", "Speicher GB", "Anbieter", "Anbietertyp", "Tarif",
    "Band", "Zustand", "Zuzahlung EUR", "Tarif/Monat EUR", "Geräterate EUR",
    "Bündel/Monat EUR", "Laufzeit Monate", "Anschlusspreis EUR",
    "Leitzahl-Zeitraum Monate",
    SPALTE_UEBER_24, SPALTE_UEBER_LAUFZEIT, "Abgerufen am",
    "Quelle", "SKU-ID",
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
    kopf, zeilen = tco_csv
    idx = {name: i for i, name in enumerate(kopf)}
    werte = [_o4_leitzahl(z, idx) for z in zeilen
             if _o4_leitzahl(z, idx)]
    assert werte, "keine einzige Leitzahl in der Datei"
    for w in werte:
        assert re.fullmatch(r"-?\d+,\d{2}", w), w


def test_die_leitzahl_zeitraum_spalte_ist_die_von_tco_24(tco_csv):
    """P0-B-h4 (BEFUND HOCH): "Kosten über 24 Monate EUR" behauptete den
    Zeitraum fest, auch fuer 74 Buendel (1&1, `buendel_monatlich`), deren
    Summe ueber 36 Monate laeuft. "Leitzahl-Zeitraum Monate" traegt jetzt
    `tco_model.Tco.leitzahl_monate` - bei einem Buendelmonatspreis dessen
    EIGENE Laufzeit (identisch mit "Laufzeit Monate"), bei der
    aufgeteilten Form IMMER `TCO_HORIZONT` (24), auch wenn die
    Geraeteraten selbst laenger laufen (congstar: 36 Raten in einer
    24-Monats-Leitzahl - "Laufzeit Monate" und "Leitzahl-Zeitraum Monate"
    sind dort verschiedene Zahlen, und genau das ist der Punkt: die eine
    ist die RATENlaufzeit, die andere der Zeitraum der Summe daneben)."""
    from telco_radar.tco_model import TCO_HORIZONT
    kopf, zeilen = tco_csv
    idx = {name: i for i, name in enumerate(kopf)}
    buendel = [z for z in zeilen if z[0] == "Bündel"
               and _o4_leitzahl(z, idx)]
    assert buendel, "keine belastbare Bündel-Zeile im Export"

    mit_buendelpreis = [z for z in buendel if z[idx["Bündel/Monat EUR"]]]
    assert mit_buendelpreis, ("kein Bündelmonatspreis im Bestand - die "
                              "Gegenprobe greift nicht")
    for z in mit_buendelpreis:
        assert (z[idx["Leitzahl-Zeitraum Monate"]]
                == z[idx["Laufzeit Monate"]]), z

    aufgeteilt = [z for z in buendel if not z[idx["Bündel/Monat EUR"]]]
    assert aufgeteilt, "keine aufgeteilte Zeile im Bestand"
    for z in aufgeteilt:
        assert z[idx["Leitzahl-Zeitraum Monate"]] == str(TCO_HORIZONT), z
    # Die Gegenprobe des urspruenglichen Befunds: eine aufgeteilte Zeile
    # mit LAENGEREN Geraeteraten traegt trotzdem die 24-Monats-Leitzahl -
    # "Laufzeit Monate" und "Leitzahl-Zeitraum Monate" laufen auseinander.
    laenger = [z for z in aufgeteilt
               if z[idx["Laufzeit Monate"]] not in ("", str(TCO_HORIZONT))]
    assert laenger, ("keine aufgeteilte Zeile mit abweichender "
                     "Ratenlaufzeit im Bestand - die Gegenprobe greift "
                     "nicht")


def test_die_sim_only_leitzahl_traegt_immer_den_horizont(tco_csv):
    """Eine SIM-only-Referenz laeuft immer ueber `als_buendel()` OHNE
    `buendel_monatlich` (P0-B-h4) - ihr Zeitraum ist deshalb immer
    `TCO_HORIZONT`, aber GELESEN aus derselben Rechnung, nicht als
    Konstante hingeschrieben."""
    from telco_radar.tco_model import TCO_HORIZONT
    kopf, zeilen = tco_csv
    idx = {name: i for i, name in enumerate(kopf)}
    sim = [z for z in zeilen if z[0] == "SIM-only"
           and _o4_leitzahl(z, idx)]
    assert sim, "keine SIM-only-Zeile mit Leitzahl im Export"
    for z in sim:
        assert z[idx["Leitzahl-Zeitraum Monate"]] == str(TCO_HORIZONT), z


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
                 if z[0] == "Bündel" and _o4_leitzahl(z, idx))

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
    assert float(_o4_leitzahl(probe, idx).replace(".", "")
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
    assert float(_o4_leitzahl(probe, idx).replace(".", "")
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
    assert _o4_leitzahl(sim, idx) == "989,75", sim
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
    assert arten == {"Preis-Alarm", "Netzbetreiber",
                     "Händler Barpreis"}, arten


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
        radar_csv):
    """Auch Band-Mismatch und kein Bündel stehen in der Datei - mit Status
    statt %-Zahl. Der Export schreibt den Bestand, die Ansicht kappt."""
    kopf, zeilen = radar_csv
    idx = {name: i for i, name in enumerate(kopf)}
    ohne_zahl = sum(1 for z in zeilen
                    if z[idx["Art"]] == "Netzbetreiber"
                    and not z[idx["Abweichung %"]])
    assert ohne_zahl > 0
    statuswerte = {z[idx["Status"]] for z in zeilen}
    assert "band_mismatch" in statuswerte or "kein_buendel" in statuswerte


def test_preisart_der_netzzeile_nennt_nur_einen_belegten_zeitraum():
    """P0-B-h4 (BEFUND HOCH): direkter Test von `_preisart_netz`. Nur eine
    Zeile mit Status "vergleichbar" teilt NACHWEISLICH denselben Zeitraum
    wie die Vodafone-Referenz (`tco_model.zeitraum_vergleichbar`, von
    `geraete_radar` VOR dieser Zeile schon gezogen) - der Zeitraum kommt
    aus `gruppe['vodafone']['monate']`, gelesen und nicht als Konstante
    24 hingeschrieben. Jede andere Zeile behauptet keinen Zeitraum, den
    diese Datei nicht kennt."""
    from telco_radar.report.geraete_export import _preisart_netz

    gruppe = {"vodafone": {"monate": 24}}
    assert _preisart_netz({"status": "vergleichbar"}, gruppe) == \
        "Kosten über 24 Monate"
    # Gelesen, nicht geraten: eine Referenz mit einem ANDEREN Zeitraum
    # (kaeme aus einem echten Vodafone-Buendel, `_referenz_aus_buendel`)
    # traegt ihre eigene Zahl, nicht die Konstante 24.
    assert _preisart_netz({"status": "vergleichbar"},
                          {"vodafone": {"monate": 36}}) == \
        "Kosten über 36 Monate"
    for status in ("nicht_vergleichbar", "band_mismatch", "kein_buendel"):
        assert _preisart_netz({"status": status}, gruppe) == \
            "Kosten über die Bündellaufzeit", status
    # Ohne Vodafone-Basis (kein Bündel und kein Barpreis fuer das Modell)
    # gibt es auch keinen belegten Zeitraum.
    assert _preisart_netz({"status": "kein_buendel"}, {"vodafone": None}) \
        == "Kosten über die Bündellaufzeit"


def test_keine_1und1_netzzeile_behauptet_24_monate(radar_csv):
    """Gegenprobe am Bestand (P0-B-h4): 1&1 nennt fuer jedes Buendel einen
    Buendelmonatspreis (§ 13.2) - seine Leitzahl traegt seine EIGENE
    Laufzeit (heute durchgehend 36 Monate, 70 Zeilen mit Preis im
    Bestand) und ist damit nie "vergleichbar" mit der 24-Monats-Referenz.
    Vor P0-B-h4 stand in der Preisart-Zelle trotzdem "Kosten über 24
    Monate" - waehrend die Grund-Zelle DERSELBEN Zeile oft ausdruecklich
    "Die Zahl von 1&1 trägt 36 Monate ..." sagt: ein Widerspruch
    innerhalb einer Zeile."""
    kopf, zeilen = radar_csv
    idx = {name: i for i, name in enumerate(kopf)}
    eins = [z for z in zeilen
            if z[idx["Art"]] == "Netzbetreiber"
            and z[idx["Anbieter"]] == "1&1"
            and z[idx["Wettbewerber-Preis EUR"]]]
    assert eins, "keine 1&1-Netzzeile mit Preis im Bestand"
    assert all(z[idx["Status"]] != "vergleichbar" for z in eins), (
        "die Gegenprobe setzt voraus, dass 1&1 im Bestand nie "
        "vergleichbar ist - sonst prueft der Test die falsche Zeile")
    falsch = [z for z in eins
             if z[idx["Preisart"]] == "Kosten über 24 Monate"]
    assert not falsch, falsch


def test_die_alarmzeilen_stehen_als_erster_abschnitt_der_datei(radar_csv):
    """Die Reihenfolge der Arten in der Datei ist die der Sektionen auf
    der Seite: Alarme, dann Abweichung (Netzbetreiber), dann Händler."""
    kopf, zeilen = radar_csv
    idx = kopf.index("Art")
    arten_in_ordnung = [z[idx] for z in zeilen]
    erste = {a: arten_in_ordnung.index(a) for a in set(arten_in_ordnung)}
    assert erste["Preis-Alarm"] < erste[
        "Netzbetreiber"] < erste["Händler Barpreis"], \
        erste


# --------------------------------------------------------------------------
# Export-Links: EINMAL zentral, von beiden Seiten
# --------------------------------------------------------------------------

def test_geraete_verlinkt_den_export_genau_einmal(geraete, site):
    """Seit dem Neuentwurf (29.09.2026) trägt die Geräteseite EINEN
    Export-Link: die Datei der Kosten über 24 Monate
    (`geraete.export.tco.datei`). Genau einmal, und die Datei existiert -
    ein Link ins Leere wäre der teuerste Weg, das herauszufinden."""
    links = [a.get("href") for a in geraete.select("a[href^='exporte/']")]
    assert links == ["exporte/geraete-tco.csv"], links
    assert (site / links[0]).exists(), f"{links[0]} fehlt in site/"


def test_der_export_link_steht_im_fuss_der_seite(geraete):
    """Der EINE Ort des Export-Links ist der Fuß der Kosten-Rangliste
    (`.kv-fuss`), neben dem Link auf die Quellen - nicht im Kopf und
    nicht zwischen Auswahl und Ergebnis."""
    fuss = geraete.select_one("#kosten .kv-fuss")
    assert fuss is not None, "kein Fuß an der Kosten-Rangliste"
    links = geraete.select("a[href^='exporte/']")
    assert links, "kein Export-Link auf der Geräteseite"
    for a in links:
        assert fuss in a.parents, (
            f"Export-Link außerhalb des Fußes: {a.get('href')}")
        assert a.has_attr("download"), "der Export-Link lädt nicht herunter"
    assert fuss.select_one("a[href='geraete-quellen.html']") is not None, (
        "der Quellen-Link fehlt im Fuß")


# ==========================================================================
# P0-B-z3 (22.09.2026) - vier Befunde des Pruefers, alle in dieser Datei.
# Ein Test je Befund, der gegen den ALTEN Stand (vor P0-B-z3) rot wird -
# CLAUDE.md: "Neues Verhalten braucht einen Test, der gegen den alten
# Stand rot wird."
# ==========================================================================

def test_jeder_kopf_traegt_nur_zahlen_die_er_richtig_beschreibt(tco_csv):
    """P0-B (22.09.2026): zwei Koepfe, ein Wert - und keine stumme Zeile.

    Der Befund war ein Kopf, der log: "Kosten über 24 Monate EUR" stand
    fest ueber JEDER Zeile, auch ueber den 74 Buendeln mit kombiniertem
    Monatsbetrag (1&1), deren Summe 36 Monate traegt. Der erste
    Behebungsversuch (h4) stellte den Zeitraum nur DANEBEN; der zweite
    (z3) baute eine zweite Wertspalte "Kosten über 24 Monate EUR (eigener
    Zeitraum)" - ein Name, der sich selbst widerspricht - und liess sie
    fuer genau diese 74 Zeilen LEER, waehrend der alte Kopf den
    36-Monats-Betrag weitertrug.

    Jetzt gilt: eine Zahl steht unter dem Kopf, der sie richtig
    beschreibt, und jede Zeile mit einer Leitzahl hat GENAU EINEN der
    beiden gefuellt. Das sind drei Zusicherungen, und jede kann fallen:
    keine falsch beschriftete Zahl, keine stumme Zeile, kein
    Doppeleintrag.
    """
    kopf, zeilen = tco_csv
    idx = {name: i for i, name in enumerate(kopf)}
    assert SPALTE_UEBER_24 in kopf and SPALTE_UEBER_LAUFZEIT in kopf, kopf
    zeitraum = idx["Leitzahl-Zeitraum Monate"]

    mit_zahl = [z for z in zeilen if _o4_leitzahl(z, idx)]
    assert mit_zahl, "keine einzige Leitzahl in der Datei"

    # 1) Unter dem 24-Monats-Kopf steht nur, was 24 Monate traegt.
    falsch = [z for z in mit_zahl
              if z[idx[SPALTE_UEBER_24]]
              and z[zeitraum] and int(z[zeitraum]) != _O4_HORIZONT]
    assert not falsch, falsch[:4]

    # 2) Und umgekehrt: was 24 Monate traegt, steht nicht in der
    #    Laufzeitspalte. Ohne diese Haelfte waere Punkt 1 auch mit einer
    #    Datei gruen, die ALLES in die Laufzeitspalte schreibt.
    verrutscht = [z for z in mit_zahl
                  if z[idx[SPALTE_UEBER_LAUFZEIT]]
                  and z[zeitraum] and int(z[zeitraum]) == _O4_HORIZONT]
    assert not verrutscht, verrutscht[:4]

    # 3) Genau EINER der zwei Koepfe ist gefuellt - nie beide, nie keiner.
    doppelt = [z for z in mit_zahl
               if z[idx[SPALTE_UEBER_24]] and z[idx[SPALTE_UEBER_LAUFZEIT]]]
    assert not doppelt, doppelt[:4]

    # Gegenprobe, dass der Lookup nicht ins Leere greift: die Fixture
    # traegt beide Faelle wirklich.
    zeitraeume = {int(z[zeitraum]) for z in mit_zahl if z[zeitraum]}
    assert _O4_HORIZONT in zeitraeume, zeitraeume
    assert zeitraeume - {_O4_HORIZONT}, (
        "keine Zeile mit abweichendem Zeitraum - der Test prueft dann nur "
        "die halbe Aussage")


def test_z3_befund2_die_art_behauptet_keinen_zeitraum(radar_csv):
    """Befund 2 (HOCH): "Art" nennt nur die Sektion, keinen Zeitraum mehr.
    Gegen den ALTEN Stand rot: die Art hiess "Netzbetreiber Kosten über 24
    Monate", obwohl in derselben Sektion Zeilen mit "Kosten über die
    Bündellaufzeit" stehen (Preisart-Spalte)."""
    kopf, zeilen = radar_csv
    idx = {name: i for i, name in enumerate(kopf)}
    arten = {z[idx["Art"]] for z in zeilen}
    assert "Netzbetreiber" in arten, arten
    assert not any("Monate" in a for a in arten), (
        f"eine Art behauptet einen Zeitraum: {arten}")


def test_z3_befund3_jede_leere_netzzeile_traegt_ihren_grund(radar_csv):
    """Befund 3 (MITTEL): keine Netzbetreiber-Zeile ohne Abweichung UND
    ohne Grund. Gegen den ALTEN Stand rot: 96 Zeilen (Bestand 22.09.2026)
    ohne Vodafone-Basis trugen weder Prozent noch Grund."""
    kopf, zeilen = radar_csv
    idx = {name: i for i, name in enumerate(kopf)}
    netz = [z for z in zeilen if z[idx["Art"]] == "Netzbetreiber"]
    stumm = [z for z in netz
             if not z[idx["Abweichung %"]] and not z[idx["Grund"]]]
    assert netz, "keine Netzbetreiber-Zeile im Export - Lookup leer"
    assert not stumm, f"{len(stumm)} Zeilen ohne Abweichung UND ohne " \
                      f"Grund: {stumm[:4]}"


def test_z3_befund4_preisart_nennt_zeitraum_nur_mit_derselben_karte(
        radar_csv):
    """Befund 4 (MITTEL): "Kosten über N Monate" steht nur, wo die Zeile
    NACHWEISLICH (Betragsgleichheit) gegen dieselbe Vodafone-Karte prüft,
    deren Zeitraum genannt wird. Direkter Test von `_preisart_netz`, weil
    die zwei Faelle (dieselbe Karte / andere bandspezifische Karte) am
    echten Bestand nicht ohne Weiteres auseinanderzuhalten sind."""
    from telco_radar.report.geraete_export import _preisart_netz

    gruppe = {"vodafone": {"monate": 24, "gesamt": 1000.0}}
    # Dieselbe Karte (vf_gesamt == Referenz-Gesamt): Zeitraum wird genannt.
    assert _preisart_netz(
        {"status": "vergleichbar", "vf_gesamt": 1000.0}, gruppe) == \
        "Kosten über 24 Monate"
    # ANDERE Karte (vf_gesamt weicht ab, z. B. bandspezifische
    # Vodafone-Karte aus `_paar_zeile`): kein behaupteter Zeitraum mehr.
    assert _preisart_netz(
        {"status": "vergleichbar", "vf_gesamt": 1234.56}, gruppe) == \
        "Kosten über die Bündellaufzeit"
