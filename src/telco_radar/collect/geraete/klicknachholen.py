"""Nachholen: Kombinationen ohne mitgeschnittene Antwort einmal am Ende neu besuchen.

Manche Seite lädt ihre Preisantwort nur nach dem Klick auf eine andere Option: Telekom
lädt ``/v2/details`` weder beim Laden noch nach einem Laufzeitklick, nur nach einem
Speicherklick (Tageslauf 08.10.2026, Actions-Lauf 37740022815: beim vorgewählten
256 GB drei Befunde „keine Antwort mitgeschnitten“, 512 GB und 1 TB gelesen). Ein
solcher Befund kommt ans Ende: sind alle Kombinationen besucht und ist die Frist offen,
besucht der Crawler ihn ein zweites Mal, nun aus dem Zustand der letzten Kombination,
sodass er die Option wieder anklickt. Das neue Ergebnis ersetzt den Befund an seiner
Stelle nur, wenn es gelesen ist (``erfasst`` oder ``befund``); jede Kombination kommt
höchstens einmal dran, und eine dabei abgelaufene Frist zählt nicht als unbesuchte
Kombination. Keine Seite geht neu auf: nur Klicks auf derselben Seite durch dasselbe
Tor.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

from .klickecho import GRUND_OHNE_ANTWORT, Befund
from .klicklauf import BEFUND, ERFASST

if TYPE_CHECKING:
    from .klicklauf import Klicklauf, Kombiergebnis
    from .klickoptionen import Auswahl

OHNE_ANTWORT = Befund("antwort", GRUND_OHNE_ANTWORT)
GELESEN = frozenset({ERFASST, BEFUND})


class Gang(Protocol):
    """Was das Nachholen vom Gang des Crawlers braucht."""

    lauf: Klicklauf
    nach_frist: int

    def zeit_um(self) -> bool:
        """Ob die Frist des Laufs abgelaufen ist."""
        ...


class Nachholen:
    """Die Befunde ohne Antwort eines Durchgangs mit ihrer Stelle in den Ergebnissen."""

    def __init__(self, gang: Gang) -> None:
        self.gang = gang
        self.offen: dict[Auswahl, int] = {}
        self.laufend: Auswahl | None = None
        self.nach_frist = 0

    def naechste(self) -> Auswahl | None:
        """Die nächste nachzuholende Kombination; ``None`` ohne sie oder nach Frist."""
        self.laufend = None
        if self.offen and not self.gang.zeit_um():
            self.laufend = next(iter(self.offen))
            self.nach_frist = self.gang.nach_frist
        return self.laufend

    def lege_ab(self, ergebnis: Kombiergebnis) -> None:
        """Hängt ``ergebnis`` an; beim Nachholen ersetzt es den Befund, wenn gelesen."""
        ergebnisse = self.gang.lauf.ergebnisse
        if self.laufend is not None and ergebnis.auswahl == self.laufend:
            stelle = self.offen.pop(self.laufend)
            self.laufend = None
            self.gang.nach_frist = self.nach_frist
            if ergebnis.status in GELESEN:
                ergebnisse[stelle] = ergebnis
            return
        if ergebnis.status == BEFUND and OHNE_ANTWORT in ergebnis.befunde:
            self.offen[ergebnis.auswahl] = len(ergebnisse)
        ergebnisse.append(ergebnis)
