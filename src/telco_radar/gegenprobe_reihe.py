"""Reihenfolge der Gegenprobe: reihum über die Anbieter, gruppiert nach Seitenbesuch.

Das Zeitbudget eines Laufs reicht nicht immer für alle Bündel (21.11.2026: 674 Bündel,
o2s 452 Änderungen nahmen alles). ``reihum`` hält die Anbieter gleichauf,
``gruppiere`` legt die Bündel einer Seite in einen Besuch.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping


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
