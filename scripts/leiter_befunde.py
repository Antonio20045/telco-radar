"""Befunde der Prüfwerkzeuge, gezählt je Datei und Code ohne Zeile."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

import waechter

Schluessel = waechter.Schluessel
_MYPY_FEHLER = ": error: "


@dataclass(frozen=True)
class Befund:
    """Ein Befund eines Prüfwerkzeugs; verglichen wird je Datei und Code, ohne Zeile."""

    pfad: str
    zeile: int
    code: str
    text: str

    @property
    def schluessel(self) -> Schluessel:
        """Datei und Code, unter denen die Basis den Befund zählt."""
        return (self.pfad, self.code)


def neue_befunde(befunde: list[Befund], basis: Counter[Schluessel]) -> list[Befund]:
    """Gibt die Befunde der Schlüssel zurück, die öfter vorkommen als in der Basis."""
    ueber = set(waechter.ueber_basis(Counter(b.schluessel for b in befunde), basis))
    return [b for b in befunde if b.schluessel in ueber]


def gesenkte_basis(
    befunde: list[Befund], basis: Counter[Schluessel]
) -> Counter[Schluessel]:
    """Gibt die Basis zurück, in der kein Schlüssel öfter steht als heute gefunden."""
    return waechter.gesenkt(Counter(b.schluessel for b in befunde), basis)


def mypy_befunde(ausgabe: str) -> list[Befund]:
    """Liest die Fehlerzeilen von mypy; Hinweiszeilen zählen nicht."""
    befunde = []
    for zeile in ausgabe.splitlines():
        ort, trenner, rest = zeile.partition(_MYPY_FEHLER)
        if not trenner:
            continue
        pfad, _, nummer = ort.partition(":")
        text, _, code = rest.rpartition("  [")
        if not code.endswith("]"):
            text, code = rest, "ohne-code]"
        nummer = nummer.partition(":")[0]
        zeile_nr = int(nummer) if nummer.isdigit() else 0
        befunde.append(Befund(pfad, zeile_nr, code[:-1], text))
    return befunde
