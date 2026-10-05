"""Goldener Lauf eines Auftrags: bei ``verhalten`` neue Seiten, sonst unberührt.

Ein Verhaltensauftrag ändert Seiten gewollt. Nach grüner Abnahme schreibt
``scripts/golden_aufnehmen.py --seiten-neu`` im Worktree ``erwartet.json`` aus zwei
Wiedergaben der bestehenden Aufnahme neu; die Bänder bleiben, wie sie sind. Vorher
steht die Aufnahme wieder auf dem Startcommit, sodass nichts vom Bauagenten bleibt.
"""

from __future__ import annotations

import importlib
import json
from pathlib import Path
from typing import Any

prozess_ = importlib.import_module("auftrag_prozess")
git_ = importlib.import_module("auftrag_git")

GOLDEN = "tests/fixtures/golden"
SKRIPT = "scripts/golden_aufnehmen.py"
NEU = ("erwartet.json", "_herkunft.json")
AUSGABE_ZEILEN = 40
PROTOKOLL = "goldener-lauf.txt"
KOPF = "Seiten neu im goldenen Lauf:"


def aufnahme(ort: Path) -> str | None:
    """Relativer Pfad der jüngsten Aufnahme oder ``None``, wenn es keine gibt."""
    ordner = ort / GOLDEN
    tage = sorted(p for p in ordner.iterdir() if p.is_dir()) if ordner.is_dir() else []
    return tage[-1].relative_to(ort).as_posix() if tage else None


def erlaubt(ort: Path) -> set[str]:
    """Die Dateien, die ``--seiten-neu`` schreiben darf."""
    relativ = aufnahme(ort)
    return {f"{relativ}/{name}" for name in NEU} if relativ else set()


def seiten_neu(wurzel: Path, ort: Path, start: str) -> tuple[str, list[str]]:
    """Befund oder ``""`` und die geänderten Seiten der jüngsten Aufnahme."""
    relativ = aufnahme(ort)
    if relativ is None:
        return "", []
    prozess_.starten(["git", "checkout", "-q", start, "--", relativ], ort)
    prozess_.starten(["git", "clean", "-fdq", "--", relativ], ort)
    python = str(wurzel / ".venv/bin/python")
    umgebung = prozess_.ohne_git({"PYTHONPATH": "src"})
    lauf = prozess_.starten(
        [python, SKRIPT, "--seiten-neu", relativ], ort, None, umgebung
    )
    ausgabe = (lauf.stdout + lauf.stderr).strip().splitlines()
    if lauf.returncode:
        rest = "\n".join(ausgabe[-AUSGABE_ZEILEN:])
        return f"goldener Lauf rot (Exit {lauf.returncode})\n{rest}", []
    geaendert = prozess_.starten(
        ["git", "status", "--porcelain", "-z", "--", relativ], ort
    ).stdout
    pfade = {e[3:] for e in geaendert.split("\0") if e}
    if fremd := sorted(pfade - erlaubt(ort)):
        return f"goldener Lauf änderte {', '.join(fremd)}", []
    return "", json.loads(lauf.stdout.strip().splitlines()[-1])


def frei(lauf: Any, rolle: str) -> set[str]:
    """Was der goldene Lauf eines Verhaltensauftrags im Bau schreiben darf."""
    verhalten = lauf.auftrag["art"] == "verhalten" and rolle == "bau"
    return erlaubt(lauf.wt) if verhalten else set()


def ohne_frei(lauf: Any, rolle: str, pfade: list[str]) -> list[str]:
    """``pfade`` ohne die, die der goldene Lauf im Bau schreiben darf."""
    schreibbar = frei(lauf, rolle)
    return [p for p in pfade if p not in schreibbar]


def fuer_auftrag(lauf: Any, geprueft: dict[str, str]) -> str:
    """Nur bei ``verhalten``: neue Seiten, Protokoll im Laufordner, sonst ``""``.

    Die geschriebenen Dateien kommen mit ihrem Blob in ``geprueft`` und so in den
    Auftragscommit.
    """
    schreibbar = frei(lauf, "bau")
    if not schreibbar:
        return ""
    befund, seiten = seiten_neu(lauf.wurzel, lauf.wt, lauf.start)
    lauf.datei(PROTOKOLL).write_text("".join(f"{s}\n" for s in seiten), "utf-8")
    geprueft |= git_.blobs(lauf.wt, sorted(schreibbar))
    return befund


def titel(protokoll: Path) -> str:
    """Zusatz zur Commit-Nachricht mit den neuen Seiten, sonst ``""``."""
    seiten = protokoll.read_text("utf-8").split() if protokoll.is_file() else []
    return f"\n\n{KOPF}\n" + "\n".join(seiten) if seiten else ""
