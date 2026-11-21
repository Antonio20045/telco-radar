"""Bilanz der Gegenprobe je Anbieter und Tag (``gegenprobe_bilanz``) und das Ablegen
der Teildateien einer Matrix (``scripts/gegenprobe_ablegen.py``).

Jede Zahl steht an EINER Stelle (``zusammenfassung``); die Seite und ein Wächter lesen
die Datei ``data/state/gegenprobe/bilanz/<datum>.json``. Die Tests zählen die Fälle
von Hand nach und prüfen dazu, dass sich die Teile zum Ganzen fügen (Gegenprobe).
"""

from __future__ import annotations

import json
from pathlib import Path

from test_beleg_skripte import lade_skript

from telco_radar import gegenprobe as gp
from telco_radar import gegenprobe_bilanz as gb
from telco_radar import gegenprobe_fenster as gf
from telco_radar.report import geraete_preisbeleg as pb

ABLEGEN = lade_skript("gegenprobe_ablegen")
TAG = "2026-11-21"


def _satz(anbieter: str, n: int, **anders) -> dict:
    werte = {
        "id": f"buendel--{anbieter}--geraet-{n}-128gb-schwarz--tarif--24m",
        "anbieter": {"o2": "o2", "1-1": "1&1"}[anbieter],
        "sku_id": f"geraet-{n}-128gb-schwarz",
        "tarif_name": "Tarif",
        "tarif_monatlich": 10.0,
        "geraet_monatsrate": 5.0,
        "geraet_zuzahlung": 1.0,
        "anschlusspreis": 0.0,
        "laufzeit_monate": 24,
        "abgerufen_am": TAG,
    }
    werte.update(anders)
    return werte


def _probe(satz: dict, datum: str, status: str, **anders) -> gp.Ergebnis:
    werte = {
        "datum": datum,
        "buendel_id": satz["id"],
        "anbieter": satz["anbieter"],
        "status": status,
        "anlass": gp.ANLASS_FENSTER,
        "gesamt_gespeichert": gb.gesamt_von(satz),
    }
    if status in (gp.NICHT_PRUEFBAR, gp.NICHT_GEGENGEPRUEFT, gp.TEILWEISE):
        werte["grund"] = "Auswahl nicht gefunden: 256 GB"
    if status == gp.ABWEICHEND:
        werte["abweichungen"] = [
            {"feld": "geraet_monatsrate", "gespeichert": 5.0, "gelesen": 6.0}
        ]
    if status == gp.ERFASSUNGSLUECKE:
        werte["luecken"] = [
            {"feld": "anschlusspreis", "gespeichert": None, "gelesen": 1}
        ]
    werte.update(anders)
    return gp.Ergebnis(**werte)


O2 = [_satz("o2", n) for n in range(6)]
EINS = [_satz("1-1", n) for n in range(2)]


def _proben() -> list[gp.Ergebnis]:
    """o2: 0 heute bestätigt, 1 vor 5 Tagen bestätigt, 2 Lücke, 3 vor 7 Tagen
    (abgelaufen), 4 abweichend, 5 nie; 1&1: 0 nicht prüfbar, 1 nicht geöffnet. Erst im
    Test gebaut: die Gesamtkosten hängen am Versand, den das Modul-Fixture setzt."""
    return [
        _probe(O2[0], TAG, gp.BESTAETIGT),
        _probe(O2[1], "2026-11-16", gp.BESTAETIGT),
        _probe(O2[2], "2026-11-20", gp.ERFASSUNGSLUECKE),
        _probe(O2[3], "2026-11-14", gp.BESTAETIGT),
        _probe(O2[4], "2026-11-20", gp.ABWEICHEND),
        _probe(EINS[0], TAG, gp.NICHT_PRUEFBAR),
        _probe(EINS[1], TAG, gp.NICHT_GEGENGEPRUEFT),
    ]


LAEUFE = [
    {"datum": TAG, "anbieter": "o2", "besuche": 2, "sekunden": 24.0, "buendel": 3},
    {"datum": TAG, "anbieter": "o2", "besuche": 1, "sekunden": 12.0, "buendel": 1},
    {
        "datum": TAG,
        "anbieter": "1-1",
        "besuche": 5,
        "sekunden": 50.0,
        "buendel": 5,
        "ausfall": "Ausfall: 5 Seitenbesuche in Folge gescheitert",
    },
    {
        "datum": "2026-11-20",
        "anbieter": "o2",
        "besuche": 9,
        "sekunden": 1.0,
        "buendel": 9,
    },
]


