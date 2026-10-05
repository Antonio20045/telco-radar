"""Urteil des Prüfers: liest seine Befunde und führt ihre Reproduktionen aus.

Ein Blocker zählt nur, wenn seine Reproduktion, genau ein pytest-Aufruf auf eine Datei
im Prüferordner, im Worktree an einer fachlichen Erwartung scheitert. Grün, ein Import-
oder Sammelfehler, eine Zeitüberschreitung oder eine fehlende Reproduktion verwirft ihn.
"""

from __future__ import annotations

import importlib
import json
import os
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

prozess_ = importlib.import_module("auftrag_prozess")

REPRODUKTION = re.compile(
    r"(?:\S*python3?(?:\.\d+)?\s+-m\s+)?pytest\s+(\S+\.py(?:::\S+)?)"
)
FACHLICH = re.compile(r"\bAssertionError\b|\bFailed: |^E\s+assert\b", re.MULTILINE)
TESTS_ROT = 1
BLOCKER = "blocker"
PRUEF_SEKUNDEN = 300
AUSGABE_ZEILEN = 30


@dataclass
class Urteil:
    """Gezählte Blocker mit Ausgabe und verworfene Befunde mit Grund."""

    gezaehlt: list[str] = field(default_factory=list)
    verworfen: list[str] = field(default_factory=list)
    unlesbar: str = ""

    @property
    def protokoll(self) -> str:
        """Befund und verworfene Befunde für die Protokolldatei des Laufs."""
        return "\n\n".join([self.befund, "Verworfen:", *self.verworfen])

    @property
    def befund(self) -> str:
        """Der Befund für die nächste Bau-Runde; leer heißt bestanden."""
        if self.unlesbar:
            return f"Prüfer ohne lesbares Urteil: {self.unlesbar}"
        if not self.gezaehlt:
            return ""
        kopf = f"Prüfer: {len(self.gezaehlt)} Blocker mit scheiternder Reproduktion"
        return "\n\n".join([kopf, *self.gezaehlt])


def befunde(bericht: object) -> list[dict] | str:
    """Liest die Befundliste aus dem Agentenbericht; ein Text nennt, was fehlt."""
    text = bericht.get("result") if isinstance(bericht, dict) else None
    if not isinstance(text, str):
        return "kein Feld result im Bericht"
    try:
        daten = json.loads(text[text.find("{") : text.rfind("}") + 1])
    except ValueError as fehler:
        return f"kein JSON ({fehler})"
    liste = daten.get("befunde") if isinstance(daten, dict) else None
    if not isinstance(liste, list) or not all(isinstance(b, dict) for b in liste):
        return "befunde ist keine Liste von Objekten"
    return liste


def _ziel(reproduktion: object, ordner: Path) -> str | None:
    if not isinstance(reproduktion, str):
        return None
    treffer = REPRODUKTION.fullmatch(reproduktion.strip())
    if not treffer:
        return None
    datei = Path(treffer.group(1).split("::")[0])
    echt = Path(os.path.realpath(datei))
    innen = echt.is_relative_to(os.path.realpath(ordner)) and echt.is_file()
    return treffer.group(1) if datei.is_absolute() and innen else None


def reproduzieren(
    ziel: str, ordner: Path, wt: Path, haupt: Path | None = None
) -> tuple[bool, str]:
    """Führt eine Reproduktion im Worktree aus; wahr heißt fachlich gescheitert.

    Das Python kommt aus dem ``.venv`` von ``haupt``, standardmäßig ``wt``.
    """
    python = str((wt if haupt is None else haupt) / ".venv/bin/python")
    befehl = [python, "-m", "pytest", "-q", "--tb=short", "-p", "no:cacheprovider"]
    umgebung = prozess_.ohne_git({"PYTHONPATH": str(wt / "src")})
    try:
        lauf = prozess_.starten(
            [*befehl, "--rootdir", str(ordner), ziel],
            wt,
            None,
            umgebung,
            PRUEF_SEKUNDEN,
        )
    except subprocess.TimeoutExpired:
        return False, f"Zeitüberschreitung nach {PRUEF_SEKUNDEN} s"
    ausgabe = "\n".join(
        (lauf.stdout + lauf.stderr).strip().splitlines()[-AUSGABE_ZEILEN:]
    )
    if lauf.returncode == TESTS_ROT and FACHLICH.search(ausgabe):
        return True, ausgabe
    grund = (
        "grün"
        if lauf.returncode == 0
        else f"Exit {lauf.returncode}, kein fachliches Scheitern"
    )
    return False, f"{grund}\n{ausgabe}"


def urteilen(
    bericht: object, ordner: Path, wt: Path, haupt: Path | None = None
) -> Urteil:
    """Zählt die Blocker des Prüfers, deren Reproduktion fachlich scheitert."""
    urteil = Urteil()
    liste = befunde(bericht)
    if isinstance(liste, str):
        urteil.unlesbar = liste
        return urteil
    for befund in liste:
        name = f"{befund.get('datei_zeile', '?')}: {befund.get('beschreibung', '')}"
        if befund.get("schwere") != BLOCKER:
            urteil.verworfen.append(f"{name} (kein Blocker)")
            continue
        ziel = _ziel(befund.get("reproduktion"), ordner)
        if ziel is None:
            urteil.verworfen.append(f"{name} (ohne Reproduktion im Prüferordner)")
            continue
        gescheitert, ausgabe = reproduzieren(ziel, ordner, wt, haupt)
        if gescheitert:
            urteil.gezaehlt.append(f"{name}\nReproduktion: {ziel}\n{ausgabe}")
        else:
            urteil.verworfen.append(f"{name} (Reproduktion {ausgabe.splitlines()[0]})")
    return urteil
