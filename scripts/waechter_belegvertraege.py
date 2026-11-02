"""Vertrag der Belegbilder: Frist und Restzeit stehen im Python-Code, nicht im Workflow.

Der Schritt „Belege-Manifest“ in ``geraete.yml`` darf den Commit des Messtags nie
sperren: ``belege_manifest.py`` hält ``GESAMT_FRIST_S`` deutlich unter dem Schritt-
Timeout ein und endet mit Exit 0. Der Job ``belege`` in ``klick.yml`` rechnet seine
Frist gegen die Restzeit des Jobs (CLAUDE.md Regel 8): ``belege_veroeffentlichen.py``
zieht von jeder übergebenen Frist die Zeit eines Aufrufs ab und lässt einen Puffer.
Die Regel liest nur diese Skripte (ohne sie zu laden) und verlangt nichts von den
Workflow-Dateien. Sie gehört zu ``waechter_vertraege.REGELN``.
"""

from __future__ import annotations

import ast
import operator
from pathlib import Path

BELEG_ABLAGE = "src/telco_radar/beleg_ablage.py"
BELEG_SKRIPT = "scripts/belege_veroeffentlichen.py"
BELEG_MANIFEST = "scripts/belege_manifest.py"
FRIST_FUNKTION = "wirksame_frist"
MIN_ABSTAND_MANIFEST_S = 60
"""So viel Luft muss zwischen ``GESAMT_FRIST_S`` und ``SCHRITT_FRIST_S`` bleiben."""
_RECHNUNG = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul}


def _wert(knoten: ast.expr, bekannt: dict[str, float]) -> float | None:
    """Zahl, Name einer bekannten Konstante oder ``+ - *`` daraus; sonst ``None``."""
    if isinstance(knoten, ast.Constant) and isinstance(knoten.value, int | float):
        return float(knoten.value)
    if isinstance(knoten, ast.Name):
        return bekannt.get(knoten.id)
    if isinstance(knoten, ast.BinOp) and type(knoten.op) in _RECHNUNG:
        links, rechts = _wert(knoten.left, bekannt), _wert(knoten.right, bekannt)
        if links is None or rechts is None:
            return None
        return _RECHNUNG[type(knoten.op)](links, rechts)
    return None


def konstanten(pfad: Path, bekannt: dict[str, float] | None = None) -> dict[str, float]:
    """Alle Modulkonstanten, die sich aus Zahlen und ``+ - *`` rechnen lassen, ohne das
    Modul zu laden; ``bekannt`` sind Namen aus anderen Modulen."""
    werte = dict(bekannt or {})
    for knoten in ast.parse(pfad.read_text(encoding="utf-8")).body:
        if isinstance(knoten, ast.Assign) and len(knoten.targets) == 1:
            ziel = knoten.targets[0]
            wert = _wert(knoten.value, werte)
            if isinstance(ziel, ast.Name) and wert is not None:
                werte[ziel.id] = wert
    return werte


def konstante(pfad: Path, name: str) -> float | None:
    """Der Zahlenwert einer Modulkonstante, ohne das Modul zu laden."""
    return konstanten(pfad).get(name)


def _hat_funktion(pfad: Path, name: str) -> bool:
    baum = ast.parse(pfad.read_text(encoding="utf-8"))
    return any(isinstance(k, ast.FunctionDef) and k.name == name for k in baum.body)


def belegbilder_halten_commit_und_zeit_frei(wurzel: Path) -> list[str]:
    """Das Manifest-Skript bricht vor dem Schritt-Timeout selbst ab; der Belegjob
    lässt nach der wirksamen Frist einen letzten Aufruf plus Puffer."""
    return [*_manifest_frist(wurzel), *_belegjob_frist(wurzel)]


def _manifest_frist(wurzel: Path) -> list[str]:
    werte = konstanten(wurzel / BELEG_MANIFEST)
    fehlt = [
        n
        for n in ("SCHRITT_FRIST_S", "GESAMT_FRIST_S", "SCHREIB_RESERVE_S")
        if n not in werte
    ]
    if fehlt:
        return [f"{BELEG_MANIFEST}: Konstanten {', '.join(fehlt)} nicht lesbar"]
    schritt, gesamt, reserve = (
        werte["SCHRITT_FRIST_S"],
        werte["GESAMT_FRIST_S"],
        werte["SCHREIB_RESERVE_S"],
    )
    meldungen = []
    if schritt - gesamt < MIN_ABSTAND_MANIFEST_S:
        meldungen.append(
            f"{BELEG_MANIFEST}: GESAMT_FRIST_S {gesamt:.0f} liegt nicht "
            f"{MIN_ABSTAND_MANIFEST_S} s unter SCHRITT_FRIST_S {schritt:.0f}: der "
            "Schritt könnte vom Timeout beendet werden und den Commit sperren"
        )
    if not 0 < reserve < gesamt:
        meldungen.append(
            f"{BELEG_MANIFEST}: SCHREIB_RESERVE_S {reserve:.0f} muss zwischen 0 "
            f"und GESAMT_FRIST_S {gesamt:.0f} liegen"
        )
    return meldungen


def _belegjob_frist(wurzel: Path) -> list[str]:
    aufruf_s = konstante(wurzel / BELEG_ABLAGE, "ZEIT_JE_AUFRUF_S")
    if aufruf_s is None:
        return [f"{BELEG_ABLAGE}: ZEIT_JE_AUFRUF_S nicht lesbar"]
    skript = wurzel / BELEG_SKRIPT
    werte = konstanten(skript, {"ZEIT_JE_AUFRUF_S": aufruf_s})
    fehlt = [n for n in ("JOB_MINUTEN", "PUFFER_S", "JOB_FRIST_S") if n not in werte]
    if fehlt:
        return [f"{BELEG_SKRIPT}: Konstanten {', '.join(fehlt)} nicht lesbar"]
    meldungen = []
    rest = werte["JOB_MINUTEN"] * 60 - werte["JOB_FRIST_S"]
    noetig = aufruf_s + werte["PUFFER_S"]
    if rest < noetig:
        meldungen.append(
            f"{BELEG_SKRIPT}: nach JOB_FRIST_S bleiben nur {rest:.0f} s bis zum "
            f"Job-Timeout, nötig sind {noetig:.0f} (ein letzter Aufruf plus Puffer)"
        )
    if not _hat_funktion(skript, FRIST_FUNKTION):
        meldungen.append(
            f"{BELEG_SKRIPT}: {FRIST_FUNKTION} fehlt, die übergebene Frist wird "
            "nicht um die Zeit eines Aufrufs gekürzt"
        )
    return meldungen
