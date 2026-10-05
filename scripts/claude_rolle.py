"""Rollen der Auftragsagenten: wohin eine Rolle schreiben darf, für Hook und Skript.

``tools/auftrag.py`` startet jeden Agenten mit ``TELCO_ROLLE`` und ``claude --settings``
aus ``einstellungen``; diese Datei ist dann sein PreToolUse-Hook für Bash und jedes
Schreibwerkzeug und endet mit Exit 2 und Begründung, wenn die Rolle dort nicht schreiben
darf. Dieselbe Regel ``verstoss`` hält das Skript nach jeder Runde gegen den Git-Stand.
Außerhalb des Repos schreibt eine Rolle nur in den Temp-Ordner, nie neben das Repo.
Ohne Rolle lässt der Hook alles durch, was die deny-Liste erlaubt.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path

from claude_rolle_shell import (
    AWK,
    ERLAUBT,
    FIND_STARTET,
    PYTHON,
    SHELLS,
    VARIABLEN,
    einfache_befehle,
    git_sperre,
    ohne_vorsatz,
    python_sperre,
    schreibziele,
)

BLOCKIERT = 2
ROLLEN = ("test", "bau", "pruefer", "entwurf", "suchen")
TESTS = "tests/"
BEREICH_WURZEL = "src/telco_radar/"
ENTWURF = "outputs/auftraege/"
NIE_NEU = frozenset(
    {
        "conftest.py",
        "__init__.py",
        "pytest.ini",
        "tox.ini",
        "setup.cfg",
        "pyproject.toml",
    }
)
REGEL = {
    "test": "nur neue Dateien unter tests/ und die Abnahme",
    "bau": "nur der Bereich des Auftrags und neue Dateien unter tests/",
    "pruefer": "nur der eigene Ordner aus TELCO_PRUEFER_ORDNER",
    "entwurf": f"nur {ENTWURF}",
    "suchen": "nichts",
}
SCHREIBWERKZEUGE = frozenset({"Edit", "Write", "MultiEdit", "NotebookEdit"})
UNBERECHENBAR = frozenset({"eval", "source", ".", "exec"})
GIT_SPERREN = tuple(
    f"Bash(git {befehl}*)"
    for befehl in (
        "add",
        "apply",
        "checkout",
        "clean",
        "commit",
        "merge",
        "mv",
        "push",
        "rebase",
        "reset",
        "restore",
        "rm",
        "stash",
        "switch",
    )
)


@dataclass(frozen=True)
class Ziel:
    """Was eine Rolle in einem Auftrag schreiben darf."""

    rolle: str
    bereich: str | None = None
    abnahme: str | None = None
    pruefer: Path | None = None


def ziel_aus_umgebung(umgebung: Mapping[str, str]) -> Ziel | None:
    """Liest Rolle, Bereich, Abnahme und Prüferordner; ohne Rolle ``None``."""
    rolle = umgebung.get("TELCO_ROLLE")
    if not rolle:
        return None
    auftrag: dict = {}
    if datei := umgebung.get("TELCO_AUFTRAG"):
        try:
            auftrag = json.loads(Path(datei).read_text("utf-8"))
        except (OSError, ValueError):
            auftrag = {}
    ordner = umgebung.get("TELCO_PRUEFER_ORDNER")
    return Ziel(
        rolle,
        auftrag.get("bereich") if isinstance(auftrag, dict) else None,
        auftrag.get("abnahme") if isinstance(auftrag, dict) else None,
        Path(ordner) if ordner else None,
    )


def verstoss(ziel: Ziel, wurzel: Path, pfad: Path, neu: bool) -> str | None:
    """Gibt den Grund, warum die Rolle ``pfad`` nicht schreiben darf, sonst ``None``.

    ``neu`` heißt: Die Datei gab es im letzten Commit nicht.
    """
    absolut = Path(os.path.realpath(pfad if pfad.is_absolute() else wurzel / pfad))
    if ziel.rolle not in ROLLEN:
        return f"Rolle {ziel.rolle} ist unbekannt; erlaubt sind {', '.join(ROLLEN)}"
    regel = f"Rolle {ziel.rolle} darf {absolut} nicht ändern ({REGEL[ziel.rolle]})"
    if ziel.rolle == "pruefer":
        ordner = Path(os.path.realpath(ziel.pruefer)) if ziel.pruefer else None
        return None if ordner and absolut.is_relative_to(ordner) else regel
    try:
        relativ = absolut.relative_to(os.path.realpath(wurzel)).as_posix()
    except ValueError:
        neben = absolut.is_relative_to(os.path.realpath(wurzel.parent))
        frei = absolut.is_relative_to(os.path.realpath(tempfile.gettempdir()))
        return None if frei and not neben and ziel.rolle != "suchen" else regel
    neuer_test = neu and relativ.startswith(TESTS) and absolut.name not in NIE_NEU
    erlaubt = {
        "test": neuer_test or relativ == ziel.abnahme,
        "bau": neuer_test or im_bereich(relativ, ziel.bereich or ""),
        "entwurf": relativ.startswith(ENTWURF),
        "suchen": False,
    }[ziel.rolle]
    return None if erlaubt else regel.replace(str(absolut), relativ)


def im_bereich(relativ: str, bereich: str) -> bool:
    """Wahr, wenn ``relativ`` im Bereich liegt: einem Unterordner mit ``/`` oder
    genau einem Modul ``.py`` unter ``src/telco_radar/``."""
    if not bereich.startswith(BEREICH_WURZEL) or bereich == BEREICH_WURZEL:
        return False
    if bereich.endswith("/"):
        return relativ.startswith(bereich)
    return bereich.endswith(".py") and relativ == bereich


def ist_neu(wurzel: Path, pfad: Path) -> bool:
    """Wahr, wenn ``pfad`` im letzten Commit von ``wurzel`` fehlt."""
    try:
        relativ = Path(os.path.realpath(wurzel / pfad)).relative_to(
            os.path.realpath(wurzel)
        )
    except ValueError:
        return True
    lauf = subprocess.run(
        ["git", "cat-file", "-e", f"HEAD:{relativ.as_posix()}"],
        cwd=wurzel,
        capture_output=True,
        check=False,
    )
    return lauf.returncode != 0


def befehl_verstoss(
    ziel: Ziel,
    wurzel: Path,
    ort: Path,
    text: str,
    neu: Callable[[Path, Path], bool] = ist_neu,
) -> str | None:
    """PreToolUse Bash einer Rolle: kein schreibendes Git, kein Schreiben außerhalb
    der Rolle über Umleitung, Dateibefehl oder eingebetteten Interpretercode."""
    if "`" in text or "$(" in text or "<(" in text or ">(" in text:
        return f"Rolle {ziel.rolle}: Befehlsersetzung ist gesperrt; schreib sie aus"
    for roh, streng in einfache_befehle(text):
        befehl, variablen = ohne_vorsatz(roh)
        if fremd := [v for v in variablen if streng and v not in VARIABLEN]:
            return f"Rolle {ziel.rolle}: die Variable {fremd[0]} ist gesperrt"
        grund = befehl and _befehl_sperre(ziel, wurzel, ort, befehl, text, neu, streng)
        if grund:
            return grund
    return None


def _befehl_sperre(
    ziel: Ziel,
    wurzel: Path,
    ort: Path,
    befehl: list[str],
    text: str,
    neu: Callable[[Path, Path], bool],
    streng: bool,
) -> str | None:
    name = Path(befehl[0]).name
    if name in UNBERECHENBAR or any(z in befehl[0] for z in "$`"):
        return (
            f"Rolle {ziel.rolle}: ein Befehl aus Variable, Ersetzung oder eval"
            " ist gesperrt; schreib ihn aus"
        )
    if streng and name not in ERLAUBT and not PYTHON.match(name):
        return f"Rolle {ziel.rolle}: der Befehl {name} ist für Rollen nicht frei"
    if name == "git" and (gesperrt := git_sperre(befehl[1:])):
        return f"Rolle {ziel.rolle}: {gesperrt} führt nur tools/auftrag.py aus"
    if name in AWK and any(z in w for w in befehl[1:] for z in (">", "|", "system")):
        return f"Rolle {ziel.rolle}: awk mit Umleitung, Pipe oder system ist gesperrt"
    if name == "find" and FIND_STARTET & set(befehl[1:]):
        return f"Rolle {ziel.rolle}: find startet keine Befehle"
    shell_ohne_c = name in SHELLS and "-c" not in befehl[1:]
    if shell_ohne_c or (
        PYTHON.match(name) and python_sperre(wurzel, ort, befehl[1:], text, neu)
    ):
        return (
            f"Rolle {ziel.rolle}: {name} nur mit festen Modulen, Repo-Skripten oder"
            " eingebettetem Code ohne Schreiben; schreib mit Edit oder Write"
        )
    for pfad in schreibziele(befehl):
        ziel_pfad = Path(pfad) if Path(pfad).is_absolute() else ort / pfad
        if grund := verstoss(ziel, wurzel, ziel_pfad, neu(wurzel, ziel_pfad)):
            return grund
    return None


def einstellungen(rolle: str) -> dict:
    """Die Einstellungen für ``claude --settings`` einer Rolle."""
    hook = 'python3 "$CLAUDE_PROJECT_DIR"/scripts/claude_rolle.py'
    werkzeuge = "Bash|" + "|".join(sorted(SCHREIBWERKZEUGE))
    eintrag = {"type": "command", "command": hook, "timeout": 10}
    return {
        "env": {"TELCO_ROLLE": rolle},
        "permissions": {"deny": list(GIT_SPERREN)},
        "hooks": {"PreToolUse": [{"matcher": werkzeuge, "hooks": [eintrag]}]},
    }


def _wurzel(ort: Path) -> Path:
    lauf = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        cwd=ort,
        capture_output=True,
        text=True,
        check=False,
    )
    return Path(lauf.stdout.strip()) if lauf.returncode == 0 else ort


def pruefe(ereignis: dict, umgebung: Mapping[str, str]) -> str | None:
    """Urteil über ein PreToolUse-Ereignis; ``None`` lässt das Werkzeug laufen."""
    ziel = ziel_aus_umgebung(umgebung)
    if ziel is None:
        return None
    ort = Path(str(ereignis.get("cwd") or Path.cwd()))
    wurzel = _wurzel(ort)
    werkzeug, eingabe = ereignis.get("tool_name"), ereignis.get("tool_input") or {}
    if werkzeug == "Bash":
        return befehl_verstoss(ziel, wurzel, ort, str(eingabe.get("command", "")))
    if werkzeug in SCHREIBWERKZEUGE:
        roh = eingabe.get("file_path") or eingabe.get("notebook_path") or ""
        pfad = Path(str(roh)) if Path(str(roh)).is_absolute() else ort / str(roh)
        return verstoss(ziel, wurzel, pfad, ist_neu(wurzel, pfad))
    return None


def main(
    lesen: Callable[[], str] = sys.stdin.read,
    umgebung: Mapping[str, str] = os.environ,
) -> int:
    """Liest das Ereignis von stdin; Exit 2 mit Begründung auf stderr blockiert."""
    try:
        ereignis = json.loads(lesen() or "{}")
        ereignis = ereignis if isinstance(ereignis, dict) else {}
        grund = pruefe(ereignis, umgebung)
    except (ValueError, OSError, TypeError, AttributeError) as fehler:
        name = type(fehler).__name__
        print(
            f"Rollen-Hook gescheitert, also gesperrt: {name}: {fehler}", file=sys.stderr
        )
        return BLOCKIERT
    if grund:
        print(grund, file=sys.stderr)
        return BLOCKIERT
    return 0


if __name__ == "__main__":
    sys.exit(main())
