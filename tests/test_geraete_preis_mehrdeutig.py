"""B2 (QA-Befund vom 04.09.2026): kein Pfeil fuer eine Preisaenderung, die
nie stattgefunden hat.

Der Fall: ALDI TALKs "Galaxy A17 LTE + Starter Kit" (129 EUR) und "Galaxy
A17 5G" (155/159 EUR) treffen beide den Katalogeintrag "Galaxy A17" und
teilen sich eine Listungs-ID. `GeraeteDB.upsert` verwirft den zweiten
Satz eines Laufs (mit genau dieser Begruendung im Kommentar) - die Pipeline
schrieb seine Historie trotzdem, und `geraete_preise.jsonl` trug je Tag zwei
Zeilen: 13 von 15 Pfeilen in G2 zeigten eine Bewegung, die es nie gab,
waehrend `gr-verlaufdaten` derselben Seite sieben Punkte konstant 129 EUR
behauptete.

Die Regel jetzt: zwei gleichzeitig gueltige Preise derselben Listung am
selben Tag sind eine MESSLUECKE - kein Punkt, kein Pfeil, kein Satz im
Fliesstext; die Luecke wird BENANNT. Beide Ansichten lesen sie aus derselben
Funktion (`geraete_verlauf.messtage`).

Bestandsdateien der gerenderten Pruefung: dieselbe Fixture wie
`test_geraete_tco_zustand._baue` (geraete_db.json, geraete_tco.json,
tarife.jsonl, geraete_preise.jsonl, drei Konfigdateien in tmp_path) - nur
die Preishistorie ist hier gestellt: o2 mit zwei Preisen je Tag, Vodafone
mit einer echten Aenderung. Die Gegenprobe im selben Test: ohne den zweiten
Preis je Tag traegt o2 seinen Pfeil.
"""
from __future__ import annotations

import json

from telco_radar.geraete_config import lade_katalog
from telco_radar.report import geraete_tco_grafik as grafik
from telco_radar.report import geraete_tco_karten as karten
from telco_radar.report import geraete_verlauf as verlauf

from test_geraete_tco_zustand import HEUTE, SKU_NEU, WURZEL, _baue, _listungen


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


def test_historienreihen_nehmen_mehrdeutige_tage_heraus_und_nennen_sie():
    hist = _Historie({"o2--x": [_p("2026-08-29", 129.0), _p("2026-08-29", 155.0),
                                _p("2026-08-30", 129.0), _p("2026-08-31", 129.0)]})
    eintrag = {"id": "o2--x", "sku_id": SKU_NEU, "device_id": "apple-iphone-15",
               "speicher_gb": 128, "anbieter": "o2", "zustand": "neu",
               "quelle_url": "https://example.de/x"}
    (reihe,) = karten.historienreihen([eintrag], hist, lade_katalog(WURZEL))
    assert [p["datum"] for p in reihe["punkte"]] == ["2026-08-30", "2026-08-31"]
    assert reihe["mehrdeutig"] == [{"datum": "2026-08-29",
                                    "betraege": [129.0, 155.0]}]


# --------------------------------------------------------------------------
# G2
# --------------------------------------------------------------------------

def _reihe(name, anbieter, punkte, mehrdeutig=None):
    return {"name": name, "anbieter": anbieter,
            "quelle_url": f"https://example.de/{anbieter}",
            "punkte": [{"datum": d, "betrag": b} for d, b in punkte],
            "mehrdeutig": mehrdeutig or []}


def test_ein_tag_mit_zwei_preisen_bekommt_keinen_pfeil():
    """Die Gegenprobe steht im selben Test: OHNE den zweiten Preis traegt
    derselbe Tag seinen Pfeil - der Pfeil faellt also an der Mehrdeutigkeit,
    nicht an der Fixture."""
    mit = grafik.historie([_reihe("A", "o2", [("2026-08-29", 500.0),
                                              ("2026-08-30", 500.0),
                                              ("2026-08-30", 520.0),
                                              ("2026-08-31", 500.0)])])
    assert mit["reihen"] == 1
    assert mit["ereignisse"] == []
    assert "gr-g2-marker" not in mit["svg"]
    assert mit["tabelle"][0]["mehrdeutig"] == [{"datum": "2026-08-30",
                                                 "betraege": [500.0, 520.0]}]
    assert [p["datum"] for p in mit["tabelle"][0]["punkte"]] == [
        "2026-08-29", "2026-08-31"]

    ohne = grafik.historie([_reihe("A", "o2", [("2026-08-29", 500.0),
                                               ("2026-08-30", 520.0),
                                               ("2026-08-31", 500.0)])])
    assert len(ohne["ereignisse"]) == 2
    assert ohne["svg"].count("gr-g2-marker") == 2


