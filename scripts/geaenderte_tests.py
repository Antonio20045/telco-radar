"""Tests, die eine Änderung selbst anfasst: Stufe 4 wählt sie nie ab, und kappt sie
den Lauf, laufen sie danach allein (``nachlauf``).

Geändert ist ein Test, wenn eine gegen ``HEAD`` geänderte Zeile in ihm liegt oder
er, auch über weitere Hilfen, einen Namen nutzt, den eine geänderte Anweisung auf
Modulebene bindet (Hilfe, Fixture, Konstante, Import). Eine Datei ohne Stand in
``HEAD`` und eine, deren Unterschied sich nicht lesen lässt, gilt ganz als geändert.
"""

from __future__ import annotations

import ast
import re
import subprocess
from collections.abc import Callable, Iterable, Mapping
from pathlib import Path
from typing import TextIO

import pruefstempel
from leiter_befunde import Ergebnis, rote_zeilen

GANZE_DATEI = ""
DATEIWEIT = frozenset(
    {
        "pytestmark",
        "setup_module",
        "teardown_module",
        "setUpModule",
        "tearDownModule",
        "setup_function",
        "teardown_function",
    }
)
NACHLAUF_SEKUNDEN = 180
DIFF = ("diff", "-U0", "--no-color", "--no-ext-diff", "--no-textconv")
HUNK = re.compile(r"^@@ -\S+ \+(\d+)(?:,(\d+))? @@", re.MULTILINE)


def ohne(nodeids: Iterable[str], praefixe: Iterable[str]) -> list[str]:
    """Gibt ``nodeids`` ohne die, die zu einem der ``praefixe`` gehören oder, weil
    pytest ``--deselect`` als Präfix liest, einen geänderten Test mit abwählten."""
    praefixe = list(praefixe)
    return [
        t
        for t in nodeids
        if not ist_geaendert(t, praefixe) and not any(p.startswith(t) for p in praefixe)
    ]


def nachlauf(
    log: TextIO,
    lauf: Callable[..., subprocess.CompletedProcess[str]],
    praefixe: list[str],
    gemessen: Mapping[str, float],
    befehl: Callable[[list[str], float], list[str]],
) -> Ergebnis | None:
    """Lässt die geänderten Tests noch einmal allein laufen, wenn Stufe 4 gekappt
    wurde, bis ``NACHLAUF_SEKUNDEN``; ein roter oder abgebrochener Lauf ist rot.
    ``befehl`` bekommt die gemessene Laufzeit der Tests, um Worker zu wählen."""
    if not praefixe:
        return None
    ziele = [p.removesuffix("::") for p in praefixe]
    dauer = sum(s for t, s in gemessen.items() if ist_geaendert(t, praefixe))
    ergebnis = lauf(log, befehl(ziele, dauer), {"COLUMNS": "1000"}, NACHLAUF_SEKUNDEN)
    if ergebnis.returncode in (0, 5):
        return None
    rot = rote_zeilen(ergebnis.stdout) or [
        f"geänderte Tests: pytest endet mit {ergebnis.returncode}:",
        *(ergebnis.stdout + ergebnis.stderr).splitlines()[-20:],
    ]
    return Ergebnis("4 Betroffen", False, rot)


def geaenderte_tests(wurzel: Path, dateien: Iterable[str]) -> list[str]:
    """Gibt je Testdatei die Präfixe ihrer geänderten Tests (``datei::name``);
    ``datei::`` steht für die ganze Datei."""
    praefixe: list[str] = []
    for datei in dateien:
        zeilen = geaenderte_zeilen(wurzel, datei)
        try:
            baum = ast.parse((wurzel / datei).read_text("utf-8", errors="replace"))
        except (OSError, SyntaxError):
            baum = None
        namen = (
            None if zeilen is None or baum is None else tests_in_zeilen(baum, zeilen)
        )
        if namen is None:
            praefixe.append(f"{datei}::{GANZE_DATEI}")
        else:
            praefixe += [f"{datei}::{name}" for name in namen]
    return sorted(praefixe)


def geaenderte_zeilen(wurzel: Path, datei: str) -> set[int] | None:
    """Gibt die gegen ``HEAD`` geänderten Zeilen des Arbeitsstands, ``None`` für
    eine neue oder nicht vergleichbare Datei."""
    try:
        pruefstempel.git(wurzel, "cat-file", "-e", f"HEAD:{datei}")
        unterschied = pruefstempel.git(wurzel, *DIFF, "HEAD", "--", datei)
    except pruefstempel.StempelFehler:
        return None
    if unterschied.strip() and not HUNK.search(unterschied):
        return None
    zeilen: set[int] = set()
    for start, anzahl in HUNK.findall(unterschied):
        erste, menge = int(start), 1 if anzahl == "" else int(anzahl)
        zeilen |= set(range(erste, erste + menge)) if menge else {erste, erste + 1}
    return zeilen


