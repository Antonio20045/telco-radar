"""Ruhiges Tempo im Klick-Tageslauf: fester Abstand zwischen zwei Seiten.

``seitenabstand_sekunden`` aus ``config/klick_tageslauf.yaml`` (Telekom 60 s) wartet
der Tageslauf zwischen zwei besuchten Seiten ab, nie vor der ersten und nie für eine
Seite, die er nicht mehr besucht. Uhr und Schlaf sind Attrappen; kein Browser, kein
Netz. Jede Seite trägt in der Ergebnisdatei ``http_status`` und ``sperre``.
"""

from __future__ import annotations

import pytest
from bestand_pfad import lese_wurzel
from klickergebnisse import WURZEL

from telco_radar.collect.geraete.klickkarte import lade_klickkarte
from telco_radar.collect.geraete.klicklauf import (
    LAUF_GELESEN,
    LAUF_GESTOERT,
    Klicklauf,
    abruf_gestoert,
)
from telco_radar.collect.geraete.klicktageslauf import fahre
from telco_radar.collect.geraete.klickziele import TAGESDATEI, lade_ziele

HEUTE = "2026-10-08"
MINUTE = 60.0
SEITE_S = 300.0


@pytest.fixture(scope="module")
def telekom():
    alle = lade_ziele(lese_wurzel(), TAGESDATEI, hoechste=None)
    return {z.schluessel: z for z in alle}["telekom"]


@pytest.fixture(scope="module")
def karte():
    return lade_klickkarte(WURZEL / "config" / "klickkarten" / "telekom.yaml")


class Uhr:
    def __init__(self) -> None:
        self.jetzt = 0.0
        self.schlaf: list[float] = []

    def __call__(self) -> float:
        return self.jetzt

    def schlafe(self, sekunden: float) -> None:
        self.schlaf.append(sekunden)
        self.jetzt += sekunden


def _crawler(uhr: Uhr, gestoert_ab: int | None = None, sperre: str | None = None):
    aufrufe: list[float] = []

    def crawle(seite, ende):
        aufrufe.append(uhr.jetzt)
        uhr.jetzt += SEITE_S
        if gestoert_ab is not None and len(aufrufe) > gestoert_ab:
            lauf = Klicklauf(
                "Telekom", seite.adresse, LAUF_GESTOERT, abruf_gestoert(202)
            )
            lauf.http_status, lauf.sperre = 202, sperre
            return lauf
        lauf = Klicklauf("Telekom", seite.adresse, LAUF_GELESEN, http_status=200)
        lauf.sperre = "challenge_bestanden"
        return lauf

    return crawle, aufrufe


def test_telekom_hat_eine_minute_seitenabstand(telekom):
    assert telekom.seitenabstand_sekunden == MINUTE


def test_tageslauf_wartet_zwischen_den_seiten_den_seitenabstand(telekom, karte):
    uhr = Uhr()
    crawle, aufrufe = _crawler(uhr)

    daten = fahre(
        telekom,
        karte,
        "telekom.yaml",
        crawle,
        HEUTE,
        1_000_000.0,
        gelesen={},
        uhr=uhr,
        schlafe=uhr.schlafe,
    )

    seiten = len(telekom.seiten)
    assert uhr.schlaf == [MINUTE] * (seiten - 1)
    abstaende = [b - a for a, b in zip(aufrufe, aufrufe[1:], strict=False)]
    assert abstaende == [SEITE_S + MINUTE] * (seiten - 1)
    assert [s["sperre"] for s in daten["seiten"]] == ["challenge_bestanden"] * seiten
    assert [s["http_status"] for s in daten["seiten"]] == [200] * seiten


def test_nach_stoerung_kein_seitenabstand_mehr_und_sperre_je_seite(telekom, karte):
    uhr = Uhr()
    crawle, aufrufe = _crawler(uhr, gestoert_ab=1, sperre="challenge")

    daten = fahre(
        telekom,
        karte,
        "telekom.yaml",
        crawle,
        HEUTE,
        10_000.0,
        gelesen={},
        uhr=uhr,
        schlafe=uhr.schlafe,
    )

    assert len(aufrufe) == 2
    assert uhr.schlaf == [MINUTE]
    seiten = daten["seiten"]
    assert [s["sperre"] for s in seiten[:2]] == ["challenge_bestanden", "challenge"]
    assert [s["http_status"] for s in seiten[:2]] == [200, 202]
    assert all(s["sperre"] is None for s in seiten[2:])
    assert all(s["http_status"] is None for s in seiten[2:])


def test_ohne_seitenabstand_kein_schlaf(telekom, karte):
    from dataclasses import replace

    uhr = Uhr()
    crawle, _ = _crawler(uhr)

    fahre(
        replace(telekom, seitenabstand_sekunden=0.0),
        karte,
        "telekom.yaml",
        crawle,
        HEUTE,
        10_000.0,
        gelesen={},
        uhr=uhr,
        schlafe=uhr.schlafe,
    )

    assert uhr.schlaf == []
