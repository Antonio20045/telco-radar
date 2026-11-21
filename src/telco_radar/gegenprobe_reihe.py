"""Reihenfolge der Gegenprobe: reihum über die Anbieter, gruppiert nach Seitenbesuch,
und der Schutzschalter je Anbieter.

Das Zeitbudget eines Laufs reicht nicht immer für alle Bündel (21.11.2026: 674 Bündel,
o2s 452 Änderungen nahmen alles). ``reihum`` hält die Anbieter gleichauf,
``gruppiere`` legt die Bündel einer Seite in einen Besuch. Am selben Tag scheiterten
169 1&1-Besuche nacheinander an derselben Stelle („Auswahl nicht gefunden“) und
verbrannten rund 60 % der Laufzeit. Eine Fehlerserie sagt aber nichts über die nächste
Seite (dritter Prüferbefund zu PR 200): die Wiederholung gescheiterter Seiten begrenzt
``gegenprobe_fenster.VERDAECHTIG_JE_NACHT``, den ganzen Anbieter stoppt
``Schutzschalter`` nur bei Sperre oder gestörtem Host.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable, Mapping

SCHUTZ_SERVERFEHLER = 5
"""So viele Serverfehler (5xx, Netz) auf nicht verdächtigen Seiten in Folge stoppen
einen Anbieter für den Rest des Laufs (``Schutzschalter``)."""


def reihum(listen: Mapping[str, list]) -> list:
    """Die Listen je Anbieter abwechselnd (Anbieter alphabetisch), bis alle leer."""
    out: list = []
    stellen = [listen[a] for a in sorted(listen)]
    for runde in range(max((len(liste) for liste in stellen), default=0)):
        out += [liste[runde] for liste in stellen if runde < len(liste)]
    return out


def gruppiere(
    wahl: Iterable[tuple[str, str]], seite: Callable[[str], str]
) -> list[list[tuple[str, str]]]:
    """Die Auswahl nach Seitenbesuch: ``seite(bid)`` nennt den Besuch, der das Bündel
    prüft (``gegenprobe_wege.seite_von``). Eine Gruppe steht dort, wo ihr erstes Bündel
    in der Auswahl steht, und nimmt die übrigen Bündel derselben Seite mit."""
    gruppen: dict[str, list[tuple[str, str]]] = {}
    for bid, anlass in wahl:
        gruppen.setdefault(seite(bid), []).append((bid, anlass))
    return list(gruppen.values())


def fehlerart(grund: str) -> str:
    """Die Art eines Fehlers ohne Einzelheiten: der Text vor dem Doppelpunkt, Zahlen
    gleich („Auswahl nicht gefunden: 256 GB“ und „…: 1 TB“ sind dieselbe Art)."""
    return re.sub(r"\d+", "#", grund.split(":")[0]).strip()


FREI = "frei"
AUS = "aus"
SERVERFEHLER = re.compile(r"HTTP 5\d\d|net::ERR_")
"""Fehler, die für einen gestörten Host sprechen, nicht für eine einzelne Seite. Eine
Ladezeitüberschreitung ist ein Seitenfehler (die Seite wird verdächtig), kein
Host-Ausfall (Schlussprüfung PR 200)."""


def ist_serverfehler(grund: str) -> bool:
    """5xx oder Netzfehler (nicht Timeout, nicht „Auswahl nicht gefunden“)."""
    return SERVERFEHLER.search(grund) is not None


class Schutzschalter:
    """Stoppt einen Anbieter für den Rest des Laufs, aber nur, wenn der Host gestört
    ist: nach einer Sperre (Bot-Schutz, nie umgangen) sofort, nach
    ``SCHUTZ_SERVERFEHLER`` Serverfehlern in Folge (``ist_serverfehler``), gezählt nur
    auf nicht verdächtigen Seiten (der Lauf meldet nur diese). Formfehler
    einer Seite („Auswahl nicht gefunden“) stoppen nie den Anbieter; ihre Wiederholung
    begrenzt ``gegenprobe_fenster.VERDAECHTIG_JE_NACHT``. ``ausfaelle`` nennt den
    Grund."""

    def __init__(self, grenze: int = SCHUTZ_SERVERFEHLER) -> None:
        self.grenze = grenze
        self._folge: dict[str, int] = {}
        self._gruende: dict[str, list[str]] = {}

    def stufe(self, anbieter: str) -> str:
        """``FREI`` oder ``AUS``."""
        return AUS if anbieter in self._gruende else FREI

    def grund(self, anbieter: str) -> str | None:
        """Warum der Anbieter gestoppt ist; None, solange er läuft."""
        gruende = self._gruende.get(anbieter)
        return gruende[-1] if gruende else None

    def ausfaelle(self, anbieter: str) -> list[str]:
        """Jeder Stopp dieses Anbieters in diesem Lauf."""
        return list(self._gruende.get(anbieter, []))

    def abgeschaltet(self) -> list[str]:
        """Die gestoppten Anbieter."""
        return sorted(self._gruende)

    def erfolg(self, anbieter: str) -> None:
        """Ein Besuch hat gelesen: die Folge beginnt neu."""
        self._folge.pop(anbieter, None)

    def fehler(self, anbieter: str, grund: str, sofort: bool = False) -> None:
        """Ein Besuch ist gescheitert; ``sofort`` (Sperre) stoppt ohne Folge."""
        if anbieter in self._gruende:
            return
        if sofort:
            stopp = f"Ausfall nach Sperre ({grund}), Rest nicht geöffnet"
            self._gruende[anbieter] = [stopp]
            return
        if not ist_serverfehler(grund):
            self._folge.pop(anbieter, None)
            return
        zahl = self._folge.get(anbieter, 0) + 1
        self._folge[anbieter] = zahl
        if zahl >= self.grenze:
            self._gruende[anbieter] = [
                f"Ausfall: {zahl} Serverfehler in Folge ({fehlerart(grund)}), "
                "Host gestört, Rest nicht geöffnet"
            ]
