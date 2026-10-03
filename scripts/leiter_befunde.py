"""Befunde der Prüfwerkzeuge, gezählt je Datei und Code ohne Zeile."""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

import waechter

Schluessel = waechter.Schluessel
_MYPY_FEHLER = ": error: "
WURZEL = Path(__file__).resolve().parents[1]


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


@dataclass
class Ergebnis:
    """Ausgang einer Stufe: grün oder rot mit den Zeilen, die Rot begründen."""

    stufe: str
    gruen: bool
    zeilen: list[str] = field(default_factory=list)
    gesenkt: list[str] = field(default_factory=list)
    angehoben: list[str] = field(default_factory=list)
    hinweise: list[str] = field(default_factory=list)
    sekunden: float = 0.0


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


def ruff_befunde(ausgabe: str) -> list[Befund]:
    """Liest ``ruff check --output-format json`` in Befunde mit relativen Pfaden."""
    return [
        Befund(
            _relativ(eintrag["filename"]),
            eintrag["location"]["row"],
            eintrag["code"] or "syntax",
            eintrag["message"],
        )
        for eintrag in json.loads(ausgabe)
    ]


def _relativ(pfad: str) -> str:
    datei = Path(pfad)
    return str(datei.relative_to(WURZEL)) if datei.is_relative_to(WURZEL) else pfad


def rote_zeilen(ausgabe: str) -> list[str]:
    """Gibt die Kurzzeilen ``FAILED``/``ERROR`` aus der Zusammenfassung von pytest."""
    return [z for z in ausgabe.splitlines() if z.startswith(("FAILED ", "ERROR "))]
