"""Mutationsprobe mit mutmut auf den Funktionen, die ein Auftrag geändert hat.

Die Probe läuft in einem Wegwerf-Worktree des Auftragsstands. Sie liefert eine Zeit
und das Verhältnis erkannter Mutanten oder, wenn sie nicht laufen kann, den Grund.
Eine gescheiterte Probe hält keinen Auftrag auf; die Prüfung fällt dann weg.
"""

from __future__ import annotations

import ast
import importlib
import os
import re
import subprocess
import sys
import tempfile
import time
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

WURZEL = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(WURZEL / "scripts"))
leiter_schnell = importlib.import_module("leiter_schnell")

FRIST = 900
QUELLE = "src/"
TRENNER = "ǁ"
ERKANNT = {"killed", "timeout", "caught by type check", "segfault"}
UEBERLEBT = {"survived", "no tests"}
OHNE_MARKER = "not browser and not langsam and not golden and not netz"
GENANNT = 5
NICHT_KOPIEREN = {"src", "tests", "data", "site", "mutants"}
HUNK = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@", re.MULTILINE)
ERGEBNIS = re.compile(r"^\s*(\S+): (.+?)\s*$", re.MULTILINE)


@dataclass(frozen=True)
class Probe:
    """Ergebnis der Probe für die Kostenzeile: Exit-Code, Sekunden, Text."""

    exit: int | str
    sekunden: float
    ergebnis: str

    def spalten(self) -> dict[str, object]:
        """Gibt die Felder der Kostenzeile außer dem Exit-Code."""
        return {"sekunden": self.sekunden, "ergebnis": self.ergebnis}


def neue_zeilen(diff: str) -> set[int]:
    """Gibt die Zeilen der neuen Fassung, die ein ``-U0``-Diff berührt."""
    zeilen: set[int] = set()
    for treffer in HUNK.finditer(diff):
        start, anzahl = int(treffer[1]), int(treffer[2] or 1)
        zeilen |= set(range(start, start + max(anzahl, 1)))
    return zeilen


def funktionen(quelltext: str, zeilen: set[int]) -> list[str]:
    """Gibt die mutmut-Namen der Funktionen und Methoden, die eine Zeile berühren."""
    namen: list[str] = []
    for knoten in ast.parse(quelltext).body:
        kandidaten = [(knoten, "x_")]
        if isinstance(knoten, ast.ClassDef):
            praefix = f"x{TRENNER}{knoten.name}{TRENNER}"
            kandidaten = [(k, praefix) for k in knoten.body]
        for kandidat, praefix in kandidaten:
            if not isinstance(kandidat, ast.FunctionDef | ast.AsyncFunctionDef):
                continue
            anfang = min(
                [kandidat.lineno, *(d.lineno for d in kandidat.decorator_list)]
            )
            if zeilen & set(range(anfang, (kandidat.end_lineno or anfang) + 1)):
                namen.append(praefix + kandidat.name)
    return namen


def geaenderte_funktionen(ort: Path, basis: str) -> dict[str, list[str]]:
    """Ordnet jeder geänderten Datei unter ``src/`` die Muster ihrer Mutanten zu."""
    befehl = ["git", "diff", "--no-renames", "--name-only", "-z", basis, "HEAD"]
    dateien = _git(ort, befehl).split("\0")
    muster: dict[str, list[str]] = {}
    for datei in dateien:
        if not (datei.startswith(QUELLE) and datei.endswith(".py")):
            continue
        if not (ort / datei).is_file():
            continue
        diff = _git(
            ort, ["git", "diff", "-U0", "--no-renames", basis, "HEAD", "--", datei]
        )
        namen = funktionen((ort / datei).read_text("utf-8"), neue_zeilen(diff))
        modul = sorted(leiter_schnell.modulnamen(datei))[0]
        if namen:
            muster[datei] = [f"{modul}.{name}__mutmut_*" for name in namen]
    return muster


def einstellungen(dateien: list[str], tests: list[str], kopien: list[str]) -> str:
    """Schreibt den Abschnitt ``[mutmut]`` für ``setup.cfg`` des Wegwerf-Worktrees."""
    argumente = ["-n", "0", "-p", "no:cacheprovider", "-m", OHNE_MARKER]
    zeilen = ["[mutmut]", "source_paths=src", "also_copy="]
    zeilen += [f"  {k}" for k in kopien] + ["only_mutate="]
    zeilen += [f"  {d}" for d in dateien]
    zeilen += ["pytest_add_cli_args_test_selection="] + [f"  {t}" for t in tests]
    zeilen += ["pytest_add_cli_args="] + [f"  {a}" for a in argumente]
    return "\n".join(zeilen) + "\n"


