"""Stufe 5 im pre-push: nur die Testdateien, die der Push berührt.

Antonio 26.10.2026 („Feedback-Schleife zu lang“): der Volllauf vor jedem Push
dauerte 25 bis 40 Minuten. Jetzt laufen vor dem Push die ganzen Testdateien,
die eine Änderung gegen ``origin/main`` betrifft (Auswahl wie Stufe 4, ohne
Kappe und ohne Abwahl langsamer Tests). Betrifft die Änderung alle Tests
(``config/``, ``conftest.py``, Abhängigkeiten), läuft die volle Suite. Der
Volllauf aller Tests kommt sonst nachts über ``ci.yml``; nur er stempelt.
"""

from __future__ import annotations

import subprocess
import sys
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import TextIO

import leiter_schnell
import pruefstempel
from leiter_befunde import Ergebnis

STUFE = "5 Push"
Lauf = Callable[
    [TextIO, list[str], Mapping[str, str]], subprocess.CompletedProcess[str]
]


def geaendert(wurzel: Path) -> list[str]:
    """Die Dateien, in denen sich HEAD von ``origin/main`` unterscheidet."""
    return pruefstempel.git(wurzel, "diff", "--name-only", "origin/main...HEAD").split()


def stufe(
    log: TextIO,
    wurzel: Path,
    lauf: Lauf,
    voll: Callable[[TextIO], Ergebnis],
    frist: int,
) -> Ergebnis:
    """Fährt die betroffenen Testdateien; ``voll`` bei einer Änderung für alle."""
    auswahl = leiter_schnell.betroffene(wurzel, geaendert(wurzel))
    if auswahl.alle:
        return voll(log)
    if not auswahl.dateien:
        return Ergebnis(STUFE, True, hinweise=["keine betroffenen Tests"])
    befehl = [sys.executable, "-m", "pytest", "-q", "-n", "auto", "-rfE"]
    befehl += [f"--timeout={frist}", *auswahl.dateien]
    ergebnis = lauf(log, befehl, {"PYTHONPATH": str(wurzel / "src"), "COLUMNS": "1000"})
    if ergebnis.returncode in (0, 5):
        return Ergebnis(STUFE, True, hinweise=[f"{len(auswahl.dateien)} Testdateien"])
    ende = ergebnis.stdout.splitlines()[-30:] + ergebnis.stderr.splitlines()[-10:]
    return Ergebnis(STUFE, False, [f"pytest endet mit {ergebnis.returncode}:", *ende])
