"""Stufe 0: Module ohne veränderlichen Modulzustand.

Ein Modul in ``ZUSTANDSFREI`` bindet auf Modulebene nur ``log`` und Konstanten:
Namen mit großem Anfangsbuchstaben (ein führender Unterstrich zählt nicht) und
einem Wert, der sich nicht ändern lässt, also Literal, Tupel, ``frozenset(...)``,
Typangabe oder Rechnung aus Konstanten. Ein annotiertes ``= None`` ist ein Platz
zum Umsetzen von außen und damit Zustand. ``global`` ist dort überall verboten.
Den Zustand eines Laufs trägt ein Objekt, das der Aufrufer anlegt.
"""

from __future__ import annotations

import ast
from pathlib import Path

ZUSTANDSFREI = (
    "src/telco_radar/analyze/llm.py",
    "src/telco_radar/analyze/llm_sitzung.py",
)
UNVERAENDERLICH = (ast.Constant, ast.JoinedStr, ast.Attribute, ast.Subscript)
FESTE_AUFRUFE = frozenset({"frozenset", "tuple", "str", "int", "float"})


def _konstant(wert: ast.expr | None) -> bool:
    if isinstance(wert, ast.Tuple):
        return all(map(_konstant, wert.elts))
    if isinstance(wert, ast.BinOp):
        return _konstant(wert.left) and _konstant(wert.right)
    if isinstance(wert, ast.Call) and isinstance(wert.func, ast.Name):
        return wert.func.id in FESTE_AUFRUFE
    if isinstance(wert, ast.Name):
        return _gross(wert.id)
    return isinstance(wert, UNVERAENDERLICH)


def _gross(name: str) -> bool:
    kern = name.lstrip("_")
    return bool(kern) and kern[:1].isupper()


def zustand_in(text: str) -> list[str]:
    """Jede Bindung auf Modulebene, die keine Konstante ist, und jedes ``global``."""
    baum = ast.parse(text)
    funde = []
    for knoten in baum.body:
        if isinstance(knoten, ast.Assign):
            ziele, wert = knoten.targets, knoten.value
        elif isinstance(knoten, ast.AnnAssign):
            ziele, wert = [knoten.target], knoten.value
            if isinstance(wert, ast.Constant) and wert.value is None:
                wert = None
        else:
            continue
        for ziel in ziele:
            name = ziel.id if isinstance(ziel, ast.Name) else ast.unparse(ziel)
            if name == "log":
                continue
            if not (_gross(name) and _konstant(wert)):
                funde.append(f"Zeile {knoten.lineno} bindet {name}")
    funde += [
        f"Zeile {k.lineno} global {', '.join(k.names)}"
        for k in ast.walk(baum)
        if isinstance(k, ast.Global)
    ]
    return funde


def modulzustand(wurzel: Path) -> list[str]:
    """Rote Zeilen für veränderlichen Modulzustand in ``ZUSTANDSFREI``."""
    rot = []
    for pfad in ZUSTANDSFREI:
        datei = wurzel / pfad
        if not datei.exists():
            continue
        for fund in zustand_in(datei.read_text(encoding="utf-8")):
            rot.append(f"{pfad}: {fund}; Laufzustand gehört in ein Objekt")
    return rot
