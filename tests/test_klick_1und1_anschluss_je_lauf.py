"""1&1: der Anschlusspreis gilt für beide Einträge eines Tags (``1und1``, ``1und1-2``).

Nachtlauf 21.11.2026: alle 308 1&1-Sätze standen ohne ``anschlusspreis``, also ohne
Gesamtkosten (vorher 39,90 €). Ursache 1: die Tarifdetail-Seiten liest nur der Eintrag
``1und1``, der Anschluss kam aber nur aus der eigenen Ergebnisdatei; die Sätze von
``1und1-2`` fanden darum nie einen. Ursache 2: in dieser Nacht las auch ``1und1`` keine
Tarifdetail-Seite (HTTP 502, ``test_klick_serverfehler``).

Daten: ``einsundeins_1und1-2_nacht_20261121.json`` (Nachtlauf, Seite Pixel 10a, 28
erfasst), ``einsundeins_1und1_tarifdetail_20261121.json`` (lokaler Lauf desselben Tags,
sieben Tarifdetail-Seiten je 39,90 €), ``einsundeins_1und1_nacht_20261121.json``
(Nachtlauf mit 502). Erwartet: jeder Satz von ``1und1-2`` trägt den Anschlusspreis
seines Tarifs aus der Datei von ``1und1`` und hat Gesamtkosten; Gegenproben: ohne
gelesene Tarifdetail-Seite und mit einer Datei eines anderen Tags bleibt er ``None``.
"""

from __future__ import annotations

import json
from collections import Counter

import pytest
from bestand_pfad import ZUSTAND, lese_wurzel
from klickergebnisse import WURZEL

from telco_radar.analyze.klick_zusammenfuehrung import fuehre_zusammen
from telco_radar.analyze.tco_buendel import aus_rohsaetzen
from telco_radar.geraete_config import lade_katalog
from telco_radar.report.geraete_tco_karten import geraet_aus_sku
from telco_radar.tarif_bezug import Tarifbestand
from telco_radar.tco_kosten import kosten_ueber

HEUTE = "2026-11-21"
ORDNER = WURZEL / "tests" / "fixtures" / "klickcrawler"
TARIFE = (
    "1&1 All-Net-Flat S",
    "1&1 All-Net-Flat M",
    "1&1 All-Net-Flat L",
    "1&1 Unlimited on demand S",
    "1&1 Unlimited on demand M",
    "1&1 Unlimited on demand L",
    "1&1 Unlimited XL",
)


@pytest.fixture(scope="module")
def katalog():
    return lade_katalog(lese_wurzel())


def _lade(name: str) -> dict:
    return json.loads((ORDNER / name).read_text(encoding="utf-8"))


def _saetze(katalog, *dateien: dict) -> list[dict]:
    zug = fuehre_zusammen(
        [], list(dateien), katalog, HEUTE, lambda s: geraet_aus_sku(s, katalog)
    )
    return [s for s in zug.rohsaetze if s["anbieter"] == "1&1"]


def test_saetze_des_zweiten_eintrags_tragen_den_anschluss_des_ersten(katalog):
    tarifdetail = _lade("einsundeins_1und1_tarifdetail_20261121.json")
    nacht = _lade("einsundeins_1und1-2_nacht_20261121.json")
    assert (tarifdetail["anbieter"], nacht["anbieter"]) == ("1und1", "1und1-2")
    assert tarifdetail["datum"] == nacht["datum"] == HEUTE

    saetze = _saetze(katalog, tarifdetail, nacht)

    assert len(saetze) == 28
    assert Counter(s["tarif_name"] for s in saetze) == {t: 4 for t in TARIFE}
    assert {s["anschlusspreis"] for s in saetze} == {39.9}


def test_unlimited_xl_findet_den_anschluss_ueber_den_namen(katalog):
    """Die Kachel nennt ``…-xl-mvl``, die Detailseite ``…-xl-ovl``."""
    saetze = _saetze(
        katalog,
        _lade("einsundeins_1und1_tarifdetail_20261121.json"),
        _lade("einsundeins_1und1-2_nacht_20261121.json"),
    )

    xl = [s for s in saetze if s["tarif_name"] == "1&1 Unlimited XL"]
    assert len(xl) == 4 and {s["anschlusspreis"] for s in xl} == {39.9}


def test_gesamtkosten_von_hand(katalog):
    """Pixel 10a 128 GB, All-Net-Flat S, 36 Monate Fix: 36 × 27,99 € + 0,00 € + 39,90 €
    = 1.047,54 € (Bündelbetrag der Nacht, Anschluss der Tarifdetail-Seite)."""
    saetze = _saetze(
        katalog,
        _lade("einsundeins_1und1_tarifdetail_20261121.json"),
        _lade("einsundeins_1und1-2_nacht_20261121.json"),
    )
    bestand = Tarifbestand.aus_datei(ZUSTAND / "tarife.jsonl")
    buendel = aus_rohsaetzen(saetze, bestand, HEUTE).buendel
    (satz,) = [
        b
        for b in buendel
        if b.tarif_name == TARIFE[0]
        and b.laufzeit_monate == 36
        and b.sku_id.startswith("google-pixel-10a-128gb")
    ]
    kosten = kosten_ueber(satz)

    assert satz.buendel_monatlich == 27.99
    assert kosten.luecken == []
    assert kosten.gesamt == pytest.approx(36 * 27.99 + 0.0 + 39.9)


def test_gegenprobe_ohne_gelesene_tarifdetail_seite_kein_anschluss(katalog):
    """Die Nacht selbst: ``1und1`` bekam HTTP 502, nichts wird erfunden."""
    saetze = _saetze(
        katalog,
        _lade("einsundeins_1und1_nacht_20261121.json"),
        _lade("einsundeins_1und1-2_nacht_20261121.json"),
    )

    assert len(saetze) == 28
    assert {s["anschlusspreis"] for s in saetze} == {None}


def test_gegenprobe_anschluss_eines_anderen_tags_zaehlt_nicht(katalog):
    gestern = {**_lade("einsundeins_1und1_tarifdetail_20261121.json")}
    gestern["datum"] = "2026-11-20"

    saetze = _saetze(katalog, gestern, _lade("einsundeins_1und1-2_nacht_20261121.json"))

    assert {s["anschlusspreis"] for s in saetze} == {None}
