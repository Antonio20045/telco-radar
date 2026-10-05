"""Stufe 3: verwaiste Ausnahmen in ``.importlinter`` streicht die Leiter selbst.

``lint-imports`` meldet eine Ausnahme, deren Import es nicht mehr gibt, als Fehler
(„No matches for ignored import …“). Die Leiter streicht genau diese Zeilen aus
``ignore_imports`` und prüft erneut, so wie Stufe 1 und 2 ihre Basen senken. Sie fügt
nie eine Zeile hinzu und ändert sonst nichts an den Verträgen.
"""

from __future__ import annotations

import re
import subprocess
from collections.abc import Callable
from pathlib import Path

VERWAIST = re.compile(r"^No matches for ignored import\s+(\S+)\s+->\s+(\S+?)\.?$", re.M)
AUSNAHMEN = "ignore_imports"


def verwaiste_ausnahmen(ausgabe: str) -> list[str]:
    """Liest aus der Ausgabe von ``lint-imports`` jede Ausnahme ohne Treffer."""
    return [f"{quelle} -> {ziel}" for quelle, ziel in VERWAIST.findall(ausgabe)]


def streiche(text: str, ausnahmen: list[str]) -> tuple[str, list[str]]:
    """Entfernt die genannten Zeilen aus jedem ``ignore_imports``; sonst nichts.

    Gibt den neuen Text und die tatsächlich entfernten Ausnahmen zurück.
    """
    weg = {_normal(a) for a in ausnahmen}
    zeilen, entfernt, schluessel = [], [], None
    for zeile in text.splitlines(keepends=True):
        eingerueckt = zeile[:1] in (" ", "\t")
        if not eingerueckt and zeile.strip():
            schluessel = zeile.partition("=")[0].strip()
        if eingerueckt and schluessel == AUSNAHMEN and _normal(zeile) in weg:
            entfernt.append(_normal(zeile))
            continue
        zeilen.append(zeile)
    return "".join(zeilen), entfernt


def senke(
    pfad: Path, pruefen: Callable[[], subprocess.CompletedProcess[str]]
) -> tuple[subprocess.CompletedProcess[str], list[str]]:
    """Prüft, streicht verwaiste Ausnahmen und prüft erneut, bis keine mehr kommt.

    Jeder Durchgang streicht mindestens eine Zeile, sonst endet er mit dem letzten
    Lauf; so endet die Schleife spätestens, wenn keine Ausnahme mehr steht.
    """
    gestrichen: list[str] = []
    lauf = pruefen()
    while lauf.returncode and (
        verwaist := verwaiste_ausnahmen(lauf.stdout + lauf.stderr)
    ):
        alt = pfad.read_text(encoding="utf-8")
        neu, entfernt = streiche(alt, verwaist)
        if not entfernt:
            break
        pfad.write_text(neu, encoding="utf-8")
        gestrichen += entfernt
        lauf = pruefen()
    return lauf, gestrichen


def _normal(zeile: str) -> str:
    quelle, _, ziel = zeile.partition("->")
    return f"{quelle.strip()} -> {ziel.strip()}"
