"""Die Prüfstelle im Gerätelauf: jeder Bündelsatz bekommt sein Feld ``pruefung``.

Datenkonzept Geräteradar, Schritt 7. ``vermerke`` prüft den ganzen Bestand vor
``TcoDB.save``; gemessen am Bestand vom 2026-10-03 (Kopie, der Schnappschuss bleibt
unberührt) mit eigenem Orakel für die Regeln 10 und 16 aus den Rohsätzen und der
Frische-Definition der Seite. Scheitert die Prüfung, steht ``unbekannt`` in jedem
Satz. Fester Bezugstag, nie das heutige Datum.
"""

from __future__ import annotations

import json
import shutil
from collections import Counter

import pytest
from bestand_pfad import ZUSTAND, lese_wurzel

from telco_radar.analyze.geraete_pruefstatus import STATUS, UNBEKANNT
from telco_radar.analyze.geraete_pruefstelle import vermerke, vortageswerte
from telco_radar.analyze.geraete_store import GeraeteDB
from telco_radar.analyze.tco_store import TcoDB
from telco_radar.geraete_config import lade_katalog
from telco_radar.report import geraete_notbremse as notbremse
from telco_radar.report.geraete_tco_karten import geraet_aus_sku, ist_frisch
from telco_radar.tarif_bezug import Tarifbestand

HEUTE = "2026-10-03"
DATEI = "geraete_tco.json"
HISTORIE = "geraete_tco_historie.jsonl"


def _tco(ordner) -> TcoDB:
    shutil.copy(ZUSTAND / DATEI, ordner / DATEI)
    return TcoDB(ordner / DATEI, historie_path=ZUSTAND / HISTORIE)


def _vermerke(tco: TcoDB, db=None) -> Counter:
    return vermerke(
        tco,
        db or GeraeteDB(ZUSTAND / "geraete_db.json"),
        Tarifbestand.aus_datei(ZUSTAND / "tarife.jsonl"),
        HEUTE,
        ist_frisch,
        geraet_aus_sku,
        lade_katalog(lese_wurzel()),
    )


@pytest.fixture(scope="module")
def geprueft(tmp_path_factory):
    ordner = tmp_path_factory.mktemp("pruefstelle")
    tco = _tco(ordner)
    zahlen = _vermerke(tco)
    tco.save(HEUTE)
    gespeichert = json.loads((ordner / DATEI).read_text(encoding="utf-8"))
    return zahlen, gespeichert["buendel"]


def _regel(satz: dict) -> set:
    return {g["regel"] for g in satz["pruefung"]["gruende"]}


def test_jeder_gespeicherte_satz_traegt_einen_status(geprueft):
    zahlen, saetze = geprueft
    assert len(saetze) > 1000, "Bestand zu klein für eine Aussage"
    gezaehlt = Counter(s["pruefung"]["status"] for s in saetze)
    assert set(gezaehlt) <= set(STATUS), gezaehlt
    assert gezaehlt == zahlen, "Rückgabe und gespeicherte Felder zählen gleich"
    assert gezaehlt["quarantaene"] > 0 and gezaehlt["gueltig"] > 0, gezaehlt


def test_frische_gegen_die_definition_der_seite(geprueft):
    _, saetze = geprueft
    alt = {s["id"] for s in saetze if not ist_frisch(s["abgerufen_am"], HEUTE)}
    assert alt, "Bestand ohne gealterten Satz: Orakel ohne Fall"
    assert {s["id"] for s in saetze if 16 in _regel(s)} == alt
    gueltig = [s for s in saetze if s["pruefung"]["status"] == "gueltig"]
    assert not any(s["id"] in alt for s in gueltig), "Gegenprobe: gültig ist frisch"


def test_abgelaufene_aktion_gegen_die_rohsaetze(geprueft):
    _, saetze = geprueft
    abgelaufen = {
        s["id"]
        for s in saetze
        for a in s.get("aktionen") or []
        if a.get("eingerechnet") and (a.get("gueltig_bis") or "9999") < HEUTE
    }
    assert {s["id"] for s in saetze if 10 in _regel(s)} == abgelaufen
    for s in saetze:
        if s["id"] in abgelaufen:
            assert s["pruefung"]["status"] in ("veraltet", "quarantaene"), s["id"]


def test_ein_gesperrter_satz_zaehlt_nicht(geprueft):
    _, saetze = geprueft
    for s in saetze:
        zaehlt = notbremse.zaehlt(notbremse.felder_aus_satz(s, HEUTE))
        if s["pruefung"]["status"] != "gueltig":
            assert not zaehlt, s["id"]


def test_heutige_daten_fehlen_und_sind_nicht_pruefbar(geprueft):
    """Gerätesumme der Seite, Echo und Beleg liefert erst der Klick-Crawler."""
    _, saetze = geprueft
    for s in saetze:
        assert {1, 9, 13} <= set(s["pruefung"]["nicht_pruefbar"]), s["id"]


class _KaputteDB:
    def eintraege(self):
        raise OSError("Listungen nicht lesbar")


def test_gescheiterte_pruefung_schreibt_unbekannt_in_jeden_satz(tmp_path, caplog):
    tco = _tco(tmp_path)
    zahlen = _vermerke(tco, db=_KaputteDB())
    assert zahlen == Counter({UNBEKANNT: len(tco.buendel())})
    fehler = {"status": UNBEKANNT, "fehler": "OSError: Listungen nicht lesbar"}
    assert all(s["pruefung"] == fehler for s in tco.buendel())
    assert "Prüfstelle gescheitert" in caplog.text
    satz = tco.buendel()[0]
    assert not notbremse.zaehlt(notbremse.felder_aus_satz(satz, HEUTE))


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
