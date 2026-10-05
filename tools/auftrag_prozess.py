"""Startet Programme eines Auftrags in eigener Sitzung und räumt sie danach ganz ab."""

from __future__ import annotations

import contextlib
import os
import signal
import subprocess
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
    mehr ändern. Bei ``frist`` wirft der Aufruf ``subprocess.TimeoutExpired``.
    """
    with subprocess.Popen(
        befehl,
        cwd=ort,
        env=ohne_git() if umgebung is None else umgebung,
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
