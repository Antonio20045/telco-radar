"""Welcher Preis bekommt welches Belegbild, und was kostete dasselbe gestern?

Ein Bild gehört zu (Gerät, Anbieter): ``geraet_id`` und ``anbieter`` stehen im
Klick-Rohsatz (``device_id``, ``speicher_gb``, ``anbieter``). Hat ein Anbieter für ein
Gerät mehrere Tarife und Laufzeiten, gewinnt der Rohsatz mit den niedrigsten
Gesamtkosten über
``TCO_HORIZONT`` Monate (bei Gleichstand die kleinere ``beleg_id``): es ist der Preis,
den die Seite als Leitzahl zeigt. Die Gesamtkosten rechnet ``tco_kosten`` an derselben
Stelle wie die Seite (CLAUDE.md Clean Code 1); eine Lücke heißt ``None`` und verliert
gegen jede Zahl.

Der Vergleichswert ist der niedrigste Wert derselben (Gerät, Anbieter) im Bestand
``geraete_tco.json`` mit Status ``gueltig``. Der Klick-Lauf läuft vor dem Geräte-Lauf;
der Bestand ist darum der Stand der letzten Messung. Ohne gültigen Bestandssatz ist
``vorher_24`` ``None`` und die Änderung nie groß (``beleg_regeln``).
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any

from ..tco_kosten import kosten_ueber
from ..tco_model import TCO_HORIZONT
from .geraete_pruefstatus import GUELTIG, buendel_aus_satz

GeraetAusSku = Callable[[str], tuple[str, int | None]]

GRUND_OHNE_BELEG = "ohne beleg_id"
GRUND_OHNE_GERAET = "ohne Gerät"
GRUND_BUENDEL = "Bündel nicht bildbar"


@dataclass(frozen=True)
class Messung:
    """Der Preis eines (Gerät, Anbieter), zu dem das Bild gehört."""

    device_id: str
    speicher_gb: int | None
    anbieter: str
    beleg_id: str
    gesamt_24: float | None
    vorher_24: float | None


@dataclass
class Zuordnung:
    """Gewählte Messungen, übersprungene Gründe (Zähler) und Zahl der Mehrdeutigen."""

    messungen: list[Messung]
    uebersprungen: dict[str, int]
    mehrdeutig: int = 0


def _niedriger(a: float | None, b: float | None) -> float | None:
    """Das kleinere der beiden; ``None`` verliert gegen jede Zahl."""
    if a is None:
        return b
    if b is None:
        return a
    return min(a, b)


def _gesamt(satz: dict[str, Any]) -> float | None:
    return kosten_ueber(buendel_aus_satz(satz), TCO_HORIZONT).gesamt


def vorher_je_geraet(
    bestand: Iterable[dict[str, Any]], geraet: GeraetAusSku
) -> dict[tuple[str, int | None, str], float | None]:
    """Niedrigste Gesamtkosten je (device_id, speicher, anbieter) im Bestand."""
    ergebnis: dict[tuple[str, int | None, str], float | None] = {}
    for satz in bestand:
        if not str(satz.get("pruefung") or "").startswith(GUELTIG):
            continue
        device_id, speicher = geraet(str(satz.get("sku_id") or ""))
        if not device_id:
            continue
        try:
            gesamt = _gesamt(satz)
        except (TypeError, ValueError, KeyError):
            continue
        schluessel = (device_id, speicher, str(satz.get("anbieter")))
        ergebnis[schluessel] = _niedriger(ergebnis.get(schluessel), gesamt)
    return ergebnis


def _besser(neu: tuple, alt: tuple) -> bool:
    """Ist ``neu`` (Gesamtkosten, beleg_id) der bessere Rohsatz als ``alt``?"""
    if neu[0] is None or alt[0] is None:
        if neu[0] is None and alt[0] is None:
            return neu[1] < alt[1]
        return neu[0] is not None
    return (neu[0], neu[1]) < (alt[0], alt[1])


def ordne_zu(
    rohsaetze: Iterable[dict[str, Any]],
    bestand: Iterable[dict[str, Any]],
    geraet: GeraetAusSku,
) -> Zuordnung:
    """Eine ``Messung`` je (Gerät, Anbieter) mit Beleg; Rest zählt ``mehrdeutig``."""
    vorher = vorher_je_geraet(bestand, geraet)
    ergebnis = Zuordnung([], {})
    beste: dict[tuple[str, int | None, str], Messung] = {}

    def melde(grund: str) -> None:
        ergebnis.uebersprungen[grund] = ergebnis.uebersprungen.get(grund, 0) + 1

    for satz in rohsaetze:
        beleg_id = satz.get("beleg_id")
        if not beleg_id:
            melde(GRUND_OHNE_BELEG)
            continue
        device_id = str(satz.get("device_id") or "")
        if not device_id:
            melde(GRUND_OHNE_GERAET)
            continue
        try:
            gesamt = _gesamt(satz)
        except (TypeError, ValueError, KeyError):
            melde(GRUND_BUENDEL)
            continue
        speicher = satz.get("speicher_gb")
        speicher = int(speicher) if speicher else None
        schluessel = (device_id, speicher, str(satz.get("anbieter")))
        messung = Messung(
            device_id,
            speicher,
            schluessel[2],
            str(beleg_id),
            gesamt,
            vorher.get(schluessel),
        )
        alt = beste.get(schluessel)
        if alt is not None:
            ergebnis.mehrdeutig += 1
            if not _besser((gesamt, messung.beleg_id), (alt.gesamt_24, alt.beleg_id)):
                continue
        beste[schluessel] = messung
    ergebnis.messungen = sorted(
        beste.values(), key=lambda m: (m.device_id, m.speicher_gb or 0, m.anbieter)
    )
    return ergebnis
