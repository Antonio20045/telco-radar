"""Meldet je geänderter Python-Datei, ob ihr Syntaxbaum zwischen zwei Ständen gleich ist.

Aufruf: ``python scripts/ast_gleich.py [ALT] [NEU]``; ohne NEU wird gegen den
Arbeitsbaum verglichen. Exit 0 nur, wenn mindestens eine Datei verglichen wurde und jede gleich ist.
"""

from __future__ import annotations

import ast
import inspect
import subprocess
import sys
from pathlib import Path

_DOCSTRING_TRAEGER = (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)


def _docstring_normalisiert(text: str) -> str:
    return "\n".join(zeile.rstrip() for zeile in inspect.cleandoc(text).splitlines())


def baum_dump(quelltext: str) -> str:
    """Gibt ``ast.dump`` mit normalisierten Docstrings zurück, wie sie der Formatierer umbricht."""
    baum = ast.parse(quelltext)
    for knoten in ast.walk(baum):
        if not isinstance(knoten, _DOCSTRING_TRAEGER) or not knoten.body:
            continue
        erster = knoten.body[0]
        if (
            isinstance(erster, ast.Expr)
            and isinstance(erster.value, ast.Constant)
            and isinstance(erster.value.value, str)
        ):
            erster.value.value = _docstring_normalisiert(erster.value.value)
    return ast.dump(baum)


def _git(wurzel: Path, *argumente: str) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(["git", *argumente], cwd=wurzel, capture_output=True)


def _inhalt(wurzel: Path, stand: str | None, pfad: str) -> str | None:
    if stand is None:
        datei = wurzel / pfad
        return datei.read_text(encoding="utf-8") if datei.exists() else None
    ergebnis = _git(wurzel, "show", f"{stand}:{pfad}")
    return ergebnis.stdout.decode("utf-8") if ergebnis.returncode == 0 else None


def vergleiche(alt: str, neu: str | None, wurzel: Path | None = None) -> dict[str, str]:
    """Ordnet jeder geänderten ``.py``-Datei ``gleich``, ``verschieden``, ``neu`` oder ``entfernt`` zu."""
    if wurzel is None:
        oben = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"], check=True, capture_output=True, text=True
        )
        wurzel = Path(oben.stdout.strip())
    bereich = [alt] if neu is None else [alt, neu]
    diff = _git(wurzel, "diff", "-z", "--no-renames", "--name-only", *bereich, "--", ":/*.py")
    diff.check_returncode()
    pfade = [pfad for pfad in diff.stdout.decode("utf-8").split("\0") if pfad]
    befund: dict[str, str] = {}
    for pfad in pfade:
        vorher, nachher = _inhalt(wurzel, alt, pfad), _inhalt(wurzel, neu, pfad)
        if vorher is None:
            befund[pfad] = "neu"
        elif nachher is None:
            befund[pfad] = "entfernt"
        elif baum_dump(vorher) == baum_dump(nachher):
            befund[pfad] = "gleich"
        else:
            befund[pfad] = "verschieden"
    return befund


def main(argumente: list[str]) -> int:
    alt = argumente[0] if argumente else "HEAD"
    neu = argumente[1] if len(argumente) > 1 else None
    befund = vergleiche(alt, neu)
    if not befund:
        print("Keine geänderte Python-Datei im Bereich; nichts nachgewiesen.")
        return 1
    for pfad, urteil in befund.items():
        print(f"{urteil:<11} {pfad}")
    abweichend = sum(urteil != "gleich" for urteil in befund.values())
    print(f"{len(befund)} Dateien, {len(befund) - abweichend} gleich, {abweichend} abweichend")
    return 1 if abweichend else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
