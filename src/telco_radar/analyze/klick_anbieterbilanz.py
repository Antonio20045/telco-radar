"""Die Klick-Bilanz JE ANBIETER (``klick_zusammenfuehrung``).

Die Summenzeile der Zusammenführung zählt über alle Anbieter zusammen. Verliert ein
einzelner Anbieter seine ganze Tagesmessung, steht in ihr dieselbe Art Zahl wie bei
einer Handvoll zurückgehaltener Sätze irgendwo sonst: am 13.11.2026 steckten 760
zurückgehaltene congstar-Sätze in „1992 Adaptersätze nicht ersetzt“, und aus dem
Protokoll des Laufs war nicht zu sehen, dass congstar an diesem Tag gar nichts
beigetragen hat. Darum zählt jede Zeile hier für genau einen Anbieter:

``saetze``            eindeutige Klick-Sätze dieses Anbieters;
``ersetzt``           Adaptersätze, die einer von ihnen ersetzt hat;
``unvollstaendig``    Adaptersätze, die ganz blieben, samt fehlender Wertfelder;
``ohne_gegenstueck``  Klick-Sätze ohne Adaptersatz mit ihrem Schlüssel.
"""

from __future__ import annotations

import logging
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass, field

log = logging.getLogger(__name__)

ZEILE = "Klick-Bündel %s: %d Sätze, %d ersetzt, %d unvollständig%s, %d ohne Gegenstück"


@dataclass
class Anbieterbilanz:
    """Was aus den Klick-Sätzen eines Anbieters wurde (Modulkopf)."""

    saetze: int = 0
    ersetzt: int = 0
    unvollstaendig: int = 0
    fehlend: Counter[str] = field(default_factory=Counter)
    ohne_gegenstueck: int = 0

    def als_daten(self) -> dict:
        """Die Zahlen dieses Anbieters für Bilanz und Protokoll."""
        return {
            "saetze": self.saetze,
            "ersetzt": self.ersetzt,
            "unvollstaendig": self.unvollstaendig,
            "felder": dict(self.fehlend),
            "ohne_gegenstueck": self.ohne_gegenstueck,
        }


def fuer(bilanzen: dict[str, Anbieterbilanz], satz: Mapping) -> Anbieterbilanz:
    """Die Zeile des Anbieters dieses Klick-Satzes; beim ersten Satz entsteht sie."""
    return bilanzen.setdefault(str(satz.get("anbieter") or ""), Anbieterbilanz())


def als_daten(bilanzen: dict[str, Anbieterbilanz]) -> dict:
    """Alle Zeilen für die Bilanz, nach Anbietername sortiert."""
    return {name: zeile.als_daten() for name, zeile in sorted(bilanzen.items())}


def protokolliere(je_anbieter: dict) -> None:
    """Eine Protokollzeile je Anbieter; fehlende Felder nur, wenn es welche gibt."""
    for name, zeile in je_anbieter.items():
        felder = ", ".join(f"{f} {n}" for f, n in zeile["felder"].items())
        log.info(
            ZEILE,
            name,
            zeile["saetze"],
            zeile["ersetzt"],
            zeile["unvollstaendig"],
            f" ({felder})" if felder else "",
            zeile["ohne_gegenstueck"],
        )
