"""Stufe 0: der Workflow der Gegenprobe (``gegenprobe.yml``) hält Zeit und Grenzen.

Fehlt der Workflow, gilt nichts. Sonst: er hängt am Gerätelauf (``workflow_run`` auf
den Namen aus ``geraete.yml``, nur ``completed``; ohne ``geraete.yml`` entfällt nur
diese Prüfung), hat eine eigene Concurrency-Gruppe ohne Abbruch (CLAUDE.md Regel 9),
sein Job-Timeout ist ``JOB_MINUTEN`` aus ``scripts/gegenprobe.py``, und der Aufruf
gibt ``--job-start`` und ``--job-frist-sekunden JOB_FRIST_S`` mit (Regel 8).
Committet wird nur ``data/state/gegenprobe``. Läuft mit den Belegverträgen
(``waechter_belegvertraege``).
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
    if job.get("timeout-minutes") != werte.get("JOB_MINUTEN"):
        meldungen.append(
            f"{WORKFLOW}: timeout-minutes {job.get('timeout-minutes')!r}"
            f" ≠ JOB_MINUTEN {werte.get('JOB_MINUTEN')!r} in {SKRIPT}"
        )
    frist = re.search(r"--job-frist-sekunden\s+(\d+)", text)
    if frist is None or float(frist.group(1)) != werte.get("JOB_FRIST_S"):
        meldungen.append(f"{WORKFLOW}: --job-frist-sekunden ≠ JOB_FRIST_S in {SKRIPT}")
    if "--job-start" not in text:
        meldungen.append(f"{WORKFLOW}: --job-start fehlt (Frist gegen die Restzeit)")
    hinzu = re.findall(r"git add (\S+)", text)
    if hinzu != ERLAUBT_ADD:
        meldungen.append(f"{WORKFLOW}: git add nimmt {hinzu}, erlaubt {ERLAUBT_ADD}")
    return meldungen
