"""Zaun um einen Auftrag: was ein Agent außerhalb seines Worktree-Inhalts schreibt.

Überwacht werden gitignorierte Dateien im Worktree (außer Caches und ``.venv``), das
``.venv`` des Hauptbaums, mit dem das Skript urteilt, und die Teile des Git-Ordners,
die Git-Befehle steuern. Verglichen wird die Signatur aus Modus, Größe, Inode und
ctime; ctime lässt sich ohne Änderung der Datei nicht zurücksetzen.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

FREI = (
    ".venv/",
    ".pruefleiter/",
    ".mypy_cache/",
    ".ruff_cache/",
    ".pytest_cache/",
    ".import_linter_cache/",
    "mutants/",
)
GIT_TEILE = ("config", "hooks", "info")
WORKTREE_TEILE = ("HEAD", "commondir", "gitdir", "config.worktree")


def _git(ort: Path, *argumente: str) -> str:
    umgebung = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    lauf = subprocess.run(
        ["git", *argumente], cwd=ort, env=umgebung, capture_output=True, check=True
    )
    return lauf.stdout.decode()


def _signaturen(pfad: Path, name: str) -> dict[str, str]:
    """Signatur je Datei unter ``pfad``; ein fehlender Pfad hat keine Einträge."""
    if pfad.is_symlink() or pfad.is_file():
        s = pfad.lstat()
        return {name: f"{s.st_mode:o},{s.st_size},{s.st_ino},{s.st_ctime_ns}"}
    ergebnis: dict[str, str] = {}
    if pfad.is_dir():
        for kind in sorted(pfad.iterdir()):
            ergebnis |= _signaturen(kind, f"{name}/{kind.name}")
    return ergebnis


def stand(wt: Path, haupt: Path) -> dict[str, str]:
    """Signaturen aller überwachten Dateien eines Auftrags."""
    roh = _git(wt, "ls-files", "-z", "--others", "--ignored", "--exclude-standard")
    ignoriert = [p for p in roh.split("\0") if p and not p.startswith(FREI)]
    ergebnis: dict[str, str] = {}
    for pfad in ignoriert:
        ergebnis |= _signaturen(wt / pfad, f"wt:{pfad}")
    ergebnis |= _signaturen(haupt / ".venv", "haupt:.venv")
    gemeinsam = Path(
        _git(wt, "rev-parse", "--path-format=absolute", "--git-common-dir").strip()
    )
    for teil in GIT_TEILE:
        ergebnis |= _signaturen(gemeinsam / teil, f"git:{teil}")
    eigen = Path(_git(wt, "rev-parse", "--path-format=absolute", "--git-dir").strip())
    for teil in WORKTREE_TEILE:
        ergebnis |= _signaturen(eigen / teil, f"git:worktree/{teil}")
    return ergebnis


def verletzt(vorher: dict[str, str], nachher: dict[str, str]) -> list[str]:
    """Überwachte Dateien, die seit ``vorher`` entstanden, fehlen oder anders sind."""
    return sorted(
        k for k in vorher.keys() | nachher.keys() if vorher.get(k) != nachher.get(k)
    )
