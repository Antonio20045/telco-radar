"""B2 (QA-Befund vom 04.09.2026): kein Pfeil fuer eine Preisaenderung, die
nie stattgefunden hat.

Der Fall: ALDI TALKs "Galaxy A17 LTE + Starter Kit" (129 EUR) und "Galaxy
A17 5G" (155/159 EUR) treffen beide den Katalogeintrag "Galaxy A17" und
teilen sich eine Listungs-ID. `GeraeteDB.upsert` verwirft den zweiten
Satz eines Laufs (mit genau dieser Begruendung im Kommentar) - die Pipeline
schrieb seine Historie trotzdem, und `geraete_preise.jsonl` trug je Tag zwei
Zeilen: 13 von 15 Pfeilen der (mit P2 gefallenen) G2 zeigten eine Bewegung,
die es nie gab, waehrend `gr-verlaufdaten` derselben Seite sieben Punkte
konstant 129 EUR behauptete.

Die Regel: zwei gleichzeitig gueltige Preise derselben Listung am selben
Tag sind eine MESSLUECKE - kein Punkt, kein Pfeil, kein Satz im
Fliesstext; die Luecke wird BENANNT. Der Wähler des Verlaufs-Reiters liest
sie aus `geraete_verlauf.messtage` (P2: der einzige Leser - die G2-Tests
sind mit dem Block gefallen, die Regel nicht).

Bestandsdateien der gerenderten Pruefung: dieselbe Fixture wie
`test_geraete_tco_zustand._baue` (geraete_db.json, geraete_tco.json,
tarife.jsonl, geraete_preise.jsonl, drei Konfigdateien in tmp_path) - nur
die Preishistorie ist hier gestellt: o2 mit zwei Preisen je Tag, Vodafone
mit einer echten Aenderung. Die Gegenprobe im selben Test: ohne den zweiten
Preis je Tag traegt o2 normale Punkte.
"""
from __future__ import annotations

import json

from telco_radar.report import geraete_verlauf as verlauf

from test_geraete_tco_zustand import SKU_NEU, _baue, _listungen


class _Historie:
    def __init__(self, reihen):
        self._reihen = reihen

    def reihe(self, lid):
        return sorted(self._reihen.get(lid, []), key=lambda s: s["datum"])


def _p(datum, betrag):
    return {"datum": datum, "preis_ohne_vertrag": betrag}


# --------------------------------------------------------------------------
# Die eine Regel
# --------------------------------------------------------------------------

def test_messtage_trennt_eindeutige_und_mehrdeutige_tage():
    eindeutig, mehrdeutig = verlauf.messtage([
        _p("2026-08-29", 129.0), _p("2026-08-29", 155.0),
        _p("2026-08-30", 129.0), _p("2026-08-30", 129.0),   # derselbe Preis zweimal
        _p("2026-08-31", 159.0), _p("2026-09-01", None)])
    assert eindeutig == {"2026-08-30": 129.0, "2026-08-31": 159.0}
    assert mehrdeutig == {"2026-08-29": [129.0, 155.0]}


# --------------------------------------------------------------------------
# Die gerenderte Seite: der Wähler aus derselben Quelle
# --------------------------------------------------------------------------

def _historie_gestellt(o2_doppelt: bool) -> list:
    listungen = {e["anbieter"] + e["sku_id"]: e for e in _listungen()}
    o2 = listungen["o2" + SKU_NEU]
    vf = listungen["Vodafone" + SKU_NEU]
    zeilen = []
    for tag, preis in (("2026-09-02", 700.0), ("2026-09-03", 700.0),
                       ("2026-09-04", 700.0)):
        zeilen.append({"listung_id": o2["id"], "device_id": o2["device_id"],
                       "anbieter": "o2", "datum": tag, "preis_ohne_vertrag": preis,
                       "quelle_url": o2["quelle_url"]})
        if o2_doppelt:
            zeilen.append(dict(zeilen[-1], preis_ohne_vertrag=720.0))
    for tag, preis in (("2026-09-02", 709.90), ("2026-09-03", 689.90),
                       ("2026-09-04", 709.90)):
        zeilen.append({"listung_id": vf["id"], "device_id": vf["device_id"],
                       "anbieter": "Vodafone", "datum": tag,
                       "preis_ohne_vertrag": preis, "quelle_url": vf["quelle_url"]})
    return zeilen


def test_die_seite_benennt_die_messluecke_statt_sie_zu_zeichnen(tmp_path):
    """Bis P2 prüfte dieser Test beide Ansichten des Reiters; die G2-Teile
    sind mit dem Block gefallen. Der Wähler liest DIESELBE Regel aus
    `#gr-verlaufdaten`: kein o2-Punkt, die Lücke benannt."""
    s = _baue(tmp_path, erneuert=False, punkte=_historie_gestellt(True))
    daten = json.loads(s.select_one("#gr-verlaufdaten").get_text())
    (geraet,) = [g for g in daten if g["id"] == "apple-iphone-15-128"]
    assert [r["anbieter"] for r in geraet["reihen"]] == ["Vodafone"]
    assert geraet["mehrdeutig"] == [{
        "anbieter": "o2", "listung_id": "o2--" + SKU_NEU,
        "tage": ["2026-09-02", "2026-09-03", "2026-09-04"],
        "betraege": {"2026-09-02": [700.0, 720.0], "2026-09-03": [700.0, 720.0],
                     "2026-09-04": [700.0, 720.0]}}]

    # Gegenprobe: ohne den zweiten Preis je Tag ist o2 eine normale Reihe.
    s2 = _baue(tmp_path / "gegen", erneuert=False,
               punkte=_historie_gestellt(False))
    daten2 = json.loads(s2.select_one("#gr-verlaufdaten").get_text())
    (geraet2,) = [g for g in daten2 if g["id"] == "apple-iphone-15-128"]
    assert sorted(r["anbieter"] for r in geraet2["reihen"]) == ["Vodafone", "o2"]
    assert geraet2["mehrdeutig"] == []