def _bilanz():
    return gb.zusammenfassung(TAG, O2 + EINS, gf.Gegenproben(_proben()), LAEUFE)


def test_zaehlt_je_anbieter_von_hand_nachgezaehlt():
    o2 = _bilanz()["anbieter"]["o2"]
    assert o2["name"] == "o2"
    assert (o2["angezeigt"], o2["im_fenster"], o2["ueberfaellig"]) == (6, 4, 2)
    assert (o2[gp.BESTAETIGT], o2[gp.ERFASSUNGSLUECKE], o2[gp.ABWEICHEND]) == (2, 1, 1)
    assert (o2["heute_geprueft"], o2["nicht_pruefbar"], o2["pruefbar"]) == (1, 0, 6)
    assert o2["anteil_bestaetigt"] == round(2 / 6, 4)
    assert (o2["besuche"], o2["sekunden_je_besuch"], o2["buendel_je_besuch"]) == (
        3,
        12.0,
        1.33,
    )


def test_nicht_pruefbar_nur_mit_grund_und_ausfall_benannt():
    eins = _bilanz()["anbieter"]["1-1"]
    assert (eins["angezeigt"], eins["im_fenster"], eins["ueberfaellig"]) == (2, 0, 2)
    assert eins["nicht_pruefbar"] == 1
    assert eins["gruende"] == {"Auswahl nicht gefunden": 1}
    assert eins["pruefbar"] == 1
    assert eins["ausfall"] == ["Ausfall: 5 Seitenbesuche in Folge gescheitert"]


def test_teile_fuegen_sich_zur_summe():
    bilanz = _bilanz()
    summe = bilanz["summe"]
    for name in (
        "angezeigt",
        "im_fenster",
        "ueberfaellig",
        "besuche",
        "nicht_pruefbar",
    ):
        assert summe[name] == sum(e[name] for e in bilanz["anbieter"].values())
    for e in (*bilanz["anbieter"].values(), summe):
        assert e["im_fenster"] + e["ueberfaellig"] == e["angezeigt"]
        assert e["im_fenster"] == sum(e[s] for s in gp.GEPRUEFT)
    assert bilanz["fenster_tage"] == gf.GEGENPROBE_FENSTER_TAGE == 7


def test_ohne_besuch_keine_zeit_je_besuch():
    bilanz = gb.zusammenfassung(TAG, O2, gf.Gegenproben(), [])
    o2 = bilanz["anbieter"]["o2"]
    assert (o2["sekunden_je_besuch"], o2["buendel_je_besuch"]) == (None, None)
    assert (o2["im_fenster"], o2["ueberfaellig"]) == (0, 6)


def _bestand(wurzel, saetze):
    pfad = wurzel / "data" / "state" / "geraete_tco.json"
    pfad.parent.mkdir(parents=True, exist_ok=True)
    pfad.write_text(json.dumps({"updated": TAG, "buendel": saetze}), encoding="utf-8")


def _teil(ordner, name, ergebnisse, laeufe):
    ordner.mkdir(parents=True)
    gp.schreibe_tag(ordner / f"{name}.jsonl", ergebnisse)
    (ordner / f"{name}.lauf.json").write_text(json.dumps(laeufe), encoding="utf-8")


def test_ablegen_fuehrt_die_teile_zusammen_und_ergaenzt(tmp_path):
    _bestand(tmp_path, O2 + EINS)
    quelle = tmp_path / "teile"
    _teil(quelle / "gegenprobe-o2", "o2", [_proben()[0]], [LAEUFE[0]])
    _teil(quelle / "gegenprobe-1-1", "1-1", [_proben()[5]], [LAEUFE[2]])
    assert ABLEGEN.main(["--root", str(tmp_path), "--quelle", str(quelle)]) == 0
    zweiter = tmp_path / "zweiter"
    _teil(
        zweiter / "gegenprobe-o2",
        "o2",
        [_probe(O2[5], TAG, gp.BESTAETIGT)],
        [LAEUFE[1]],
    )
    assert ABLEGEN.main(["--root", str(tmp_path), "--quelle", str(zweiter)]) == 0
    tag = {e.buendel_id: e.status for e in gp.lies_tag(gp.tagesdatei(tmp_path, TAG))}
    assert tag == {
        O2[0]["id"]: gp.BESTAETIGT,
        O2[5]["id"]: gp.BESTAETIGT,
        EINS[0]["id"]: gp.NICHT_PRUEFBAR,
    }
    bilanz = json.loads(gb.bilanzdatei(tmp_path, TAG).read_text(encoding="utf-8"))
    assert len(bilanz["laeufe"]) == 3
    assert bilanz["anbieter"]["o2"]["im_fenster"] == 2
    assert bilanz["anbieter"]["o2"]["besuche"] == 3
    assert bilanz["anbieter"]["1-1"]["ausfall"] == [LAEUFE[2]["ausfall"]]


