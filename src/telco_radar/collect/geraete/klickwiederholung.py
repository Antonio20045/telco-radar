"""Serverfehler im Klick-Tageslauf: dieselbe Seite noch einmal, statt aufzuhören.

Nachtlauf 21.11.2026 (1&1, Eintrag ``1und1``): ein einziges HTTP 502 der ersten
Tarifdetail-Seite hielt den Eintrag an, sieben Übersichten und 21 Produktseiten blieben
unbesucht. Ein 5xx ist kein Bot-Schutz (CLAUDE.md Regel 10). ``Wiederholung.um`` legt
sich im Tageslauf (``klicktageslauf.fahre``) um Crawler und Übersichtsleser: endet eine
Seite mit ``klicklauf.STOERUNG_SERVER``, liest sie dieselbe Seite höchstens
``WIEDERHOLUNGEN_SERVERFEHLER`` Mal neu, nach den wachsenden Pausen
``PAUSEN_SERVERFEHLER_S`` und nur, solange danach bis zur Grenze der Seite noch
``MINDESTZEIT_NACH_PAUSE_S`` bleiben (CLAUDE.md Regel 8). Jede Anfrage geht weiter durch
dieselbe Hostschleuse samt robots.txt und Crawl-delay. Nach einer Wiederholung nennt
``versuche`` die Zahl der Lesungen (Produktseite unter ``ladung``, Übersicht oben).

Bleibt der Fehler, ist die Seite gestört mit Serverfehler, und der Tageslauf liest die
nächste. Erst ``HOECHSTE_SERVERFEHLER_IN_FOLGE`` solche Seiten hintereinander, ohne eine
gelesene dazwischen, beenden den Anbieter: die letzte trägt dann ``stoerung`` ``None``
und den Grund ``GRUND_SERVERFEHLER``, und der Tageslauf schickt wie nach Bot-Schutz
keine Anfrage mehr. 403, 429 und Challenge sind keine Serverfehler und beenden ihn wie
bisher sofort.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import replace
from typing import TypeVar, cast

from .klicklauf import LAUF_GELESEN, LAUF_GESTOERT, STOERUNG_SERVER, Klicklauf

log = logging.getLogger(__name__)

WIEDERHOLUNGEN_SERVERFEHLER = 2
PAUSEN_SERVERFEHLER_S = (20.0, 60.0)
"""Pause vor dem ersten und vor dem zweiten neuen Versuch."""
MINDESTZEIT_NACH_PAUSE_S = 3 * 60
HOECHSTE_SERVERFEHLER_IN_FOLGE = 3
GRUND_SERVERFEHLER = "Seiten in Folge mit Serverfehler"

Ziel = TypeVar("Ziel")
Ergebnis = TypeVar("Ergebnis", Klicklauf, dict)
Erster = TypeVar("Erster", bound=Callable[..., Klicklauf])
Zweiter = TypeVar("Zweiter", bound=Callable[..., dict])


def _status(ergebnis: Klicklauf | dict) -> tuple[object, object, object]:
    if isinstance(ergebnis, Klicklauf):
        return ergebnis.status, ergebnis.stoerung, ergebnis.grund
    return ergebnis.get("status"), ergebnis.get("stoerung"), ergebnis.get("grund")


def serverfehler(ergebnis: Klicklauf | dict) -> bool:
    """Wahr, wenn Lauf oder Übersicht mit einem Serverfehler gestört endete."""
    status, stoerung, _ = _status(ergebnis)
    return status == LAUF_GESTOERT and stoerung == STOERUNG_SERVER


def _mit_versuchen(ergebnis: Ergebnis, versuche: int) -> Ergebnis:
    if versuche == 1:
        return ergebnis
    if isinstance(ergebnis, Klicklauf):
        return replace(
            ergebnis, ladung={**(ergebnis.ladung or {}), "versuche": versuche}
        )
    return {**ergebnis, "versuche": versuche}


def _als_stopp(ergebnis: Ergebnis, grund: str) -> Ergebnis:
    """Die Seite als Störung ohne Art; bei einer Übersicht auch ihre Seiten."""
    if isinstance(ergebnis, Klicklauf):
        return replace(ergebnis, stoerung=None, grund=grund)
    seiten = [
        {**s, "stoerung": None, "grund": grund} if serverfehler(s) else s
        for s in ergebnis.get("seiten") or []
    ]
    neu = {**ergebnis, "stoerung": None, "grund": grund}
    return {**neu, "seiten": seiten} if "seiten" in ergebnis else neu


class Wiederholung:
    """Wiederholt Seiten mit Serverfehler und zählt sie in Folge (Modulkopf)."""

    def __init__(
        self, uhr: Callable[[], float], schlafe: Callable[[float], None]
    ) -> None:
        self.uhr, self.schlafe = uhr, schlafe
        self.in_folge = 0

    def um(self, crawle: Erster, lies: Zweiter) -> tuple[Erster, Zweiter]:
        """Crawler ``(seite, ende)`` und Übersichtsleser ``(adresse, ende)`` mit
        Wiederholung und gemeinsamer Zählung in Folge."""
        return cast(Erster, self._mit(crawle)), cast(Zweiter, self._mit(lies))

    def _mit(
        self, lies: Callable[[Ziel, float], Ergebnis]
    ) -> Callable[[Ziel, float], Ergebnis]:
        def wiederholt(ziel: Ziel, ende: float) -> Ergebnis:
            ergebnis = lies(ziel, ende)
            versuche = 1
            for pause in PAUSEN_SERVERFEHLER_S[:WIEDERHOLUNGEN_SERVERFEHLER]:
                rest = ende - self.uhr()
                if (
                    not serverfehler(ergebnis)
                    or rest < pause + MINDESTZEIT_NACH_PAUSE_S
                ):
                    break
                grund = _status(ergebnis)[2]
                log.info("Klick-Tageslauf: %s, neuer Versuch in %.0f s", grund, pause)
                self.schlafe(pause)
                ergebnis = lies(ziel, ende)
                versuche += 1
            return self._zaehle(_mit_versuchen(ergebnis, versuche))

        return wiederholt

    def _zaehle(self, ergebnis: Ergebnis) -> Ergebnis:
        status, _, grund = _status(ergebnis)
        if status == LAUF_GELESEN:
            self.in_folge = 0
        if not serverfehler(ergebnis):
            return ergebnis
        self.in_folge += 1
        if self.in_folge < HOECHSTE_SERVERFEHLER_IN_FOLGE:
            return ergebnis
        return _als_stopp(ergebnis, f"{self.in_folge} {GRUND_SERVERFEHLER}: {grund}")
