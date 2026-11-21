"""Gegenprobe: Schutzschalter je Anbieter, Beleg beim Scheitern, Zeit je Besuch.

Lauf 21.11.2026: 169 1&1-Besuche scheiterten nacheinander an „Auswahl nicht
gefunden: <Speicher>“, je rund 10 s, zusammen rund 60 % der Laufzeit, und ihre Zeilen
hatten weder Seite noch Bild. Seitdem endet ein Anbieter nach
``SCHUTZ_GLEICHE_FEHLER`` gescheiterten Besuchen gleicher Art (nach einer Sperre
sofort) als benannter Ausfall, und jede Zeile „nicht prüfbar“ nennt Seite und Bild.
"""

from __future__ import annotations

import itertools

from test_beleg_skripte import lade_skript

from telco_radar import gegenprobe as gp
from telco_radar.collect.geraete import gegenprobe_browser as gb
from telco_radar.gegenprobe_reihe import (
    SCHUTZ_GLEICHE_FEHLER,
    Schutzschalter,
    fehlerart,
)

SKRIPT = lade_skript("gegenprobe")
TAG = "2026-11-21"


def test_fehlerart_ohne_einzelheiten():
    assert fehlerart("Auswahl nicht gefunden: 256 GB") == "Auswahl nicht gefunden"
    assert fehlerart("Auswahl nicht gefunden: 1 TB") == "Auswahl nicht gefunden"
    assert fehlerart("Seite antwortet mit HTTP 502") == "Seite antwortet mit HTTP #"


def test_gleiche_fehler_in_folge_schalten_ab():
    schutz = Schutzschalter()
    for n in range(SCHUTZ_GLEICHE_FEHLER - 1):
        schutz.fehler("1-1", f"Auswahl nicht gefunden: {n} GB")
    assert "1-1" not in schutz.aus
    schutz.fehler("1-1", "Auswahl nicht gefunden: 1 TB")
    assert "Auswahl nicht gefunden" in schutz.aus["1-1"]
    assert f"{SCHUTZ_GLEICHE_FEHLER} Seitenbesuche" in schutz.aus["1-1"]


def test_erfolg_oder_andere_fehlerart_beginnt_die_folge_neu():
    schutz = Schutzschalter(grenze=2)
    schutz.fehler("o2", "Auswahl nicht gefunden: 24 Monate")
    schutz.erfolg("o2")
    schutz.fehler("o2", "Auswahl nicht gefunden: 36 Monate")
    schutz.fehler("o2", "Preisbereich nicht gefunden: Dein Angebot")
    assert schutz.aus == {}
    schutz.fehler("telekom", "Auswahl nicht gefunden: 24 Raten")
    assert schutz.aus == {}


def test_sperre_schaltet_sofort_ab():
    schutz = Schutzschalter()
    schutz.fehler("telekom", "HTTP 403", sofort=True)
    assert "Sperre" in schutz.aus["telekom"]


class _Args:
    aufnehmen = None
    gemessen_um = None


def _satz(anbieter: str, n: int) -> dict:
    return {
        "id": f"buendel--{anbieter}--geraet-{n}-256gb-schwarz--tarif--24m",
        "anbieter": anbieter,
        "sku_id": f"geraet-{n}-256gb-schwarz",
        "tarif_name": "Tarif",
        "laufzeit_monate": 24,
        "quelle_url": f"https://{anbieter}.example/{n}",
    }


def _lauf(monkeypatch, saetze, lies_gruppe):
    monkeypatch.setattr(SKRIPT, "lies_gruppe", lies_gruppe)
    lauf = SKRIPT.Lauf(_Args(), None, saetze, TAG, {}, float("inf"), None)
    uhr = itertools.count(0.0, 4.0)
    lauf.uhr = lambda: next(uhr)
    return lauf


def test_lauf_beendet_einen_gestoerten_anbieter_und_nennt_den_ausfall(monkeypatch):
    besucht: list[str] = []

    def lies_gruppe(browser, schluessel, gruppe, kennung, vor_laden, aufnehmen):
        for b in gruppe:
            besucht.append(b["id"])
            yield b, gb.NichtPruefbar(f"Auswahl nicht gefunden: {len(besucht)} GB")

    eins = [_satz("1-1", n) for n in range(SCHUTZ_GLEICHE_FEHLER + 3)]
    saetze = {s["id"]: s for s in eins}
    lauf = _lauf(monkeypatch, saetze, lies_gruppe)
    gruppen = [[(s["id"], gp.ANLASS_AENDERUNG)] for s in eins]
    lauf.alle(gruppen)
    assert len(besucht) == SCHUTZ_GLEICHE_FEHLER
    zeilen = {e.buendel_id: e for e in lauf.zeilen(gruppen)}
    assert len(zeilen) == len(eins)
    offen = [e for e in zeilen.values() if e.status == gp.NICHT_GEGENGEPRUEFT]
    assert len(offen) == 3
    assert all(e.grund.startswith("Ausfall") for e in offen)
    (bilanz,) = lauf.laeufe()
    assert bilanz["besuche"] == SCHUTZ_GLEICHE_FEHLER
    assert bilanz["ausfall"] == offen[0].grund


def test_lauf_misst_sekunden_und_buendel_je_besuch(monkeypatch):
    def lies_gruppe(browser, schluessel, gruppe, kennung, vor_laden, aufnehmen):
        for b in gruppe:
            yield b, gb.Lesung(text="", seite=b["quelle_url"])

    o2 = [_satz("o2", n) for n in range(3)]
    lauf = _lauf(monkeypatch, {s["id"]: s for s in o2}, lies_gruppe)
    lauf.alle([[(o2[0]["id"], gp.ANLASS_FENSTER), (o2[1]["id"], gp.ANLASS_FENSTER)]])
    lauf.alle([[(o2[2]["id"], gp.ANLASS_FENSTER)]])
    (bilanz,) = lauf.laeufe()
    assert (bilanz["besuche"], bilanz["buendel"], bilanz["ausfall"]) == (2, 3, None)
    assert bilanz["sekunden"] > 0


def test_nicht_pruefbar_nennt_seite_und_bild(monkeypatch):
    def lies_gruppe(browser, schluessel, gruppe, kennung, vor_laden, aufnehmen):
        for b in gruppe:
            fehler = gb.NichtPruefbar("Auswahl nicht gefunden: 256 GB")
            fehler.seite, fehler.bild = "https://1-1.example/gesehen", b"RIFFbild"
            yield b, fehler

    satz = _satz("1-1", 1)
    lauf = _lauf(monkeypatch, {satz["id"]: satz}, lies_gruppe)
    lauf.alle([[(satz["id"], gp.ANLASS_FENSTER)]])
    e = lauf.ergebnisse[satz["id"]]
    assert (e.status, e.seite) == (gp.NICHT_PRUEFBAR, "https://1-1.example/gesehen")
    assert lauf.bilder[satz["id"]] == b"RIFFbild"


def test_ohne_bild_nennt_die_zeile_wenigstens_die_angefragte_adresse(monkeypatch):
    def lies_gruppe(browser, schluessel, gruppe, kennung, vor_laden, aufnehmen):
        for b in gruppe:
            yield b, gb.NichtPruefbar("Preisbereich nicht gefunden: Dein Angebot")

    satz = _satz("o2", 1)
    lauf = _lauf(monkeypatch, {satz["id"]: satz}, lies_gruppe)
    lauf.alle([[(satz["id"], gp.ANLASS_FENSTER)]])
    assert lauf.ergebnisse[satz["id"]].seite == satz["quelle_url"]
    assert satz["id"] not in lauf.bilder
