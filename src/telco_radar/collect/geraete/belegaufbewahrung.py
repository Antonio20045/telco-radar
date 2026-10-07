"""Aufbewahrung der Belegdateien nach Abschnitt 10, gerechnet über das Manifest.

Das Manifest bleibt dauerhaft. Über Screenshot und Mitschnitt eines Belegs entscheidet
``aufbewahrung``: der erste Beleg einer Reihe und jeder, dessen Werte sich gegen den
vorigen derselben Reihe ändern, bleibt dauerhaft; jeder jüngere als ``TAEGLICH_TAGE``
Tage bleibt (täglich); danach bleibt je Reihe und ISO-Kalenderwoche einer, der früheste
noch nicht gedeckten Woche (Wochenbeleg); jeder andere wird gelöscht. Eine Reihe ist
Anbieter, Produktseite und Variante. Werte vergleicht sie ohne Lücken, so ändert der
Wechsel der Belegversion (``klickbeleg.BELEGFELDER``) nichts. Der Stichtag kommt vom
Aufrufer, nie von der Uhr.
Dieses Modul ruft kein Netz.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date

from .belegmanifest import ablageschluessel, belegtag
from .klickbeleg import Beleg

TAEGLICH_TAGE = 90
ERSTER = "erster Beleg der Variante"
WERTAENDERUNG = "Wertänderung"
TAEGLICH = f"jünger als {TAEGLICH_TAGE} Tage"
WOCHENBELEG = "Wochenbeleg"
LOESCHEN = f"älter als {TAEGLICH_TAGE} Tage, ohne Wertänderung, kein Wochenbeleg"

Reihe = tuple[str, str, object, object, object]


@dataclass(frozen=True)
class Entscheidung:
    """Ob die Dateien eines Belegs bleiben, warum, und ihre Ablageschlüssel."""

    beleg_id: str
    behalten: bool
    grund: str
    dateien: tuple[str, ...]


def aufbewahrung(belege: Iterable[Beleg], stichtag: date) -> list[Entscheidung]:
    """Je Beleg eine Entscheidung, in der Reihenfolge der Eingabe, ohne Doppelte."""
    eindeutig = list({b.beleg_id: b for b in belege}.values())
    reihen: dict[Reihe, list[Beleg]] = {}
    for beleg in eindeutig:
        reihen.setdefault(reihe_von(beleg), []).append(beleg)
    entschieden: dict[str, Entscheidung] = {}
    for folge in reihen.values():
        folge.sort(key=lambda b: (b.zeitpunkt, b.beleg_id))
        vorher: Beleg | None = None
        gedeckt: set[tuple[int, int]] = set()
        for beleg in folge:
            tag = belegtag(beleg)
            woche = tag.isocalendar()[:2]
            grund = _grund(beleg, vorher, tag, stichtag, woche in gedeckt)
            if grund != LOESCHEN:
                gedeckt.add(woche)
            dateien = tuple(
                ablageschluessel(beleg, d) for d in (beleg.bild, beleg.mitschnitt)
            )
            entschieden[beleg.beleg_id] = Entscheidung(
                beleg.beleg_id, grund != LOESCHEN, grund, dateien
            )
            vorher = beleg
    return [entschieden[b.beleg_id] for b in eindeutig]


def reihe_von(beleg: Beleg) -> Reihe:
    """Anbieter, Produktseite und Variante: die Reihe, in der Werte sich ändern."""
    v = beleg.variante
    return (beleg.anbieter, beleg.adresse, v["speicher"], v["tarif"], v["laufzeit"])


def _grund(
    beleg: Beleg, vorher: Beleg | None, tag: date, stichtag: date, gedeckt: bool
) -> str:
    if vorher is None:
        return ERSTER
    if _gelesen(beleg) != _gelesen(vorher):
        return WERTAENDERUNG
    if (stichtag - tag).days < TAEGLICH_TAGE:
        return TAEGLICH
    if not gedeckt:
        return WOCHENBELEG
    return LOESCHEN


def _gelesen(beleg: Beleg) -> dict[str, object]:
    """Die gelesenen Werte; ein Feld erst einer späteren Version gilt als gleich."""
    return {f: w for f, w in beleg.werte.items() if w is not None}
