"""congstar: Tarifpreis bis zur letzten Rate, wenn der Tarif keine Rabattphase hat.

Die Klick-Karte congstar liest ``prices.recurring.discounts`` des Tarifs als Nachweis
``ratenplan`` (JSON). Leer heißt: keine Rabattphase, der Tarifpreis gilt über alle Raten
(dieselbe Regel wie ``ratenlaufzeit.congstar_phasen``). Fixtures:
``congstar_tarifpreise_20261007.json.gz`` (Auszug der GraphQL-Antwort der
Klick-Erkundung vom 07.10.2026, alle acht Tarife ohne Rabatt) und
``klick_ergebnisse_20261010.json.gz``; Herkunft in ``_herkunft.json``.
"""

from __future__ import annotations

import copy
import gzip
import json
from pathlib import Path

import pytest
from bestand_pfad import lese_wurzel

from telco_radar.collect.geraete.klickantwort import lies_antwort
from telco_radar.collect.geraete.klickkarte import lade_klickkarte
from telco_radar.collect.geraete.klickratenplan import NACHWEIS, ratenplan_phasen
from telco_radar.collect.geraete.klickrohsatz import ausbeute
from telco_radar.geraete_config import lade_katalog

WURZEL = Path(__file__).resolve().parents[1]
FIX = WURZEL / "tests" / "fixtures" / "geraete"
TARIFE = {"543": 15.0, "544": 15.0, "560": 20.0, "559": 20.0, "540": 25.0}
RABATT = [{"iterations": 12, "iterationType": "LIMITED", "amount": 5.0}]


def _gz(name: str):
    with gzip.open(FIX / name, "rt", encoding="utf-8") as fh:
        return json.load(fh)


@pytest.fixture(scope="module")
def quelle():
    return lade_klickkarte(WURZEL / "config" / "klickkarten" / "congstar.yaml").antwort


@pytest.fixture(scope="module")
def antwort():
    return _gz("congstar_tarifpreise_20261007.json.gz")


def _mit_nachweis(daten: dict, nachweis: str) -> dict:
    neu = copy.deepcopy(daten)
    for seite in neu["seiten"]:
        for kombination in seite.get("kombinationen") or []:
            kombination["nachweise"] = {NACHWEIS: nachweis}
    return neu


@pytest.mark.parametrize(("plan", "preis"), sorted(TARIFE.items()))
def test_karte_liest_die_leeren_rabatte_als_nachweis(quelle, antwort, plan, preis):
    lesung = lies_antwort(antwort, quelle, None, {"plan": plan})

    assert lesung.nachweise == {NACHWEIS: "[]"}
    (phase,) = lesung.werte.tarifphasen
    assert (phase.von_monat, phase.bis_monat, phase.betrag) == (1, None, preis)


def test_gegenprobe_rabatt_und_fremder_plan(quelle, antwort):
    """Derselbe Auszug, im Test mit einem Rabatt auf Tarif 543: kein leerer Nachweis."""
    mit_rabatt = copy.deepcopy(antwort)
    for plan in mit_rabatt["data"]["plans"]:
        for variante in plan["variants"]:
            if variante["id"] == 543:
                variante["prices"]["recurring"]["discounts"] = RABATT

    lesung = lies_antwort(mit_rabatt, quelle, None, {"plan": "543"})
    fremd = lies_antwort(antwort, quelle, None, {"plan": "999"})

    assert json.loads(lesung.nachweise[NACHWEIS]) == RABATT
    assert ratenplan_phasen("congstar", {"nachweise": lesung.nachweise}, 36, 15.0) == []
    assert fremd.nachweise == {}


def test_ohne_rabattphase_gilt_der_preis_bis_zur_letzten_rate():
    (phase,) = ratenplan_phasen("congstar", {"nachweise": {NACHWEIS: "[]"}}, 36, 25.0)

    assert (phase["von_monat"], phase["bis_monat"], phase["betrag"]) == (1, 36, 25.0)
    assert "discounts []" in phase["beleg"]
    assert ratenplan_phasen("o2", {"nachweise": {NACHWEIS: "[]"}}, 36, 25.0) == []
    assert (
        ratenplan_phasen("congstar", {"nachweise": {NACHWEIS: "[]"}}, None, 25.0) == []
    )


def test_congstar_saetze_bekommen_die_phase_sonst_nichts():
    katalog = lade_katalog(lese_wurzel())
    daten = _gz("klick_ergebnisse_20261010.json.gz")["congstar"]
    vorher = ausbeute(daten, katalog)
    nachher = ausbeute(_mit_nachweis(daten, "[]"), katalog)
    mit_rabatt = ausbeute(_mit_nachweis(daten, json.dumps(RABATT)), katalog)

    assert nachher.luecken == vorher.luecken
    assert mit_rabatt.rohsaetze == vorher.rohsaetze
    assert len(nachher.rohsaetze) == len(vorher.rohsaetze) > 0
    for alt, satz in zip(vorher.rohsaetze, nachher.rohsaetze, strict=True):
        assert {**satz, "tarif_phasen": alt["tarif_phasen"]} == alt
        if alt["tarif_phasen"]:
            assert satz["tarif_phasen"] == alt["tarif_phasen"]
            continue
        (phase,) = satz["tarif_phasen"]
        assert (phase["von_monat"], phase["bis_monat"]) == (1, satz["laufzeit_monate"])
        assert phase["betrag"] == satz["tarif_monatlich"]
