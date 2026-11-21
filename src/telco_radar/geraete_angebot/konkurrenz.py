"""Keine Zählung neben einem anderen Lauf auf denselben Hosts (Prüfung PR 205).

Feste UTC-Fenster schützen nicht vor verspäteten Läufen (``geraete.yml`` nennt
Stunden Verzug). Vor dem Start und danach alle ``TAKT_S`` fragt der Zähler darum
GitHub (``gh api``, nur lesend, ``actions: read``), ob ein Lauf von ``klick.yml``,
``geraete.yml`` oder ``gegenprobe.yml`` gerade läuft oder wartet, der denselben Host
besucht. Dann wartet er gegen die Restzeit (``WARTE_S`` je Runde) und hört sonst
benannt auf („nicht gezählt: Klick-Lauf läuft“). Lässt sich das nicht prüfen (lokal,
``gh`` fehlt), steht das im Ergebnis (``Zaehlung.konkurrenz``), nie still.
"""

from __future__ import annotations

from collections.abc import Callable

KLICK_HOSTS = frozenset({"telekom", "vodafone", "o2", "1und1", "congstar"})
ALLE = KLICK_HOSTS | {"tarifwelt"}
LAEUFE = {
    "klick.yml": ("Klick-Lauf", KLICK_HOSTS),
    "geraete.yml": ("Gerätelauf", ALLE),
    "gegenprobe.yml": ("Gegenprobe", ALLE),
}
"""Workflow -> (Name, Anbieter, deren Hosts er besucht)."""
TAKT_S = 300.0
WARTE_S = 60.0
NICHT_PRUEFBAR = "Prüfung auf parallele Läufe nicht möglich"


class NichtPruefbar(Exception):
    """Die Abfrage an GitHub ist gescheitert (benannt, nicht still)."""


class Konkurrenz:
    """``abfrage(workflow)`` gibt die Zahl laufender oder wartender Läufe; ``None``
    heißt: keine Abfrage möglich (lokal)."""

    def __init__(
        self,
        abfrage: Callable[[str], int] | None,
        anbieter: str,
        mono: Callable[[], float],
        schlafe: Callable[[float], None],
    ) -> None:
        """``mono``/``schlafe`` sind Uhr und Warten (im Test ersetzt)."""
        self.abfrage, self.anbieter = abfrage, anbieter
        self.mono, self.schlafe = mono, schlafe
        self.zuletzt: float | None = None
        self.vermerk: str | None = None

    def laeuft(self) -> str | None:
        """Name des Laufs, der gerade denselben Host besucht; sonst ``None``."""
        if self.abfrage is None:
            self.vermerk = f"{NICHT_PRUEFBAR} (ohne GitHub-Zugang)"
            return None
        for workflow, (name, anbieter) in LAEUFE.items():
            if self.anbieter not in anbieter:
                continue
            try:
                zahl = self.abfrage(workflow)
            except NichtPruefbar as fehler:
                self.vermerk = f"{NICHT_PRUEFBAR}: {fehler}"[:200]
                continue
            if zahl:
                return f"{name} läuft"
        return None

    def frei(self, ende: float) -> str | None:
        """Wartet, bis kein Lauf mehr denselben Host besucht; ``None`` = frei,
        sonst der Grund, wenn die Restzeit bis ``ende`` nicht reicht."""
        self.zuletzt = self.mono()
        grund = self.laeuft()
        while grund is not None:
            if ende - self.mono() < 2 * WARTE_S:
                return grund
            self.schlafe(WARTE_S)
            grund = self.laeuft()
        self.zuletzt = self.mono()
        return None

    def zwischendurch(self, ende: float) -> str | None:
        """Wie ``frei``, aber höchstens alle ``TAKT_S`` eine Abfrage."""
        if self.zuletzt is not None and self.mono() - self.zuletzt < TAKT_S:
            return None
        return self.frei(ende)
