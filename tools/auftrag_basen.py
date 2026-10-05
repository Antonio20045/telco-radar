"""Basen und Vertragsausnahmen im Worktree eines Auftrags.

Startet ein Agent die Leiter selbst, senkt sie Basen unter ``pruef/`` und streicht
verwaiste Ausnahmen in ``.importlinter``. Das ist keine Änderung des Agenten: Die
Leiter auf ``main`` senkt nach dem Merge dasselbe. Was nur strenger wurde, steht
danach wieder auf dem Startcommit; jede Lockerung bleibt ein Befund.
"""

from __future__ import annotations

import importlib
from pathlib import Path

waechter = importlib.import_module("waechter")
prozess_ = importlib.import_module("auftrag_prozess")

BASEN = ("pruef/", ".importlinter")


def _am_start(ort: Path, start: str, pfad: str) -> str | None:
    lauf = prozess_.starten(["git", "show", f"{start}:{pfad}"], ort)
    return lauf.stdout if lauf.returncode == 0 else None


def bereinigen(ort: Path, start: str, pfade: list[str]) -> tuple[list[str], list[str]]:
    """Übrige Pfade und Lockerungen; nur gesenkte Basen stehen wieder auf ``start``."""
    rest: list[str] = []
    lockerer: list[str] = []
    for pfad in pfade:
        vergleich = waechter.LISTEN.get(pfad)
        alt = _am_start(ort, start, pfad) if vergleich else None
        if vergleich is None or alt is None or not pfad.startswith(BASEN):
            rest.append(pfad)
            continue
        datei = ort / pfad
        neu = datei.read_text(encoding="utf-8") if datei.is_file() else ""
        if zeilen := vergleich(alt, neu):
            lockerer += [f"{pfad} lockerer: {zeile}" for zeile in zeilen]
            continue
        prozess_.starten(["git", "checkout", "-q", start, "--", pfad], ort)
    return rest, lockerer
