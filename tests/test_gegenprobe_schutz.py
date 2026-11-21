"""Gegenprobe: Schutzschalter je Anbieter, Beleg beim Scheitern, Zeit je Besuch.

Lauf 21.11.2026: 169 1&1-Besuche scheiterten nacheinander an „Auswahl nicht
gefunden: <Speicher>“, je rund 10 s, zusammen rund 60 % der Laufzeit, und ihre Zeilen
hatten weder Seite noch Bild. Seitdem besucht ein Anbieter nach
``SCHUTZ_GLEICHE_FEHLER`` gescheiterten Besuchen gleicher Art nur noch bekannt lesbare
Seiten, nach einer zweiten Serie oder einer Sperre keine mehr, jeder Schritt benannt;
jede Zeile „nicht prüfbar“ nennt Seite und Bild.
"""

from __future__ import annotations

import itertools

from test_beleg_skripte import lade_skript

from telco_radar import gegenprobe as gp
from telco_radar.collect.geraete import gegenprobe_browser as gb
from telco_radar.gegenprobe_reihe import (
    AUS,
    FREI,
    NUR_BEKANNT,
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


def test_erste_serie_beschraenkt_zweite_schaltet_ab():
    schutz = Schutzschalter()
    for n in range(SCHUTZ_GLEICHE_FEHLER - 1):
        schutz.fehler("1-1", f"Auswahl nicht gefunden: {n} GB")
    assert (schutz.stufe("1-1"), schutz.grund("1-1")) == (FREI, None)
    schutz.fehler("1-1", "Auswahl nicht gefunden: 1 TB")
    assert schutz.stufe("1-1") == NUR_BEKANNT
    assert "nur noch bekannt lesbare Seiten" in (schutz.grund("1-1") or "")
    for n in range(SCHUTZ_GLEICHE_FEHLER):
        schutz.fehler("1-1", f"Auswahl nicht gefunden: {n} GB")
    assert schutz.stufe("1-1") == AUS
    assert len(schutz.ausfaelle("1-1")) == 2


def test_erfolg_oder_andere_fehlerart_beginnt_die_folge_neu():
    schutz = Schutzschalter(grenze=2)
    schutz.fehler("o2", "Auswahl nicht gefunden: 24 Monate")
    schutz.erfolg("o2")
    schutz.fehler("o2", "Auswahl nicht gefunden: 36 Monate")
    schutz.fehler("o2", "Preisbereich nicht gefunden: Dein Angebot")
    schutz.fehler("telekom", "Auswahl nicht gefunden: 24 Raten")
    assert schutz.abgeschaltet() == []


def test_sperre_schaltet_sofort_ab():
    schutz = Schutzschalter()
    schutz.fehler("telekom", "HTTP 403", sofort=True)
    assert schutz.stufe("telekom") == AUS
    assert "Sperre" in (schutz.grund("telekom") or "")


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


def _scheitert(ids: set[str], besucht: list[str], fehler=gb.NichtPruefbar):
    def lies_gruppe(browser, schluessel, gruppe, kennung, vor_laden, aufnehmen):
        for b in gruppe:
            besucht.append(b["id"])
            if b["id"] in ids:
                yield b, fehler(f"Auswahl nicht gefunden: {len(besucht)} GB")
            else:
                yield b, gb.Lesung(text="", seite=b["quelle_url"])

    return lies_gruppe


def test_nach_serie_nur_bekannt_lesbare_seiten(monkeypatch):
    neu = [_satz("1-1", n) for n in range(SCHUTZ_GLEICHE_FEHLER + 3)]
    bekannt = [_satz("1-1", n) for n in range(100, 104)]
    saetze = {s["id"]: s for s in neu + bekannt}
    besucht: list[str] = []
    lauf = _lauf(monkeypatch, saetze, _scheitert({s["id"] for s in neu}, besucht))
    lauf.bekannt_gut = {s["id"] for s in bekannt}
    gruppen = [[(s["id"], gp.ANLASS_AENDERUNG)] for s in neu + bekannt]
    lauf.alle(gruppen)
    assert besucht == [s["id"] for s in neu[:SCHUTZ_GLEICHE_FEHLER] + bekannt]
    offen = [e for e in lauf.zeilen(gruppen) if e.status == gp.NICHT_GEGENGEPRUEFT]
    assert len(offen) == 3
    assert all("nur noch bekannt lesbare Seiten" in (e.grund or "") for e in offen)
    (eintrag,) = lauf.laeufe()
    assert eintrag["besuche"] == SCHUTZ_GLEICHE_FEHLER + len(bekannt)
    assert "bekannt lesbare" in eintrag["ausfall"]


def test_serie_auch_auf_bekannten_seiten_schaltet_ab(monkeypatch):
    eins = [_satz("1-1", n) for n in range(3 * SCHUTZ_GLEICHE_FEHLER)]
    saetze = {s["id"]: s for s in eins}
    besucht: list[str] = []
    lauf = _lauf(monkeypatch, saetze, _scheitert(set(saetze), besucht))
    lauf.bekannt_gut = set(saetze)
    lauf.alle([[(s["id"], gp.ANLASS_FENSTER)] for s in eins])
    assert len(besucht) == 2 * SCHUTZ_GLEICHE_FEHLER
    assert lauf.schutz.stufe("1-1") == AUS


def test_sperre_stoppt_alles(monkeypatch):
    eins = [_satz("telekom", n) for n in range(4)]
    saetze = {s["id"]: s for s in eins}
    besucht: list[str] = []
    lies = _scheitert(set(saetze), besucht, fehler=gb.Gesperrt)
    lauf = _lauf(monkeypatch, saetze, lies)
    lauf.bekannt_gut = set(saetze)
    lauf.alle([[(s["id"], gp.ANLASS_FENSTER)] for s in eins])
    assert len(besucht) == 1
    assert "Sperre" in (lauf.laeufe()[0]["ausfall"] or "")


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
