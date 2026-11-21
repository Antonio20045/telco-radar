"""1&1 ohne jede Kachel: die Seitenliste schrumpft nicht und neue Modelle kommen dazu.

BEFUND 21.11.2026 (Klick-Lauf 44840854026, ``data/state/klick/1und1*.json``): die
Geräteübersicht ``/smartphones`` war noch nie ganz gelesen (am 21.11. nach einem HTTP
502 der ersten Tarifdetail-Seite „nicht besucht“), es gab also keine Kachel und keinen
Vorrat. Der Rückfall „Seiten des Laufs“ las dann nur die Datei ``1und1.json``: aus 42
Seiten des 20.11. (beide Einträge) wurden 21 für den 22.11., die nächste Nacht wieder
die Hälfte. Und weil der Rückfall Seiten lieferte, leitete ``klickliste_auto`` für 1&1
nichts mehr ab: das iPhone Duo, das 1&1 führt (Kachel „iPhone Duo“ auf
``/smartphones`` und Produktseite ``/iphone-duo``, Browser 21.11.2026, ab 62,99 €/Monat
mit All-Net-Flat S), stand in keiner Seitenliste mehr; der Abdeckungswächter meldete
es als fehlendes Pflichtmodell.

Jetzt sammelt der Rückfall die Seiten aller Einträge derselben Quelle, und ein Anbieter
mit Seiten nur aus dem Rückfall bekommt seine fehlenden Modelle von ``klickliste_auto``.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from bestand_pfad import AUTO_KATALOG, ZUSTAND, lese_wurzel, verlinke_neben_data

from telco_radar.collect.geraete.klickliste_kacheln import (
    lies_kachelseiten,
    seiten_aus_kacheln,
)
from telco_radar.collect.geraete.klickziele import TAGESDATEI, lade_ziele
from telco_radar.geraete_config import lade_katalog

TAG = "2026-11-21"
UEBERSICHT = "https://mobile.1und1.de/smartphones"
_NICHT_BESUCHT = {"adresse": UEBERSICHT, "status": "nicht_besucht", "saetze": []}


def _datei(schluessel: str, geraete: list[str]) -> dict:
    return {
        "anbieter": schluessel,
        "name": "1&1",
        "datum": TAG,
        "format": 1,
        "laufstatus": "gelesen",
        "uebersichten": [dict(_NICHT_BESUCHT)] if schluessel == "1und1" else [],
        "seiten": [
            {
                "adresse": f"https://mobile.1und1.de/{g.removeprefix('apple-')}",
                "geraet": g,
            }
            for g in geraete
        ],
    }


ERSTE = ["apple-iphone-17", "apple-iphone-17-pro"]
ZWEITE = ["apple-iphone-17e", "apple-iphone-17"]


def _root(tmp_path: Path, mit_duo: bool = True) -> Path:
    root = tmp_path / "r"
    klick = root / "data" / "state" / "klick"
    klick.mkdir(parents=True)
    shutil.copy2(ZUSTAND / AUTO_KATALOG, root / "data" / "state" / AUTO_KATALOG)
    verlinke_neben_data(root)
    for schluessel, geraete in (("1und1", ERSTE), ("1und1-2", ZWEITE)):
        daten = _datei(schluessel, geraete)
        (klick / f"{schluessel}.json").write_text(json.dumps(daten), "utf-8")
    buendel = []
    if mit_duo:
        buendel.append(
            {
                "id": "buendel--1-1--apple-iphone-duo-256gb-sternenweiss--x--36m",
                "sku_id": "apple-iphone-duo-256gb-sternenweiss",
                "anbieter": "1&1",
                "tarif_name": "1&1 All-Net-Flat S",
                "laufzeit_monate": 36,
                "zustand": "neu",
                "quelle_url": "https://mobile.1und1.de/iphone-duo",
                "abgerufen_am": "2026-11-19",
            }
        )
    tco = {"buendel": buendel}
    (root / "data" / "state" / "geraete_tco.json").write_text(json.dumps(tco), "utf-8")
    return root


def test_rueckfall_nimmt_die_seiten_beider_eintraege():
    katalog = lade_katalog(lese_wurzel())
    erste, zweite = _datei("1und1", ERSTE), _datei("1und1-2", ZWEITE)

    ergebnis = seiten_aus_kacheln(erste, katalog, weitere=[zweite])

    geraete = sorted(s["geraet"] for s in ergebnis.seiten)
    assert geraete == ["apple-iphone-17", "apple-iphone-17-pro", "apple-iphone-17e"]
    assert ergebnis.rueckfall is True
    assert ergebnis.luecken[-1] == "keine Kachel, 3 Seiten des Laufs vom 21.11.2026"


def test_gegenprobe_ohne_weitere_datei_nur_die_eigenen_seiten():
    katalog = lade_katalog(lese_wurzel())
    ergebnis = seiten_aus_kacheln(_datei("1und1", ERSTE), katalog)

    assert sorted(s["geraet"] for s in ergebnis.seiten) == sorted(ERSTE)


def test_lies_kachelseiten_liest_die_geschwisterdateien(tmp_path):
    root = _root(tmp_path)
    katalog = lade_katalog(root)

    ergebnis = lies_kachelseiten(root, "1und1", katalog, geschwister=["1und1-2"])

    assert len(ergebnis.seiten) == 3


def test_tagesplan_ohne_kachel_hat_alle_seiten_und_das_duo(tmp_path):
    ziele = [
        z
        for z in lade_ziele(_root(tmp_path), TAGESDATEI, hoechste=None, auto=True)
        if z.name == "1&1"
    ]

    seiten = {s.geraet for z in ziele for s in z.seiten}
    assert {"apple-iphone-17", "apple-iphone-17-pro", "apple-iphone-17e"} <= seiten
    (auto,) = [z for z in ziele if z.schluessel == "1und1-auto"]
    assert [(s.geraet, s.adresse) for s in auto.seiten] == [
        ("apple-iphone-duo", "https://mobile.1und1.de/iphone-duo")
    ]


def test_gegenprobe_mit_echten_kacheln_leitet_auto_nichts_ab(tmp_path):
    root = _root(tmp_path)
    pfad = root / "data" / "state" / "klick" / "1und1.json"
    daten = json.loads(pfad.read_text("utf-8"))
    daten["uebersichten"] = [
        {
            "adresse": UEBERSICHT,
            "status": "gelesen",
            "saetze": [
                {
                    "art": "liste",
                    "titel": "iPhone 17",
                    "url": "https://mobile.1und1.de/iphone-17",
                }
            ],
        }
    ]
    pfad.write_text(json.dumps(daten), "utf-8")

    ziele = lade_ziele(root, TAGESDATEI, hoechste=None, auto=True)

    assert not [z for z in ziele if z.schluessel == "1und1-auto"]