def auszaehlen(ausgabe: str, muster: list[str]) -> tuple[Counter[str], list[str]]:
    """Zählt Zustände der gewählten Mutanten; nennt fremde, die mutmut prüfte."""
    praefixe = [m.removesuffix("*") for m in muster]
    zustaende: Counter[str] = Counter()
    fremd: list[str] = []
    for name, zustand in ERGEBNIS.findall(ausgabe):
        if any(name.startswith(p) for p in praefixe):
            zustaende[zustand] += 1
        elif zustand != "not checked":
            fremd.append(name)
    return zustaende, fremd


def urteil(zustaende: Counter[str], fremd: list[str], ausgabe: str) -> str:
    """Fasst die gezählten Zustände zu einem Ergebnis oder einem Grund zusammen."""
    if fremd:
        return f"entfällt: mutmut prüfte nicht gewählte Mutanten ({fremd[0]} …)"
    gesamt = sum(zustaende.values())
    if not gesamt:
        return "entfällt: mutmut erzeugte für die geänderten Funktionen keine Mutanten"
    offen = set(zustaende) - ERKANNT - UEBERLEBT
    if offen:
        return f"entfällt: Mutanten ohne Ergebnis ({', '.join(sorted(offen))})"
    erkannt = sum(n for z, n in zustaende.items() if z in ERKANNT)
    text = f"{erkannt} von {gesamt} Mutanten erkannt"
    if erkannt < gesamt:
        namen = [
            kurzname(name)
            for name, zustand in ERGEBNIS.findall(ausgabe)
            if zustand in UEBERLEBT
        ]
        mehr = " …" if len(namen) > GENANNT else ""
        text += f", überlebt: {' '.join(namen[:GENANNT])}{mehr}"
    return text


def kurzname(mutant: str) -> str:
    """Kürzt ``modul.xǁKlasseǁname__mutmut_3`` zu ``Klasse.name#3``."""
    name = mutant.rsplit(".", 1)[-1].replace("__mutmut_", "#")
    return name.removeprefix("x_").removeprefix(f"x{TRENNER}").replace(TRENNER, ".")


def probe(ort: Path, basis: str, protokoll: Path, frist: float = FRIST) -> Probe:
    """Lässt mutmut auf den geänderten Funktionen von ``basis..HEAD`` laufen."""
    start = time.monotonic()

    def ende(code: int | str, text: str) -> Probe:
        return Probe(code, round(time.monotonic() - start, 1), text)

    muster = geaenderte_funktionen(ort, basis)
    if not muster:
        return ende("", "entfällt: keine geänderte Funktion unter src/")
    python = str(ort / ".venv/bin/python")
    tests = leiter_schnell.betroffene(ort, list(muster)).dateien
    if not tests:
        return ende("", "entfällt: kein Test importiert die geänderten Module")
    alle = [m for liste in muster.values() for m in liste]
    with tempfile.TemporaryDirectory(prefix="mutation-") as ordner:
        baum = Path(ordner) / "baum"
        _git(ort, ["git", "worktree", "add", "-q", "--detach", str(baum), "HEAD"])
        try:
            kopien = _oberste(baum)
            cfg = einstellungen(list(muster), tests, kopien)
            (baum / "setup.cfg").write_text(cfg, "utf-8")
            code, ausgabe = _mutmut(python, baum, ["run", *alle], frist)
            if code == 0:
                code, ausgabe = _mutmut(python, baum, ["results", "--all", "true"], 60)
                text = urteil(*auszaehlen(ausgabe, alle), ausgabe)
            else:
                text = f"entfällt: {_grund(code, ausgabe)}"
        finally:
            _git(ort, ["git", "worktree", "remove", "--force", str(baum)])
    protokoll.write_text(ausgabe, "utf-8")
    return ende(code, text)


def _grund(code: int | str, ausgabe: str) -> str:
    if isinstance(code, str):
        return f"mutmut {code}"
    if "No module named mutmut" in ausgabe:
        return "mutmut fehlt im .venv"
    letzte = (ausgabe.strip().splitlines() or [""])[-1][:120]
    return f"mutmut Exit {code} ({letzte})" if letzte else f"mutmut Exit {code}"


def _mutmut(
    python: str, baum: Path, argumente: list[str], frist: float
) -> tuple[int | str, str]:
    befehl = [python, "-m", "mutmut", *argumente]
    try:
        lauf = subprocess.run(
            befehl,
            cwd=baum,
            env=_umgebung(),
            capture_output=True,
            text=True,
            timeout=frist,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return f"nach {frist:.0f} s abgebrochen", ""
    return lauf.returncode, lauf.stdout + lauf.stderr


def _oberste(baum: Path) -> list[str]:
    pfade = _git(baum, ["git", "ls-files", "-z"]).split("\0")
    return sorted({p.split("/")[0] for p in pfade if p} - NICHT_KOPIEREN)


def _git(ort: Path, befehl: list[str]) -> str:
    return subprocess.run(
        befehl, cwd=ort, env=_umgebung(), capture_output=True, text=True, check=True
    ).stdout


def _umgebung() -> dict[str, str]:
    return {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
