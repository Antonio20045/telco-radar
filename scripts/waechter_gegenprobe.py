"""Stufe 0: der Workflow der Gegenprobe (``gegenprobe.yml``) hält Zeit und Grenzen.

Fehlt der Workflow, gilt nichts. Sonst: er hängt am Gerätelauf (``workflow_run`` auf
den Namen aus ``geraete.yml``, nur ``completed``; ohne ``geraete.yml`` entfällt nur
diese Prüfung), hat eine eigene Concurrency-Gruppe ohne Abbruch (CLAUDE.md Regel 9),
und der Aufruf gibt ``--job-start`` und ``--job-frist-sekunden`` mit (Regel 8).
Committet wird nur ``data/state/gegenprobe``. Läuft mit den Belegverträgen
(``waechter_belegvertraege``).

Zwei Formen (``scripts/gegenprobe.py``): ein Einzeljob ``gegenprobe`` mit
``JOB_MINUTEN``/``JOB_FRIST_S``, oder eine Matrix je Anbieter (Job ``gegenprobe`` mit
``strategy.matrix``) mit ``MATRIX_JOB_MINUTEN``/``MATRIX_JOB_FRIST_S``. Die Matrix
braucht einen Job ``plan`` (``--plan``), schneidet je Job mit
``--anbieter "${{ matrix.anbieter }}"`` und ``--ausgabe`` (Teildatei, nie die
Tagesdatei) und legt nur im Job ``ablegen`` (``scripts/gegenprobe_ablegen.py``) ab,
dem einzigen, der ``git add`` ruft; so überschreiben die Matrix-Jobs einander nie.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml
from waechter_belegvertraege import konstanten

WORKFLOW = ".github/workflows/gegenprobe.yml"
GERAETE = ".github/workflows/geraete.yml"
SKRIPT = "scripts/gegenprobe.py"
JOB = "gegenprobe"
GRUPPE = "gegenprobe"
ERLAUBT_ADD = ["data/state/gegenprobe"]
MATRIX_ANBIETER = '--anbieter "${{ matrix.anbieter }}"'
ABLEGEN = "scripts/gegenprobe_ablegen.py"


def _befehle(job: dict) -> str:
    """Die ``run``-Texte eines Jobs untereinander."""
    return "\n".join(str(s.get("run") or "") for s in job.get("steps") or [])


def _matrix(daten: dict, job: dict) -> list[str]:
    """Was eine Matrix je Anbieter zusätzlich halten muss."""
    jobs = daten.get("jobs") or {}
    text = _befehle(job)
    meldungen = []
    if "--plan" not in _befehle(jobs.get("plan") or {}):
        meldungen.append(f"{WORKFLOW}: Matrix ohne Job plan (--plan)")
    if MATRIX_ANBIETER not in text or "--ausgabe" not in text:
        meldungen.append(f"{WORKFLOW}: Matrix-Job ohne {MATRIX_ANBIETER} und --ausgabe")
    if ABLEGEN not in _befehle(jobs.get("ablegen") or {}):
        meldungen.append(f"{WORKFLOW}: Matrix ohne Job ablegen ({ABLEGEN})")
    if "git add" in text:
        meldungen.append(f"{WORKFLOW}: ein Matrix-Job committet selbst")
    return meldungen


def gegenprobe_haelt_zeit_und_grenzen(wurzel: Path) -> list[str]:
    """Meldungen zum Gegenprobe-Workflow; leer, wenn er den Vertrag hält oder fehlt."""
    pfad = wurzel / WORKFLOW
    if not pfad.exists():
        return []
    geraete = wurzel / GERAETE
    name = (
        yaml.safe_load(geraete.read_text(encoding="utf-8")).get("name")
        if geraete.exists()
        else None
    )
    text = pfad.read_text(encoding="utf-8")
    daten = yaml.safe_load(text)
    meldungen: list[str] = []
    ausloeser = (daten.get(True) or daten.get("on") or {}).get("workflow_run") or {}
    if name is not None and (
        ausloeser.get("workflows") != [name] or ausloeser.get("types") != ["completed"]
    ):
        meldungen.append(f"{WORKFLOW}: workflow_run nicht nach {name!r} (completed)")
    gruppe = daten.get("concurrency") or {}
    if gruppe.get("group") != GRUPPE or gruppe.get("cancel-in-progress") is not False:
        meldungen.append(f"{WORKFLOW}: concurrency {GRUPPE!r} ohne Abbruch fehlt")
    werte = konstanten(wurzel / SKRIPT)
    job = (daten.get("jobs") or {}).get(JOB) or {}
    matrix = bool((job.get("strategy") or {}).get("matrix"))
    minuten, frist_name = (
        ("MATRIX_JOB_MINUTEN", "MATRIX_JOB_FRIST_S")
        if matrix
        else ("JOB_MINUTEN", "JOB_FRIST_S")
    )
    if job.get("timeout-minutes") != werte.get(minuten):
        meldungen.append(
            f"{WORKFLOW}: timeout-minutes {job.get('timeout-minutes')!r}"
            f" ≠ {minuten} {werte.get(minuten)!r} in {SKRIPT}"
        )
    frist = re.search(r"--job-frist-sekunden\s+(\d+)", text)
    if frist is None or float(frist.group(1)) != werte.get(frist_name):
        meldungen.append(f"{WORKFLOW}: --job-frist-sekunden ≠ {frist_name} in {SKRIPT}")
    if "--job-start" not in text:
        meldungen.append(f"{WORKFLOW}: --job-start fehlt (Frist gegen die Restzeit)")
    hinzu = re.findall(r"git add (\S+)", text)
    if hinzu != ERLAUBT_ADD:
        meldungen.append(f"{WORKFLOW}: git add nimmt {hinzu}, erlaubt {ERLAUBT_ADD}")
    if matrix:
        meldungen += _matrix(daten, job)
    return meldungen
