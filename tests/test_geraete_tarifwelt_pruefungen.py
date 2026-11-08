"""Tarifwelt-Leser: die Antwort muss zu sich selbst und zur Config passen, sonst
ist die Variante eine benannte Luecke und kein Preis (fail-closed), und jeder
Weiterleitungssprung geht durch dieselbe Abrufschleuse wie der erste Abruf.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from test_geraete_adapter_tarifwelt import LEITER, fixture_hole

from telco_radar.abdeckung_pflicht import pflichtmodelle_je_anbieter
from telco_radar.collect.geraete import laufuhr, tarifwelt_lauf
from telco_radar.collect.geraete.basis import GeraeteAbrufFehler
from telco_radar.geraete_abruf import hole_fuer_anbieter

JETZT = datetime(2026, 11, 8, 12, 0, tzinfo=UTC)


def _verfaelscht(aendere):
    hole, aufrufe = fixture_hole()

    def neu(url, **kw):
        status, text = hole(url, **kw)
        if "storage=" in url and "tfi=" in url:
            daten = json.loads(text)
            if daten.get("tariff", {}).get("_id"):
                aendere(daten)
            return status, json.dumps(daten)
        return status, text

    return neu, aufrufe


def _lies(aendere):
    hole, _ = _verfaelscht(aendere)
    return tarifwelt_lauf.lies_modell(
        "apple-iphone-17", LEITER, hole, "2026-11-08", warte=lambda s: None
    )


def _posten(daten, art="oneTimeCosts"):
    return daten["costs"][art]["items"]


def _grund(lauf) -> str:
    return " | ".join(g for _, g in lauf.luecken)


def test_unveraenderte_antworten_liefern_buendel():
    lauf = _lies(lambda d: None)
    assert len(lauf.buendel) == 2
    assert not any(w in _grund(lauf) for w in ("Versand", "Monat", "posten"))


def test_mehr_als_ein_geraeteposten_ist_eine_luecke_kein_erster_posten():
    def zusatz(d):
        _posten(d).append({"label": "Gratis Huelle", "amount": 0, "isDueNow": True})

    lauf = _lies(zusatz)
    assert lauf.buendel == []
    assert "2 Geraeteposten statt 1" in _grund(lauf)


def test_versandposten_gegen_die_config(caplog):
    def teurer(d):
        for p in _posten(d):
            if p["label"] == "Versandkosten":
                p["amount"] = 6.95

    with caplog.at_level(logging.WARNING):
        lauf = _lies(teurer)
    assert lauf.buendel == []
    assert "Versand 6.95 weicht von versandkosten.yaml (5.95) ab" in _grund(lauf)
    assert "weicht von versandkosten.yaml" in caplog.text


def test_fehlender_versandposten_ist_eine_abweichung_nicht_gratis():
    def ohne(d):
        d["costs"]["oneTimeCosts"]["items"] = [
            p for p in _posten(d) if p["label"] != "Versandkosten"
        ]

    lauf = _lies(ohne)
    assert lauf.buendel == []
    assert "Versand None weicht" in _grund(lauf)


def test_monatspreis_gegen_die_summe_der_monatsposten():
    def um(cent):
        def f(d):
            _posten(d, "monthlyCosts")[0]["amount"] += cent

        return f

    assert len(_lies(um(0.01)).buendel) == 2
    lauf = _lies(um(0.02))
    assert lauf.buendel == []
    assert "weicht von der Summe der Monatsposten" in _grund(lauf)


def test_fehlende_monatsposten_sind_eine_luecke():
    def leer(d):
        d["costs"]["monthlyCosts"]["items"] = []

    lauf = _lies(leer)
    assert lauf.buendel == []
    assert "monatliche Kostenposten fehlen" in _grund(lauf)


class _Roh:
    def __init__(self):
        self.aufrufe: list[tuple[str, dict]] = []

    def __call__(self, url, **kw):
        self.aufrufe.append((url, kw))
        if url.endswith("/robots.txt"):
            return 200, "User-agent: *\nDisallow: /checkout\n"
        return 200, "{}"


def test_einmal_abruf_bekommt_die_weiterleitungswache_der_schleuse():
    roh = _Roh()
    anbieter = SimpleNamespace(user_agent="", rate_limit_sekunden=0.0)
    hole = hole_fuer_anbieter(roh, anbieter, laufuhr(JETZT))
    hole("https://tarife-api2.mediamarkt.de/v1/x", einmalig=True)
    kw = roh.aufrufe[-1][1]
    wache = kw["vor_weiterleitung"]
    wache("https://tarife-api2.mediamarkt.de/v1/y")
    with pytest.raises(GeraeteAbrufFehler):
        wache("https://tarife-api2.mediamarkt.de/checkout")


def test_normaler_abruf_bekommt_keine_weiterleitungswache():
    roh = _Roh()
    anbieter = SimpleNamespace(user_agent="", rate_limit_sekunden=0.0)
    hole = hole_fuer_anbieter(roh, anbieter, laufuhr(JETZT))
    hole("https://tarife-api2.mediamarkt.de/v1/x")
    assert "vor_weiterleitung" not in roh.aufrufe[-1][1]


def test_haendlerzeile_in_pflicht_anbieter_ist_ein_konfigurationsfehler(tmp_path):
    pfad = tmp_path / "geraete_abdeckung.yaml"
    daten = {
        "pflicht_anbieter": ["Telekom", "Zeile A"],
        "pflicht_modelle": ["m-a"],
        "pflicht_anbieter_wenn_aktiv": {"Quelle X": ["Zeile A"]},
        "pflicht_modelle_wenn_aktiv": {"Quelle X": ["m-a"]},
    }
    with pytest.raises(ValueError, match="Zeile A"):
        pflichtmodelle_je_anbieter(daten, pfad)
