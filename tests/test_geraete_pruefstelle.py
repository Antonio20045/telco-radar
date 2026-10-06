"""Die Prüfstelle im Gerätelauf: jeder Bündelsatz bekommt sein Feld ``pruefung``.

Datenkonzept Geräteradar, Schritt 7. ``vermerke`` prüft den ganzen Bestand vor
``TcoDB.save``; gemessen am Bestand vom 2026-10-03 (Kopie, der Schnappschuss bleibt
unberührt) mit eigenem Orakel für die Regeln 10 und 16 aus den Rohsätzen und der
Frische-Definition der Seite. Scheitert die Prüfung, auch an einer Regel mit
unerwartetem Fehler, steht ``unbekannt`` mit dem Fehler in jedem Satz und in den
Kennzahlen. Der Vermerk je Satz ist kurz: der gespeicherte Bestand wächst um weniger als
``ZUWACHS_HOECHSTENS`` Bytes. Fester Bezugstag, nie das heutige Datum.
"""

from __future__ import annotations

import json
import shutil
from collections import Counter

import pytest
from bestand_pfad import ZUSTAND, lese_wurzel

from telco_radar.analyze import geraete_regeln
from telco_radar.analyze.geraete_pruefstatus import (
    STATUS,
    UNBEKANNT,
    Vermerk,
    lies_vermerk,
)
from telco_radar.analyze.geraete_pruefstelle import Seite, vermerke, vortageswerte
from telco_radar.analyze.geraete_store import GeraeteDB
from telco_radar.analyze.tco_store import TcoDB
from telco_radar.geraete_config import lade_katalog
from telco_radar.geraete_pipeline import abgesichert
from telco_radar.report import geraete_notbremse as notbremse
from telco_radar.report.geraete_tco_karten import geraet_aus_sku, ist_frisch
from telco_radar.tarif_bezug import Tarifbestand

HEUTE = "2026-10-03"
DATEI = "geraete_tco.json"
HISTORIE = "geraete_tco_historie.jsonl"
ZUWACHS_HOECHSTENS = 300_000


def _tco(ordner) -> TcoDB:
    shutil.copy(ZUSTAND / DATEI, ordner / DATEI)
    return TcoDB(ordner / DATEI, historie_path=ZUSTAND / HISTORIE)


def _vermerke(tco: TcoDB, db=None) -> Counter:
    return vermerke(
        tco,
        db or GeraeteDB(ZUSTAND / "geraete_db.json"),
        Tarifbestand.aus_datei(ZUSTAND / "tarife.jsonl"),
        HEUTE,
        Seite(ist_frisch, geraet_aus_sku, lade_katalog(lese_wurzel())),
        abgesichert,
    )


@pytest.fixture(scope="module")
def geprueft(tmp_path_factory):
    ordner = tmp_path_factory.mktemp("pruefstelle")
    tco = _tco(ordner)
    zahlen = _vermerke(tco)
    tco.save(HEUTE)
    gespeichert = json.loads((ordner / DATEI).read_text(encoding="utf-8"))
    groesse = (ordner / DATEI).stat().st_size
    return zahlen, gespeichert["buendel"], gespeichert["pruefung"], groesse


def _status(satz: dict) -> str | None:
    return lies_vermerk(satz.get("pruefung")).status


def _regel(satz: dict) -> set:
    return set(lies_vermerk(satz.get("pruefung")).regeln)


def test_jeder_gespeicherte_satz_traegt_einen_status(geprueft):
    zahlen, saetze, *_ = geprueft
    assert len(saetze) > 1000, "Bestand zu klein für eine Aussage"
    gezaehlt = Counter(_status(s) for s in saetze)
    assert set(gezaehlt) <= set(STATUS), gezaehlt
    assert gezaehlt == zahlen, "Rückgabe und gespeicherte Felder zählen gleich"
    assert gezaehlt["quarantaene"] > 0 and gezaehlt["gueltig"] > 0, gezaehlt


def test_frische_gegen_die_definition_der_seite(geprueft):
    _, saetze, *_ = geprueft
    alt = {s["id"] for s in saetze if not ist_frisch(s["abgerufen_am"], HEUTE)}
    assert alt, "Bestand ohne gealterten Satz: Orakel ohne Fall"
    assert {s["id"] for s in saetze if 16 in _regel(s)} == alt
    gueltig = [s for s in saetze if _status(s) == "gueltig"]
    assert not any(s["id"] in alt for s in gueltig), "Gegenprobe: gültig ist frisch"


def test_abgelaufene_aktion_gegen_die_rohsaetze(geprueft):
    _, saetze, *_ = geprueft
    abgelaufen = {
        s["id"]
        for s in saetze
        for a in s.get("aktionen") or []
        if a.get("eingerechnet") and (a.get("gueltig_bis") or "9999") < HEUTE
    }
    assert {s["id"] for s in saetze if 10 in _regel(s)} == abgelaufen
    for s in saetze:
        if s["id"] in abgelaufen:
            assert _status(s) in ("veraltet", "quarantaene"), s["id"]


def test_ein_gesperrter_satz_zaehlt_nicht(geprueft):
    _, saetze, *_ = geprueft
    for s in saetze:
        zaehlt = notbremse.zaehlt(notbremse.felder_aus_satz(s, HEUTE))
        if _status(s) != "gueltig":
            assert not zaehlt, s["id"]


