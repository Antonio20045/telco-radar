"""Gelesene Seiten eines gestörten Klick-Laufs kommen in den Gerätelauf (Pitch 1,
Schnitt 3).

Eine Telekom-Ergebnisdatei mit Laufstatus „gestoert“: die erste Seite ist gelesen
(MagentaMobil M, 36 Raten, Anzahlung 199 €, Rate 30,80 €), die zweite endet mit HTTP
202 und trägt selbst eine erfasste Kombination (Anzahlung 458,15 €), die dritte wurde
nicht besucht. Verwendet werden nur die Rohsätze der gelesenen Seite. Gegenprobe:
eine Datei nur mit der gestörten Seite liefert nichts. Der Erfassungsgrund bleibt für
den Anbieter, erscheint aber nur bei Modellen ohne Karte dieses Anbieters.
"""

from __future__ import annotations

from dataclasses import replace

import pytest
from bestand_pfad import lese_wurzel
from klickergebnisse import (
    TELEKOM_SEITE,
    erfasst,
    ergebnisdatei,
    lauf,
    telekom_lesung,
)

from telco_radar.analyze.klick_erfassung import erfassungsgruende, ohne_karte
from telco_radar.analyze.klick_zusammenfuehrung import fuehre_zusammen
from telco_radar.collect.geraete.klickergebnis import nicht_besucht
from telco_radar.collect.geraete.klicklauf import LAUF_GESTOERT
from telco_radar.geraete_config import lade_katalog
from telco_radar.report.geraete_tco_karten import geraet_aus_sku

HEUTE = "2026-10-08"
GESTOERT = {"status": LAUF_GESTOERT, "grund": "Abruf gestört (HTTP 202)"}
ZWEITE = replace(TELEKOM_SEITE, adresse=TELEKOM_SEITE.adresse + "&seite=2")
DRITTE = replace(TELEKOM_SEITE, adresse=TELEKOM_SEITE.adresse + "&seite=3")


@pytest.fixture(scope="module")
def katalog():
    return lade_katalog(lese_wurzel())


def _geraet(katalog):
    return lambda sku: geraet_aus_sku(sku, katalog)


def _gelesen():
    klick = erfasst(telekom_lesung("36", "199"), laufzeit=36)
    return (TELEKOM_SEITE, lauf(TELEKOM_SEITE, [klick]))


def _gestoert():
    klick = erfasst(telekom_lesung("36", "458,15"), laufzeit=36)
    return (ZWEITE, lauf(ZWEITE, [klick], **GESTOERT))


def _datei(*seiten, unbesucht=False):
    daten = ergebnisdatei("Telekom", "telekom", list(seiten), HEUTE)
    if unbesucht:
        daten["seiten"].append(nicht_besucht(DRITTE, "Zeitbudget erschöpft"))
    return daten


def _klick(saetze):
    return [s for s in saetze if s.get("quelle_art") == "klick"]


def test_gestoerter_lauf_liefert_die_gelesene_seite(katalog):
    datei = _datei(_gelesen(), _gestoert(), unbesucht=True)
    assert datei["laufstatus"] == LAUF_GESTOERT

    zug = fuehre_zusammen([], [datei], katalog, HEUTE, _geraet(katalog))

    (satz,) = _klick(zug.rohsaetze)
    assert (satz["anbieter"], satz["tarif_name"]) == ("Telekom", "MagentaMobil M")
    assert (satz["geraet_zuzahlung"], satz["geraet_monatsrate"]) == (199.0, 30.8)
    assert zug.bilanz["mehrdeutig"] == []
    (eintrag,) = zug.bilanz["dateien"]
    assert eintrag["verwendet"] is True
    assert eintrag["seiten_verwendet"] == 1
    assert "Abruf gestört (HTTP 202)" in eintrag["warum_nicht"]
    assert zug.erfassung["Telekom"].startswith("Telekom nicht erfasst")


def test_gestoerte_seite_allein_liefert_nichts(katalog):
    zug = fuehre_zusammen([], [_datei(_gestoert())], katalog, HEUTE, _geraet(katalog))

    assert _klick(zug.rohsaetze) == []
    (eintrag,) = zug.bilanz["dateien"]
    assert eintrag["verwendet"] is False
    assert eintrag["seiten_verwendet"] == 0
    assert "Telekom" in erfassungsgruende(zug.bilanz)


def test_grund_nur_ohne_karte_des_anbieters():
    gruende = {"Telekom": "Telekom nicht erfasst: …", "o2": "o2 nicht erfasst: …"}
    karten = [
        {"anbieter": "Telekom", "gesamt": 1500.0},
        {"anbieter": "o2", "gesamt": None, "leer_grund": "kein Bündel erhoben"},
    ]

    assert ohne_karte(gruende, karten) == {"o2": "o2 nicht erfasst: …"}
    assert ohne_karte(gruende, []) == gruende