def tests_in_zeilen(baum: ast.Module, zeilen: set[int]) -> list[str] | None:
    """Gibt die Testfunktionen und -klassen, die eine der ``zeilen`` enthalten oder
    über Hilfen der Modulebene einen dort gebundenen Namen nutzen; ``None`` heißt die
    ganze Datei (geänderte ``autouse``-Fixture, Name aus ``DATEIWEIT``, ``pytest_``-Hook
    oder Anweisung, die keinen Namen bindet)."""
    hilfen = [k for k in baum.body if not _ist_test(k)]
    geaendert: set[str] = set()
    for knoten in hilfen:
        if not _spanne(knoten) & zeilen:
            continue
        namen = _gebundene_namen(knoten)
        hook = any(n.startswith("pytest_") for n in namen)
        if not namen or hook or namen & DATEIWEIT or _ist_autouse(knoten):
            return None
        geaendert |= namen
    while neu := {
        n
        for k in hilfen
        if _genutzte_namen(k) & geaendert
        for n in _gebundene_namen(k) - geaendert
    }:
        geaendert |= neu
    return [
        name
        for name, knoten in _tests(baum)
        if _spanne(knoten) & zeilen or _genutzte_namen(knoten) & geaendert
    ]


def ist_geaendert(nodeid: str, praefixe: Iterable[str]) -> bool:
    """Wahr, wenn ``nodeid`` zu einem der Präfixe aus ``geaenderte_tests`` gehört."""
    for praefix in praefixe:
        if praefix.endswith("::") and nodeid.startswith(praefix):
            return True
        if nodeid == praefix or nodeid.startswith((f"{praefix}[", f"{praefix}::")):
            return True
    return False


Definition = ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef


def _tests(baum: ast.Module) -> list[tuple[str, ast.stmt]]:
    """Testfunktionen und Testklassen der Modulebene; eine Klasse zählt als Ganzes."""
    return [
        (k.name, k) for k in baum.body if isinstance(k, Definition) and _ist_test(k)
    ]


def _ist_test(knoten: ast.stmt) -> bool:
    if isinstance(knoten, ast.ClassDef):
        return knoten.name.startswith("Test")
    if isinstance(knoten, ast.FunctionDef | ast.AsyncFunctionDef):
        return knoten.name.startswith("test")
    return False


def _spanne(knoten: ast.stmt) -> set[int]:
    dekoriert = getattr(knoten, "decorator_list", [])
    anfang = min([knoten.lineno, *(d.lineno for d in dekoriert)])
    return set(range(anfang, (knoten.end_lineno or knoten.lineno) + 1))


def _gebundene_namen(knoten: ast.stmt) -> set[str]:
    """Namen, die die Anweisung auf Modulebene bindet; Rümpfe zählen nicht."""
    namen: set[str] = set()
    offen: list[ast.AST] = [knoten]
    while offen:
        teil = offen.pop()
        if isinstance(teil, Definition):
            namen.add(teil.name)
            continue
        offen += ast.iter_child_nodes(teil)
        if isinstance(teil, ast.Import | ast.ImportFrom):
            namen |= {(a.asname or a.name).partition(".")[0] for a in teil.names}
        elif isinstance(teil, ast.Name) and isinstance(teil.ctx, ast.Store):
            namen.add(teil.id)
    return namen


def _genutzte_namen(knoten: ast.AST) -> set[str]:
    """Namen, Argumente (Fixtures) und Texte (``usefixtures("name")``) im Knoten."""
    namen: set[str] = set()
    for teil in ast.walk(knoten):
        if isinstance(teil, ast.Name):
            namen.add(teil.id)
        elif isinstance(teil, ast.arg):
            namen.add(teil.arg)
        elif isinstance(teil, ast.Constant) and isinstance(teil.value, str):
            namen.add(teil.value)
    return namen


def _ist_autouse(knoten: ast.stmt) -> bool:
    return any(
        isinstance(k, ast.keyword) and k.arg == "autouse"
        for d in getattr(knoten, "decorator_list", [])
        for k in ast.walk(d)
    )
