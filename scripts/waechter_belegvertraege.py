"""Vertrag der Belegbilder in den Workflows: Commit des Messtags und Restzeit.

Der Schritt „Belege-Manifest“ in ``geraete.yml`` darf den Commit des Messtags nie
sperren; der Job ``belege`` in ``klick.yml`` rechnet seine Frist gegen die Restzeit
des Jobs (CLAUDE.md Regel 8). Die Regel gehört zu ``waechter_vertraege.REGELN``.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import yaml

GERAETE = ".github/workflows/geraete.yml"
KLICK = ".github/workflows/klick.yml"
BELEG_ABLAGE = "src/telco_radar/beleg_ablage.py"
BELEG_SKRIPT = "scripts/belege_veroeffentlichen.py"
SCHRITT = "Belege-Manifest"
COMMIT_SCHRITT = "Commit state"
FRIST_OPTION = "--job-frist-sekunden"
AUSFALL_OPTION = "--melde-ausfall"


def konstante(pfad: Path, name: str) -> float | None:
    """Der Zahlenwert einer Modulkonstante, ohne das Modul zu laden."""
    for knoten in ast.parse(pfad.read_text(encoding="utf-8")).body:
        if (
            isinstance(knoten, ast.Assign)
            and [getattr(z, "id", None) for z in knoten.targets] == [name]
            and isinstance(knoten.value, ast.Constant)
        ):
            return float(knoten.value.value)
    return None


def _yaml(wurzel: Path, pfad: str) -> dict:
    return yaml.safe_load((wurzel / pfad).read_text(encoding="utf-8"))


def belegbilder_halten_commit_und_zeit_frei(wurzel: Path) -> list[str]:
    """Das Manifest bricht vor seinem Schritt-Timeout selbst ab, endet immer mit
    ``exit 0`` (ohne ``continue-on-error``, das Stufe 0 zählt), vermerkt jeden
    Fehler als Ausfall und steht vor dem Commit; der Belegjob lässt einen letzten
    Aufruf plus Puffer."""
    schritte = _yaml(wurzel, GERAETE)["jobs"]["geraete"]["steps"]
    namen = [s.get("name") for s in schritte]
    schritt = schritte[namen.index(SCHRITT)]
    run = schritt.get("run", "")
    sekunden = int(schritt.get("timeout-minutes", 0)) * 60
    innen = re.search(r"^\s*timeout\s+(\d+)\s", run, re.MULTILINE)
    pruefungen = [
        (
            namen.index(SCHRITT) < namen.index(COMMIT_SCHRITT),
            "steht nicht vor dem Commit",
        ),
        (
            (run.strip().splitlines() or [""])[-1].strip() == "exit 0"
            and "|| rc=$?" in run,
            "endet nicht immer mit exit 0 und könnte den Commit sperren",
        ),
        (sekunden > 0, "hat kein timeout-minutes"),
        (
            bool(innen) and int(innen.group(1)) < sekunden,
            "bricht nicht vor dem Schritt-Timeout selbst ab",
        ),
        (AUSFALL_OPTION in run, "meldet einen Fehler nicht als Ausfall an die Seite"),
    ]
    meldungen = [
        f"{GERAETE}: Schritt {SCHRITT!r} {text}"
        for gilt, text in pruefungen
        if not gilt
    ]
    return [*meldungen, *_belegjob_frist(wurzel)]


def _belegjob_frist(wurzel: Path) -> list[str]:
    job = _yaml(wurzel, KLICK)["jobs"]["belege"]
    sekunden = int(job["timeout-minutes"]) * 60
    skript = BELEG_SKRIPT.split("/")[-1]
    aufruf = next(s["run"] for s in job["steps"] if skript in s.get("run", ""))
    frist = int(aufruf.split(FRIST_OPTION)[1].split()[0])
    aufruf_s = konstante(wurzel / BELEG_ABLAGE, "ZEIT_JE_AUFRUF_S")
    puffer = konstante(wurzel / BELEG_SKRIPT, "PUFFER_S")
    minuten = konstante(wurzel / BELEG_SKRIPT, "JOB_MINUTEN")
    if aufruf_s is None or puffer is None or minuten is None:
        return [f"{KLICK}: Konstanten der Belegfrist nicht lesbar"]
    meldungen = []
    if minuten * 60 != sekunden:
        meldungen.append(
            f"{KLICK}: Job belege {sekunden} s ≠ JOB_MINUTEN {minuten} min"
        )
    if sekunden - frist < aufruf_s + puffer:
        meldungen.append(
            f"{KLICK}: Job belege lässt nach {FRIST_OPTION} {frist} nur"
            f" {sekunden - frist} s, nötig sind {aufruf_s + puffer:.0f}"
            " (ein letzter Aufruf plus Puffer)"
        )
    return meldungen
