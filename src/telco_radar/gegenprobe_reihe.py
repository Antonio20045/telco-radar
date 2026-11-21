"""Reihenfolge der Gegenprobe: reihum über die Anbieter, gruppiert nach Seitenbesuch,
und der Schutzschalter je Anbieter.

Das Zeitbudget eines Laufs reicht nicht immer für alle Bündel (21.11.2026: 674 Bündel,
o2s 452 Änderungen nahmen alles). ``reihum`` hält die Anbieter gleichauf,
``gruppiere`` legt die Bündel einer Seite in einen Besuch. Am selben Tag scheiterten
169 1&1-Besuche nacheinander an derselben Stelle („Auswahl nicht gefunden“) und
verbrannten rund 60 % der Laufzeit: ``Schutzschalter`` beendet eine Art von Bündeln
eines Anbieters nach ``SCHUTZ_GLEICHE_FEHLER`` gescheiterten Besuchen gleicher
Fehlerart in Folge, nach einer Sperre den ganzen Anbieter, und nennt den Grund.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable, Mapping

SCHUTZ_GLEICHE_FEHLER = 5
"""So viele gescheiterte Seitenbesuche gleicher Fehlerart in Folge beenden eine Art
von Bündeln eines Anbieters für den Rest des Laufs."""


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


class Schutzschalter:
    """Zählt je Anbieter und Art gescheiterte Seitenbesuche in Folge und schaltet die
    Art ab, die scheitert; eine Sperre schaltet den ganzen Anbieter ab. Die Art ist,
    was die Bündel eines Besuchs gemeinsam haben (``herleitung``: Produktseite oder
    Tarif-Übersicht); Bündel anderer Art desselben Anbieters laufen weiter. ``grund``
    nennt je abgeschalteter Art den Ausfall (benannt, kein stilles Leer)."""

    def __init__(self, grenze: int = SCHUTZ_GLEICHE_FEHLER) -> None:
        self.grenze = grenze
        self._folge: dict[tuple[str, str], tuple[str, int]] = {}
        self.aus: dict[tuple[str, str | None], str] = {}
        """(Anbieter, Art) → Grund; Art None heißt: der ganze Anbieter (Sperre)."""

    def grund(self, anbieter: str, art: str = "") -> str | None:
        """Warum Bündel dieser Art nicht mehr geöffnet werden; None: sie laufen."""
        return self.aus.get((anbieter, None)) or self.aus.get((anbieter, art))

    def ausfaelle(self, anbieter: str) -> list[str]:
        """Jeder Ausfall dieses Anbieters in diesem Lauf."""
        return [g for (a, _), g in sorted(self.aus.items(), key=str) if a == anbieter]

    def erfolg(self, anbieter: str, art: str = "") -> None:
        """Ein Besuch hat gelesen: die Folge dieser Art beginnt neu."""
        self._folge.pop((anbieter, art), None)

    def fehler(
        self, anbieter: str, grund: str, sofort: bool = False, art: str = ""
    ) -> None:
        """Ein Besuch ist gescheitert; ``sofort`` (Sperre) schaltet ohne Folge ab."""
        if sofort:
            self.aus[(anbieter, None)] = (
                f"Ausfall nach Sperre ({grund}), Rest nicht geöffnet"
            )
            return
        fehler = fehlerart(grund)
        vorige, zahl = self._folge.get((anbieter, art), (fehler, 0))
        zahl = zahl + 1 if vorige == fehler else 1
        self._folge[(anbieter, art)] = (fehler, zahl)
        if zahl >= self.grenze:
            self.aus[(anbieter, art)] = (
                f"Ausfall ({art or 'Produktseite'}): {zahl} Seitenbesuche in Folge "
                f"gescheitert ({fehler}), Rest dieser Art nicht geöffnet"
            )