def test_heutige_daten_fehlen_und_sind_nicht_pruefbar(geprueft):
    """Gerätesumme der Seite, Echo und Beleg liefert erst der Klick-Crawler;
    Tarifbindung und Preisphasen ergänzt erst die Ansicht aus dem Tarifblatt."""
    _, saetze, lauf, _ = geprueft
    regeln = {r["nr"]: r for r in lauf["regeln"]}
    for nr in (1, 7, 8, 9, 13):
        assert regeln[nr]["nicht_pruefbar"] == len(saetze), nr
        assert regeln[nr]["verletzt"] == 0, nr
    assert lauf["lauf"] == HEUTE and lauf["summe"]["buendel"] == len(saetze)


def test_der_vermerk_je_satz_ist_kurz(geprueft, tmp_path):
    """Nur Status und Regelnummern je Satz; Sätze je Regel stehen in ``REGELN``."""
    _, saetze, _, nachher = geprueft
    for s in saetze:
        vermerk = lies_vermerk(s["pruefung"])
        assert vermerk.status in STATUS, s["pruefung"]
        assert vermerk.als_text() == s["pruefung"], "Text und Lesart decken sich"
    ohne = _tco(tmp_path)
    ohne.save(HEUTE)
    vorher = (tmp_path / DATEI).stat().st_size
    assert 0 < nachher - vorher < ZUWACHS_HOECHSTENS, nachher - vorher


def test_vermerk_hin_und_zurueck():
    for vermerk in (
        Vermerk("gueltig"),
        Vermerk("quarantaene", (3, 5)),
        Vermerk("veraltet", (16,)),
        Vermerk(UNBEKANNT, fehler="RuntimeError: kaputt"),
    ):
        assert lies_vermerk(vermerk.als_text()) == vermerk
    assert lies_vermerk(None) == Vermerk(None), "nie geprüft"
    assert lies_vermerk("gueltig drei").status == UNBEKANNT, "unlesbar ist unbekannt"
    assert lies_vermerk({"status": "gueltig"}).status == UNBEKANNT


class _KaputteDB:
    def eintraege(self):
        raise OSError("Listungen nicht lesbar")


def _gescheitert(tco: TcoDB, fehler: str, caplog) -> None:
    assert all(s["pruefung"] == f"{UNBEKANNT} {fehler}" for s in tco.buendel())
    assert tco.pruefung is not None
    summe = tco.pruefung["summe"]
    assert (summe["gescheitert"], summe["fehler"]) == (len(tco.buendel()), fehler)
    assert "Prüfstelle gescheitert" in caplog.text
    satz = tco.buendel()[0]
    assert not notbremse.zaehlt(notbremse.felder_aus_satz(satz, HEUTE))


def test_gescheiterte_pruefung_schreibt_unbekannt_in_jeden_satz(tmp_path, caplog):
    tco = _tco(tmp_path)
    zahlen = _vermerke(tco, db=_KaputteDB())
    assert zahlen == Counter({UNBEKANNT: len(tco.buendel())})
    _gescheitert(tco, "OSError: Listungen nicht lesbar", caplog)


def test_eine_regel_mit_unerwartetem_fehler_kostet_keinen_messtag(
    tmp_path, caplog, monkeypatch
):
    def _kaputt(*_args, **_kw):
        raise RuntimeError("Regel kaputt")

    monkeypatch.setattr(geraete_regeln, "sim_only_preis", _kaputt)
    tco = _tco(tmp_path)
    zahlen = _vermerke(tco)
    assert zahlen == Counter({UNBEKANNT: len(tco.buendel())})
    _gescheitert(tco, "RuntimeError: Regel kaputt", caplog)
    tco.save(HEUTE)
    gespeichert = json.loads((tmp_path / DATEI).read_text(encoding="utf-8"))
    assert gespeichert["pruefung"]["summe"]["gescheitert"] == len(tco.buendel())


def test_vortag_ist_die_letzte_messung_vor_dem_abruf(tmp_path, caplog):
    historie = tmp_path / HISTORIE
    bid = "buendel--o2--phone--tarif--24m"
    zeilen = [
        {"id": bid, "laufzeit_monate": 24, "datum": "2026-09-30", "tarif": 1},
        {"id": bid, "laufzeit_monate": 24, "datum": "2026-10-02", "tarif": 2},
        {"id": bid, "laufzeit_monate": 24, "datum": "2026-10-03", "tarif": 3},
        {"id": bid, "laufzeit_monate": 24, "datum": "2026-10-01", "tarif": 4},
    ]
    text = "\n".join(json.dumps(z) for z in zeilen) + "\n{kaputt\n"
    historie.write_text(text, encoding="utf-8")
    vortag = vortageswerte(historie, {bid: "2026-10-03"})
    assert vortag[bid]["tarif"] == 2, "letzte Messung VOR dem Abruf, nicht der Tag"
    assert "1 Zeilen der Historie unlesbar" in caplog.text
    assert vortageswerte(historie, {bid: "2026-09-30"}) == {}, "erster Abruf"
    assert vortageswerte(tmp_path / "fehlt.jsonl", {bid: HEUTE}) == {}
