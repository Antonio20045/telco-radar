"""1&1: jeder Eintrag liest die Tarifdetail-Seiten selbst (Anschlusspreis, 21.11.2026).

Nachtlauf 21.11.2026: alle 308 1&1-Bündel des Tages standen ohne Anschlusspreis und
damit ohne Gesamtkosten (am 19.11.: 39,90 €). Die 308 Sätze kamen aus dem Eintrag
``1und1-2`` (15 Produktseiten gelesen). Den Anschlusspreis nennt nur die
Tarifdetail-Seite je Tarif. Die Tarifauswahl, die ``1und1-2`` liest, zeigt ihn nicht:
die Kachel nennt keine Einmalzahlung, die Preisübersicht braucht einen POST. Die
Produktseite nennt nur „erstatten wir Ihnen den Bereitstellungspreis“ ohne Betrag
(Abruf 21.11.2026). Die Tarifdetail-Seiten las aber nur ``1und1``, und der bekam HTTP
502. Mit #184 teilen sich die Einträge den Anschluss eines Tags; fällt der eine aus,
fehlt er trotzdem allen. Erwartet:

- jeder 1&1-Eintrag liest alle Tarifdetail-Seiten selbst;
- eine Datei, die nur Tarifdetail-Seiten als Übersicht trägt, sagt nichts über das
  Geräteangebot (``nicht_im_angebot`` bleibt ``None``, nicht „alle Geräte“);
- mit den echten Dateien der Nacht (``1und1`` mit 502) und den Tarifdetail-Seiten im
  Eintrag ``1und1-2`` trägt jeder Satz 39,90 €.

Gegenprobe: ohne gelesene Tarifdetail-Seite bleibt der Anschlusspreis ``None``
(``test_klick_1und1_anschluss_je_lauf``).
"""

from __future__ import annotations

import json
from urllib.parse import parse_qs, urlsplit

import pytest
from bestand_pfad import lese_wurzel
from klickergebnisse import WURZEL

from telco_radar.analyze.klick_erfassung import erfassungsgruende
from telco_radar.analyze.klick_zusammenfuehrung import fuehre_zusammen
from telco_radar.collect.geraete.klickrohsatz import ausbeute
from telco_radar.collect.geraete.klickziele import TAGESDATEI, lade_ziele
from telco_radar.geraete_config import lade_katalog
from telco_radar.report.geraete_tco_karten import geraet_aus_sku

HEUTE = "2026-11-21"
ORDNER = WURZEL / "tests" / "fixtures" / "klickcrawler"
TARIFDETAIL = "einsundeins_1und1_tarifdetail_20261121.json"
NACHT = "einsundeins_1und1_nacht_20261121.json"
ZWEITER = "einsundeins_1und1-2_nacht_20261121.json"


@pytest.fixture(scope="module")
def katalog():
    return lade_katalog(lese_wurzel())


def _lade(name: str) -> dict:
    return json.loads((ORDNER / name).read_text(encoding="utf-8"))


def _tarife(adressen) -> set[str]:
    return {
        parse_qs(urlsplit(a).query)["chosenTariff"][0]
        for a in adressen
        if "chosenTariff=" in a
    }


def test_jeder_1und1_eintrag_liest_alle_tarifdetail_seiten():
    ziele = [
        z
        for z in lade_ziele(lese_wurzel(), TAGESDATEI, hoechste=None)
        if z.name == "1&1" and z.schluessel in ("1und1", "1und1-2")
    ]
    gelesen = {u["adresse"] for u in _lade(TARIFDETAIL)["uebersichten"]}

    assert [z.schluessel for z in ziele] == ["1und1", "1und1-2"]
    assert len(_tarife(gelesen)) == 7
    assert {z.schluessel: _tarife(z.uebersichten) for z in ziele} == {
        "1und1": _tarife(gelesen),
        "1und1-2": _tarife(gelesen),
    }


def test_tarifdetail_seiten_sind_keine_geraeteliste(katalog):
    """Die echte Datei mit nur den sieben Tarifdetail-Seiten (alle gelesen und
    vollständig) nannte bisher jedes Katalog-Gerät „nicht im Angebot“."""
    daten = _lade(TARIFDETAIL)
    assert {(u["status"], u["vollstaendig"]) for u in daten["uebersichten"]} == {
        ("gelesen", True)
    }

    assert ausbeute(daten, katalog).nicht_im_angebot is None


def _zweiter_mit_tarifdetail() -> dict:
    zweiter = _lade(ZWEITER)
    return {**zweiter, "uebersichten": _lade(TARIFDETAIL)["uebersichten"]}


def test_nacht_mit_502_der_zweite_eintrag_bringt_den_anschluss_selbst(katalog):
    nacht = _lade(NACHT)
    assert (nacht["laufstatus"], nacht["datum"]) == ("gestoert", HEUTE)

    zug = fuehre_zusammen(
        [],
        [nacht, _zweiter_mit_tarifdetail()],
        katalog,
        HEUTE,
        lambda s: geraet_aus_sku(s, katalog),
    )
    saetze = [s for s in zug.rohsaetze if s["anbieter"] == "1&1"]

    assert len(saetze) == 28
    assert {s["anschlusspreis"] for s in saetze} == {39.9}


def test_kein_geraet_heisst_nicht_im_angebot(katalog):
    zug = fuehre_zusammen(
        [],
        [_lade(NACHT), _zweiter_mit_tarifdetail()],
        katalog,
        HEUTE,
        lambda s: geraet_aus_sku(s, katalog),
    )
    gruende = erfassungsgruende(zug.bilanz)

    assert not [s for s in gruende.values() if "nicht im Angebot" in s]
