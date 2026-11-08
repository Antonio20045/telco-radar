"""Welcher Preis bekommt welches Belegbild, und was kostete dasselbe gestern?

Ein Bild gehört zu (Gerät, Anbieter): ``geraet_id`` und ``anbieter`` stehen im
Klick-Rohsatz (``device_id``, ``speicher_gb``, ``anbieter``). Hat ein Anbieter für ein
Gerät mehrere Tarife und Laufzeiten, gewinnt der Rohsatz mit den niedrigsten
Gesamtkosten über
``TCO_HORIZONT`` Monate (bei Gleichstand die kleinere ``beleg_id``): es ist der Preis,
den die Seite als Leitzahl zeigt. Die Gesamtkosten rechnet ``tco_kosten`` an derselben
Stelle wie die Seite (CLAUDE.md Clean Code 1); eine Lücke heißt ``None`` und verliert
gegen jede Zahl.

Der Vergleichswert ist der letzte Stand DERSELBEN Konfiguration im Bestand
``geraete_tco.json``: gleiches Gerät, gleicher Speicher, Anbieter, Tarif, Laufzeit und
Zustand, gleiche Quelle (Klick), Status ``gueltig`` oder ``veraltet`` (``quarantaene``
zählt nicht). Es ist ausdrücklich nicht das Minimum über alle Tarife: ein unveränderter
Preis darf nicht „groß“ werden, nur weil ein anderer Tarif billiger ist. Der Klick-Lauf
läuft vor dem Geräte-Lauf; der Bestand ist darum der Stand der letzten Messung.
Gibt es den Satz dort nicht (neue Konfiguration), ist ``vorher_24`` ``None`` und die
Änderung nie groß (``beleg_regeln``).
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any

from ..collect.geraete.klickrohsatz import QUELLE
from .beleg_position import gesamt_kosten
from .geraete_pruefstatus import GUELTIG, VERALTET
from .klick_zusammenfuehrung import Schluessel, klickschluessel

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


def vorher_je_konfiguration(
    bestand: Iterable[dict[str, Any]], geraet: GeraetAusSku
) -> dict[Schluessel, float | None]:
    """Letzter Stand der Gesamtkosten je Klick-Konfiguration im Bestand.

    Schlüssel ist ``klickschluessel`` (Anbieter, Gerät, Speicher, Tarif, Laufzeit,
    Zustand). Gibt es mehrere Sätze, gewinnt der jüngste ``abgerufen_am``, bei
    Gleichstand der niedrigere Wert.
    """
    stand: dict[Schluessel, tuple[str, float | None]] = {}
    for satz in bestand:
        if satz.get("quelle_art") != QUELLE:
            continue
        pruefung = str(satz.get("pruefung") or "")
        if not pruefung.startswith((GUELTIG, VERALTET)):
            continue
        device_id, speicher = geraet(str(satz.get("sku_id") or ""))
        if not device_id:
            continue
        try:
            gesamt = gesamt_kosten(satz)
        except (TypeError, ValueError, KeyError):
            continue
        schluessel = klickschluessel(
            {**satz, "device_id": device_id, "speicher_gb": speicher}, mit_zustand=True
        )
        abgerufen = str(satz.get("abgerufen_am") or "")
        alt = stand.get(schluessel)
        if alt is None or abgerufen > alt[0]:
            stand[schluessel] = (abgerufen, gesamt)
        elif abgerufen == alt[0]:
            stand[schluessel] = (abgerufen, _niedriger(alt[1], gesamt))
    return {schluessel: gesamt for schluessel, (_, gesamt) in stand.items()}


def _besser(neu: tuple, alt: tuple) -> bool:
    """Ist ``neu`` (Gesamtkosten, beleg_id) der bessere Rohsatz als ``alt``?"""
    if neu[0] is None or alt[0] is None:
        if neu[0] is None and alt[0] is None:
            return neu[1] < alt[1]
        return neu[0] is not None
    return (neu[0], neu[1]) < (alt[0], alt[1])


def ist_besser(neu: Messung, alt: Messung) -> bool:
    """Ist ``neu`` die bessere Messung für dasselbe Bild als ``alt`` (niedrigere
    Gesamtkosten, ``None`` verliert, bei Gleichstand die kleinere ``beleg_id``)?"""
    return _besser((neu.gesamt_24, neu.beleg_id), (alt.gesamt_24, alt.beleg_id))


def ordne_zu(
    rohsaetze: Iterable[dict[str, Any]],
    bestand: Iterable[dict[str, Any]],
    geraet: GeraetAusSku,
) -> Zuordnung:
    """Eine ``Messung`` je (Gerät, Anbieter) mit Beleg; Rest zählt ``mehrdeutig``."""
    vorher = vorher_je_konfiguration(bestand, geraet)
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
            gesamt = gesamt_kosten(satz)
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
            vorher.get(klickschluessel(satz, mit_zustand=True)),
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