def test_ablegen_meldet_eine_unlesbare_teildatei(tmp_path):
    _bestand(tmp_path, O2)
    quelle = tmp_path / "teile"
    _teil(quelle / "a", "o2", [_proben()[0]], [LAEUFE[0]])
    (quelle / "a" / "kaputt.jsonl").write_text("{kein json\n", encoding="utf-8")
    assert ABLEGEN.main(["--root", str(tmp_path), "--quelle", str(quelle)]) == 1
    assert gp.lies_tag(gp.tagesdatei(tmp_path, TAG))[0].buendel_id == O2[0]["id"]


def test_seite_und_bilanz_lesen_dieselbe_gegenprobe():
    """Vor 3 Tagen bestätigt, gestern belegt gescheitert: Seite und Bilanz lesen die
    letzte gute Prüfung (im Fenster, bestätigt); die Seite nennt den gescheiterten
    Versuch als Hinweis."""
    gut = _probe(O2[0], "2026-11-18", gp.BESTAETIGT)
    versuch = _probe(O2[0], "2026-11-20", gp.NICHT_PRUEFBAR)
    proben = gf.Gegenproben([gut, versuch])
    preis = gb.gesamt_von(O2[0])
    assert proben.letzte_gute(O2[0]["id"], preis) is gut
    assert proben.letzter_versuch(O2[0]["id"], preis) is versuch
    o2 = gb.zusammenfassung(TAG, [O2[0]], proben, [])["anbieter"]["o2"]
    assert (o2["im_fenster"], o2[gp.BESTAETIGT], o2["ueberfaellig"]) == (1, 1, 0)
    karte = {"buendel_id": O2[0]["id"], "gesamt": preis, "abgerufen_am": TAG}
    beleg = pb.Preisbelege(Path("."), proben, lambda k: None).der_karte(karte)
    assert beleg["gegenprobe"]["status"] == gp.BESTAETIGT
    assert (
        "letzter Versuch 20.11.2026: nicht prüfbar (Auswahl nicht gefunden: 256 GB)"
        in beleg["gegenprobe"]["hinweise"]
    )


def test_fehlende_messung_im_lauf_bleibt_eine_luecke():
    laeufe = [
        {"datum": TAG, "anbieter": "o2", "besuche": 2, "sekunden": None, "buendel": 3}
    ]
    o2 = gb.zusammenfassung(TAG, O2, gf.Gegenproben(), laeufe)["anbieter"]["o2"]
    assert (o2["besuche"], o2["sekunden"], o2["sekunden_je_besuch"]) == (2, None, None)
    assert o2["buendel_je_besuch"] == 1.5


def test_fehlende_teildatei_ist_eine_benannte_luecke_nie_null(tmp_path):
    _bestand(tmp_path, O2 + EINS)
    quelle = tmp_path / "teile"
    _teil(quelle / "gegenprobe-teil-o2", "o2", [_proben()[0]], [LAEUFE[0]])
    argumente = ["--root", str(tmp_path), "--quelle", str(quelle)]
    assert ABLEGEN.main([*argumente, "--erwartet", '["o2", "1-1"]']) == 0
    bilanz = json.loads(gb.bilanzdatei(tmp_path, TAG).read_text(encoding="utf-8"))
    eins = bilanz["anbieter"]["1-1"]
    assert (eins["besuche"], eins["sekunden"], eins["sekunden_je_besuch"]) == (
        None,
        None,
        None,
    )
    assert eins["messung_fehlt"] == ABLEGEN.GRUND_TEIL_FEHLT
    assert eins["ausfall"] == [ABLEGEN.GRUND_TEIL_FEHLT]
    assert bilanz["anbieter"]["o2"]["besuche"] == 2
    assert bilanz["summe"]["besuche"] is None
    assert "1-1" in bilanz["summe"]["messung_fehlt"]


def test_anbieter_ohne_lauf_hat_keine_messung_statt_null():
    o2 = gb.zusammenfassung(TAG, O2, gf.Gegenproben(), [])["anbieter"]["o2"]
    assert (o2["besuche"], o2["messung_fehlt"]) == (None, gb.KEIN_LAUF)
