"""Gegenprobe: Schutzschalter je Anbieter, Beleg beim Scheitern, Zeit je Besuch.

Lauf 21.11.2026: 169 1&1-Besuche scheiterten nacheinander an „Auswahl nicht
gefunden: <Speicher>“, je rund 10 s, zusammen rund 60 % der Laufzeit, und ihre Zeilen
hatten weder Seite noch Bild. Eine Fehlerserie sagt aber nichts über die nächste Seite
(dritte Prüfung zu PR 200): den ganzen Anbieter stoppt nur eine Sperre oder eine Serie
von ``SCHUTZ_SERVERFEHLER`` Serverfehlern (gestörter Host), Formfehler nie; die
Wiederholung gescheiterter Seiten begrenzt ``VERDAECHTIG_JE_NACHT``
(``test_gegenprobe_naechte``). Jede Zeile „nicht prüfbar“ nennt Seite und Bild.
"""

from __future__ import annotations

import itertools

from test_beleg_skripte import lade_skript

from telco_radar import gegenprobe as gp
from telco_radar.collect.geraete import gegenprobe_browser as gb
from telco_radar.gegenprobe_reihe import (
    AUS,
    FREI,
    SCHUTZ_SERVERFEHLER,
    Schutzschalter,
    fehlerart,
    ist_serverfehler,
)

SKRIPT = lade_skript("gegenprobe")
TAG = "2026-11-21"


def test_fehlerart_ohne_einzelheiten():
    assert fehlerart("Auswahl nicht gefunden: 256 GB") == "Auswahl nicht gefunden"
    assert fehlerart("Auswahl nicht gefunden: 1 TB") == "Auswahl nicht gefunden"
    assert fehlerart("Seite antwortet mit HTTP 502") == "Seite antwortet mit HTTP #"


def test_serverfehler_erkannt_formfehler_nicht():
    assert ist_serverfehler("Seite antwortet mit HTTP 502")
    assert ist_serverfehler("Browser: Page.goto: net::ERR_CONNECTION_RESET at …")
    assert not ist_serverfehler("Browser: Page.goto: Timeout 45000ms exceeded.")
    assert not ist_serverfehler("Auswahl nicht gefunden: 256 GB")
    assert not ist_serverfehler("Browser: Locator.click: Timeout 8000ms exceeded.")


def test_serverfehler_in_folge_stoppen_den_anbieter():
    schutz = Schutzschalter()
    for _ in range(SCHUTZ_SERVERFEHLER - 1):
        schutz.fehler("o2", "Seite antwortet mit HTTP 503")
    assert (schutz.stufe("o2"), schutz.grund("o2")) == (FREI, None)
    schutz.fehler("o2", "Seite antwortet mit HTTP 503")
    assert schutz.stufe("o2") == AUS
    assert "Serverfehler" in (schutz.grund("o2") or "")


def test_formfehler_stoppen_nie_und_unterbrechen_die_serverserie():
    schutz = Schutzschalter(grenze=2)
    for n in range(50):
        schutz.fehler("1-1", f"Auswahl nicht gefunden: {n} GB")
    schutz.fehler("o2", "Seite antwortet mit HTTP 500")
    schutz.fehler("o2", "Auswahl nicht gefunden: 24 Monate")
    schutz.fehler("o2", "Seite antwortet mit HTTP 500")
    schutz.erfolg("o2")
    schutz.fehler("o2", "Seite antwortet mit HTTP 500")
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


def test_formfehler_halten_den_anbieter_nie_an(monkeypatch):
    eins = [_satz("1-1", n) for n in range(4 * SCHUTZ_SERVERFEHLER)]
    saetze = {s["id"]: s for s in eins}
    besucht: list[str] = []
    lauf = _lauf(monkeypatch, saetze, _scheitert(set(saetze), besucht))
    gruppen = [[(s["id"], gp.ANLASS_AENDERUNG)] for s in eins]
    lauf.alle(gruppen)
    assert len(besucht) == len(eins)
    assert lauf.laeufe()[0]["ausfall"] is None


def test_serverfehler_in_folge_stoppen_den_lauf_des_anbieters(monkeypatch):
    def http_503(text):
        return gb.NichtPruefbar("Seite antwortet mit HTTP 503")

    eins = [_satz("o2", n) for n in range(3 * SCHUTZ_SERVERFEHLER)]
    saetze = {s["id"]: s for s in eins}
    besucht: list[str] = []
    lauf = _lauf(monkeypatch, saetze, _scheitert(set(saetze), besucht, http_503))
    gruppen = [[(s["id"], gp.ANLASS_AENDERUNG)] for s in eins]
    lauf.alle(gruppen)
    assert len(besucht) == SCHUTZ_SERVERFEHLER
    offen = [e for e in lauf.zeilen(gruppen) if e.status == gp.NICHT_GEGENGEPRUEFT]
    assert len(offen) == 2 * SCHUTZ_SERVERFEHLER
    assert all("Serverfehler" in (e.grund or "") for e in offen)


def test_sperre_stoppt_alles(monkeypatch):
    eins = [_satz("telekom", n) for n in range(4)]
    saetze = {s["id"]: s for s in eins}
    besucht: list[str] = []
    lies = _scheitert(set(saetze), besucht, fehler=gb.Gesperrt)
    lauf = _lauf(monkeypatch, saetze, lies)
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
