"""Stufe 0: Eine neue oder geänderte Testfunktion muss etwas prüfen.

Verglichen wird mit dem Stand, von dem die Arbeit abzweigt (``merge-base`` mit
``origin/main``, ohne Ursprung ``HEAD``). Eine Testfunktion ohne ``assert``, ``raise``,
``pytest.raises``, ``pytest.fail``, ``pytest.warns`` oder einen Aufruf, dessen Name
``assert`` enthält, ist rot, wenn es sie dort nicht genau so gab. So wird ein geleerter
Rumpf nicht grün und ein Dummy nicht zum Ersatz für einen gelöschten roten Test.
"""

from __future__ import annotations

import ast
import subprocess
from pathlib import Path

PRUEF_AUFRUFE = frozenset({"raises", "fail", "warns", "deprecated_call"})
TESTDATEIEN = ("test_*.py", "*_test.py")


def _prueft(funktion: ast.AST) -> bool:
    for knoten in ast.walk(funktion):
        if isinstance(knoten, ast.Assert | ast.Raise):
            return True
        if isinstance(knoten, ast.Call):
            name = getattr(knoten.func, "attr", None) or getattr(knoten.func, "id", "")
            if name in PRUEF_AUFRUFE or "assert" in name.lower():
                return True
    return False


def _testfunktionen(text: str) -> dict[str, tuple[str, bool]]:
    """Name (mit Klasse), Syntaxbaum und Prüfung jeder Testfunktion der Datei."""
    try:
        baum = ast.parse(text)
    except SyntaxError:
        return {}
    funde: dict[str, tuple[str, bool]] = {}
    for knoten in baum.body:
        kinder = [knoten]
        if isinstance(knoten, ast.ClassDef) and knoten.name.startswith("Test"):
            kinder = [k for k in knoten.body if isinstance(k, ast.FunctionDef)]
        for kind in kinder:
            if isinstance(
                kind, ast.FunctionDef | ast.AsyncFunctionDef
            ) and kind.name.startswith("test"):
                vorsatz = f"{knoten.name}." if kind is not knoten else ""
                funde[vorsatz + kind.name] = (ast.dump(kind), _prueft(kind))
    return funde


def _git(wurzel: Path, *argumente: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *argumente], cwd=wurzel, capture_output=True, text=True, check=False
    )


def abzweig(wurzel: Path) -> str | None:
    """Der Commit, gegen den verglichen wird; ``None`` ohne Git-Verlauf."""
    basis = _git(wurzel, "merge-base", "HEAD", "origin/main")
    if basis.returncode:
        basis = _git(wurzel, "rev-parse", "HEAD")
    return basis.stdout.strip() if basis.returncode == 0 else None


def leere_tests(wurzel: Path) -> list[str]:
    """Rote Zeilen für neue oder geänderte Testfunktionen, die nichts prüfen."""
    commit = abzweig(wurzel)
    rot = []
    for muster in TESTDATEIEN:
        for datei in sorted((wurzel / "tests").rglob(muster)):
            if "__pycache__" in datei.parts:
                continue
            text = datei.read_text(encoding="utf-8", errors="replace")
            ohne = {
                name: baum
                for name, (baum, prueft) in _testfunktionen(text).items()
                if not prueft
            }
            if not ohne:
                continue
            pfad = datei.relative_to(wurzel).as_posix()
            alt = _git(wurzel, "show", f"{commit}:{pfad}") if commit else None
            vorher = _testfunktionen(alt.stdout) if alt and alt.returncode == 0 else {}
            rot += [
                f"{pfad}::{name} prüft nichts (kein assert, raise oder pytest.raises)"
                f" und ist neu oder geändert seit {(commit or 'Anfang')[:7]}"
                for name, baum in ohne.items()
                if vorher.get(name, ("", False))[0] != baum
            ]
    return rot
