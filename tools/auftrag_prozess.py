"""Startet Programme eines Auftrags in eigener Sitzung und räumt sie danach ganz ab."""

from __future__ import annotations

import contextlib
import os
import shutil
import signal
import subprocess
import tempfile
from pathlib import Path


def ohne_git(extra: dict[str, str] | None = None) -> dict[str, str]:
    """Umgebung ohne ``GIT_*``-Variablen, ergänzt um ``extra``."""
    umgebung = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    return umgebung | (extra or {})


def starten(
    befehl: list[str],
    ort: Path,
    eingabe: str | None = None,
    umgebung: dict[str, str] | None = None,
    frist: float | None = None,
) -> subprocess.CompletedProcess[str]:
    """Führt ``befehl`` aus; danach endet jeder Prozess seiner Gruppe.

    Ein Hintergrundprozess, der in der Gruppe bleibt, kann so nach dem Ende nichts
    mehr ändern. Python schreibt keinen Bytecode und liest ihn nur aus einem leeren
    eigenen Ordner, nie aus einem ``__pycache__``, den ein Agent angelegt hat. Bei
    ``frist`` wirft der Aufruf ``subprocess.TimeoutExpired``.
    """
    bytecode = tempfile.mkdtemp(prefix="auftrag-pyc-")
    umgebung = (ohne_git() if umgebung is None else umgebung) | {
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONPYCACHEPREFIX": bytecode,
    }
    try:
        return _ausfuehren(befehl, ort, eingabe, umgebung, frist)
    finally:
        shutil.rmtree(bytecode, ignore_errors=True)


def _ausfuehren(
    befehl: list[str],
    ort: Path,
    eingabe: str | None,
    umgebung: dict[str, str],
    frist: float | None,
) -> subprocess.CompletedProcess[str]:
    with subprocess.Popen(
        befehl,
        cwd=ort,
        env=umgebung,
        stdin=subprocess.DEVNULL if eingabe is None else subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,
    ) as lauf:
        try:
            aus, fehler = lauf.communicate(eingabe, timeout=frist)
        finally:
            with contextlib.suppress(ProcessLookupError):
                os.killpg(lauf.pid, signal.SIGKILL)
    return subprocess.CompletedProcess(befehl, lauf.returncode, aus, fehler)


def leiter(
    wurzel: Path, ort: Path, art: str, basen: tuple[str, ...]
) -> tuple[int, str]:
    """Führt die Prüfleiter mit dem Python des Hauptbaums in ``ort`` aus.

    Außerhalb des Hauptbaums stehen die Basen danach wieder auf dem Commit, weil
    eine gesenkte Basis erst die Leiter auf ``main`` schreibt.
    """
    python = str(wurzel / ".venv/bin/python")
    lauf = starten([python, "scripts/pruefleiter.py", f"--{art}"], ort)
    if ort != wurzel:
        for basis in basen:
            starten(["git", "checkout", "-q", "--", basis], ort)
    return lauf.returncode, lauf.stdout + lauf.stderr
