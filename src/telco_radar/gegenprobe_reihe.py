"""Reihenfolge der Gegenprobe: reihum über die Anbieter, gruppiert nach Seitenbesuch,
und der Schutzschalter je Anbieter.

Das Zeitbudget eines Laufs reicht nicht immer für alle Bündel (21.11.2026: 674 Bündel,
o2s 452 Änderungen nahmen alles). ``reihum`` hält die Anbieter gleichauf,
``gruppiere`` legt die Bündel einer Seite in einen Besuch. Am selben Tag scheiterten
169 1&1-Besuche nacheinander an derselben Stelle („Auswahl nicht gefunden“) und
verbrannten rund 60 % der Laufzeit: ``Schutzschalter`` beschränkt einen Anbieter nach
``SCHUTZ_GLEICHE_FEHLER`` gescheiterten Besuchen gleicher Fehlerart in Folge auf
bekannt lesbare Seiten, nach einer zweiten Serie oder einer Sperre schaltet er ihn ab,
und nennt jeden Schritt mit Grund.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable, Mapping

SCHUTZ_GLEICHE_FEHLER = 5
"""So viele gescheiterte Seitenbesuche gleicher Fehlerart in Folge schalten einen
Anbieter eine Stufe herunter (``Schutzschalter``)."""


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
NUR_BEKANNT = "nur_bekannt"
"""Nach einer Fehlerserie: nur noch Seiten, die schon einmal gut gelesen wurden."""
AUS = "aus"


class Schutzschalter:
    """Zählt je Anbieter gescheiterte Seitenbesuche gleicher Fehlerart in Folge.

    Nach ``SCHUTZ_GLEICHE_FEHLER`` in Folge besucht der Lauf für den Rest der Nacht
    nur noch Seiten mit einer früheren guten Prüfung (``NUR_BEKANNT``): Dauerfehler
    neuer oder fremder Seiten kosten keine Zeit mehr, bekannt lesbare Seiten laufen
    weiter. Scheitert auch dort eine Serie, ist der Anbieter aus (``AUS``); eine Sperre
    schaltet ihn sofort aus. ``ausfaelle`` nennt jeden Schritt mit Grund."""

    def __init__(self, grenze: int = SCHUTZ_GLEICHE_FEHLER) -> None:
        self.grenze = grenze
        self._folge: dict[str, tuple[str, int]] = {}
        self._stufe: dict[str, str] = {}
        self._gruende: dict[str, list[str]] = {}

    def stufe(self, anbieter: str) -> str:
        """``FREI``, ``NUR_BEKANNT`` oder ``AUS``."""
        return self._stufe.get(anbieter, FREI)

    def grund(self, anbieter: str) -> str | None:
        """Der jüngste Grund, warum Seiten dieses Anbieters nicht mehr besucht
        werden; None, solange er frei läuft."""
        gruende = self._gruende.get(anbieter)
        return gruende[-1] if gruende else None

    def ausfaelle(self, anbieter: str) -> list[str]:
        """Jede Einschränkung und jeder Ausfall dieses Anbieters in diesem Lauf."""
        return list(self._gruende.get(anbieter, []))

    def abgeschaltet(self) -> list[str]:
        """Die Anbieter mit Einschränkung oder Ausfall."""
        return sorted(self._gruende)

    def erfolg(self, anbieter: str) -> None:
        """Ein Besuch hat gelesen: die Folge beginnt neu."""
        self._folge.pop(anbieter, None)

    def _setze(self, anbieter: str, stufe: str, grund: str) -> None:
        self._stufe[anbieter] = stufe
        self._gruende.setdefault(anbieter, []).append(grund)

    def fehler(self, anbieter: str, grund: str, sofort: bool = False) -> None:
        """Ein Besuch ist gescheitert; ``sofort`` (Sperre) schaltet ohne Folge ab."""
        if sofort:
            self._setze(
                anbieter, AUS, f"Ausfall nach Sperre ({grund}), Rest nicht geöffnet"
            )
            return
        art = fehlerart(grund)
        vorige, zahl = self._folge.get(anbieter, (art, 0))
        zahl = zahl + 1 if vorige == art else 1
        self._folge[anbieter] = (art, zahl)
        if zahl < self.grenze:
            return
        self._folge.pop(anbieter)
        serie = f"{zahl} Seitenbesuche in Folge gescheitert ({art})"
        if self.stufe(anbieter) == FREI:
            self._setze(
                anbieter, NUR_BEKANNT, f"{serie}: nur noch bekannt lesbare Seiten"
            )
        elif self.stufe(anbieter) == NUR_BEKANNT:
            self._setze(
                anbieter, AUS, f"Ausfall: auch auf bekannt lesbaren Seiten {serie}"
            )