def test_eine_reihe_aus_lauter_mehrdeutigen_tagen_wird_benannt_statt_gezeichnet():
    ergebnis = grafik.historie([
        _reihe("Galaxy A17 128 GB", "ALDI TALK", [
            ("2026-08-29", 129.0), ("2026-08-29", 155.0),
            ("2026-08-30", 129.0), ("2026-08-30", 159.0)]),
        _reihe("B", "o2", [("2026-08-29", 223.0), ("2026-09-02", 271.0)]),
    ])
    assert ergebnis["reihen"] == 1 and ergebnis["reihen_gesamt"] == 1
    assert [t["name"] for t in ergebnis["tabelle"]] == ["B"]
    # Genau EIN Pfeil - der echte von o2, keiner von ALDI TALK.
    assert ergebnis["svg"].count("gr-g2-marker") == 1
    assert [e["anbieter"] for e in ergebnis["ereignisse"]] == ["o2"]
    assert ergebnis["ausgelassen"] == [{
        "name": "Galaxy A17 128 GB", "anbieter": "ALDI TALK",
        "quelle_url": "https://example.de/ALDI TALK",
        "tage": ["2026-08-29", "2026-08-30"],
        "betraege": {"2026-08-29": [129.0, 155.0],
                     "2026-08-30": [129.0, 159.0]}}]


def test_die_mehrdeutigkeit_aus_der_reihe_zaehlt_wie_die_aus_den_punkten():
    """`historienreihen` liefert die Tage schon herausgenommen und in
    `mehrdeutig` - die Grafik muss sie von dort genauso lesen wie aus
    doppelten Punkten."""
    ergebnis = grafik.historie([_reihe("A", "o2", [("2026-08-29", 500.0),
                                                   ("2026-08-31", 500.0)],
                                       mehrdeutig=[{"datum": "2026-08-30",
                                                    "betraege": [500.0, 520.0]}])])
    assert ergebnis["tabelle"][0]["mehrdeutig"][0]["datum"] == "2026-08-30"
    assert ergebnis["ereignisse"] == []


def test_die_bildunterschrift_kennt_die_grundmenge():
    """S8: sieben Reihen mit zwei Punkten, fuenf gezeichnet - und das steht
    dran, statt "5 Reihen" zu behaupten."""
    reihen = [_reihe(f"R{i}", "o2", [("2026-08-29", 100.0 + i),
                                     ("2026-08-30", 100.0 + i)])
              for i in range(7)]
    ergebnis = grafik.historie(reihen)
    assert ergebnis["reihen"] == grafik.MAX_REIHEN == 5
    assert ergebnis["reihen_gesamt"] == 7


# --------------------------------------------------------------------------
# Die gerenderte Seite: beide Ansichten aus einer Quelle
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
    s = _baue(tmp_path, erneuert=False, punkte=_historie_gestellt(True))
    tafel = s.select_one("#tafel-verlauf")

    # G2: zwei Pfeile - beide von Vodafone (709,90 -> 689,90 -> 709,90).
    svg = tafel.select_one("svg.gr-g2")
    marker = svg.select(".gr-g2-marker")
    assert len(marker) == 2
    text = " ".join(tafel.get_text(" ", strip=True).split())
    assert "bei o2 +" not in text and "bei o2 −" not in text, \
        "kein Satz ueber eine o2-Aenderung, die es nie gab"
    # Die ausgelassene Reihe steht mit Grund und beiden Betraegen da.
    hinweis = tafel.select_one(".gr-g2-ausgelassen")
    assert hinweis is not None
    hinweis_text = " ".join(hinweis.get_text(" ", strip=True).split())
    assert "iPhone 15 128 GB bei o2 (3 Messtage, zuletzt 4. September 2026: " \
           "700,00 € und 720,00 €)" in hinweis_text
    assert "eine Messlücke, keine Preisbewegung" in hinweis_text

    # `gr-verlaufdaten` liest DIESELBE Regel: kein o2-Punkt, die Luecke
    # benannt.
    daten = json.loads(s.select_one("#gr-verlaufdaten").get_text())
    (geraet,) = [g for g in daten if g["id"] == "apple-iphone-15-128"]
    assert [r["anbieter"] for r in geraet["reihen"]] == ["Vodafone"]
    assert geraet["mehrdeutig"] == [{
        "anbieter": "o2", "listung_id": "o2--" + SKU_NEU,
        "tage": ["2026-09-02", "2026-09-03", "2026-09-04"],
        "betraege": {"2026-09-02": [700.0, 720.0], "2026-09-03": [700.0, 720.0],
                     "2026-09-04": [700.0, 720.0]}}]

    # Gegenprobe: ohne den zweiten Preis je Tag ist o2 eine normale Reihe
    # ohne Pfeil (700 -> 700 -> 700) und ohne Hinweis.
    s2 = _baue(tmp_path / "gegen", erneuert=False,
               punkte=_historie_gestellt(False))
    tafel2 = s2.select_one("#tafel-verlauf")
    assert tafel2.select_one(".gr-g2-ausgelassen") is None
    assert len(tafel2.select_one("svg.gr-g2").select(".gr-g2-marker")) == 2
    daten2 = json.loads(s2.select_one("#gr-verlaufdaten").get_text())
    (geraet2,) = [g for g in daten2 if g["id"] == "apple-iphone-15-128"]
    assert sorted(r["anbieter"] for r in geraet2["reihen"]) == ["Vodafone", "o2"]
    assert geraet2["mehrdeutig"] == []
