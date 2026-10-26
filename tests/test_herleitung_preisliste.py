"""Preisprüfung 26.10.2026: 1&1 bepreist jede Tarifstufe als Grundangebot plus festen
Tarifaufschlag. Ein so nachgerechneter Preis (A17, All-Net-Flat M, 22,99 €) steht beim
Anbieter und zählt in Band, Grafik und Rangfolge; eine echte Schätzung (o2 aus
Tarifsumme minus Geräterate) zählt weiter nicht. Vodafone nennt den Tarif mit Gerät
nur rabattiert; die Zeile heißt dann „Tarifanteil nach Rabatten“."""

from __future__ import annotations

from telco_radar.analyze.geraete_pruefstatus import buendel_zaehlt, ist_schaetzung
from telco_radar.report import geraete_notbremse as notbremse
from telco_radar.report import geraete_rechnung
from telco_radar.tco_kosten import (
    SCHRITT_GERAET,
    SCHRITT_TARIF,
    Rechenschritt,
    monatsschritte,
)

HEUTE = "2026-10-26"


def test_tarifaufschlag_von_1und1_zaehlt():
    assert not ist_schaetzung("tarifaufschlag_aus_tarifraster")
    assert buendel_zaehlt("tarifaufschlag_aus_tarifraster", [], HEUTE, None)
    assert buendel_zaehlt("schlusszahlung_aus_grundtarif", [], HEUTE, None)
    assert notbremse.herleitung_satz("1&1", "tarifaufschlag_aus_tarifraster") == ""


def test_schaetzung_von_o2_zaehlt_weiter_nicht():
    assert ist_schaetzung("tarifsumme_minus_geraeterate")
    assert not buendel_zaehlt("tarifsumme_minus_geraeterate", [], HEUTE, None)
    felder = notbremse.felder_aus_satz(
        {"herleitung": "tarifsumme_minus_geraeterate"}, HEUTE
    )
    assert felder["notbremse"]["kurz"] == notbremse.DELTA_SCHAETZUNG


def test_gemessen_zaehlt():
    assert not ist_schaetzung("")
    assert buendel_zaehlt("", [], HEUTE, None)


def _monat(rabattiert: bool) -> list[dict]:
    schritte = [
        Rechenschritt(SCHRITT_GERAET, 24, 8.25, 198.0),
        Rechenschritt(SCHRITT_TARIF, 24, 29.85, 716.4),
    ]
    return geraete_rechnung.zum_lesen(monatsschritte(schritte), rabattiert)


def test_rabattierter_tarif_heisst_tarifanteil_nach_rabatten():
    assert geraete_rechnung.tarif_rabattiert(29.85, 49.95)
    teile = [t["wort"] for t in _monat(True)[0]["teile"]]
    assert teile == ["Gerät", "Tarifanteil nach Rabatten"]


def test_tarif_zum_listenpreis_heisst_tarif():
    assert not geraete_rechnung.tarif_rabattiert(49.95, 49.95)
    assert not geraete_rechnung.tarif_rabattiert(29.85, None)
    teile = [t["wort"] for t in _monat(False)[0]["teile"]]
    assert teile == ["Gerät", "Tarif"]
