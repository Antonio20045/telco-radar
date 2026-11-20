"""Stufe-0-Vertrag des Gegenprobe-Workflows an einem Beispiel im Wegwerfordner.

Das Beispiel hält den Vertrag; jeder Test bricht genau eine Stelle und erwartet ihre
Meldung. Fehlt der Workflow, gilt nichts.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
wg = importlib.import_module("waechter_gegenprobe")
wv = importlib.import_module("waechter_vertraege")

SKRIPT = "JOB_MINUTEN = 60\nPUFFER_S = 600\nJOB_FRIST_S = JOB_MINUTEN * 60 - PUFFER_S\n"
GERAETE = "name: Geraete- und Preisradar\non: {workflow_dispatch: {}}\njobs: {}\n"
BEISPIEL = """\
name: Gegenprobe
on:
  workflow_run:
    workflows: ["Geraete- und Preisradar"]
    types: [completed]
concurrency:
  group: gegenprobe
  cancel-in-progress: false
jobs:
  gegenprobe:
    timeout-minutes: 60
    steps:
      - run: |
          python scripts/gegenprobe.py --hochladen \\
            --job-start "$JOB_START" --job-frist-sekunden 3000
      - run: |
          git add data/state/gegenprobe
          git commit -m x
"""


def _baum(tmp_path: Path, workflow: str | None = BEISPIEL) -> Path:
    (tmp_path / ".github/workflows").mkdir(parents=True)
    (tmp_path / "scripts").mkdir()
    (tmp_path / wg.SKRIPT).write_text(SKRIPT, encoding="utf-8")
    (tmp_path / wg.GERAETE).write_text(GERAETE, encoding="utf-8")
    if workflow is not None:
        (tmp_path / wg.WORKFLOW).write_text(workflow, encoding="utf-8")
    return tmp_path


def test_beispiel_haelt_den_vertrag(tmp_path):
    assert wg.gegenprobe_haelt_zeit_und_grenzen(_baum(tmp_path)) == []


def test_ohne_workflow_gilt_nichts(tmp_path):
    assert wg.gegenprobe_haelt_zeit_und_grenzen(_baum(tmp_path, None)) == []


@pytest.mark.parametrize(
    ("alt", "neu", "meldung"),
    [
        ("timeout-minutes: 60", "timeout-minutes: 90", "timeout-minutes 90"),
        ("--job-frist-sekunden 3000", "--job-frist-sekunden 3500", "JOB_FRIST_S"),
        ('--job-start "$JOB_START" ', "", "--job-start fehlt"),
        ("cancel-in-progress: false", "cancel-in-progress: true", "ohne Abbruch"),
        ('["Geraete- und Preisradar"]', '["Klick-Tageslauf"]', "workflow_run"),
        ("git add data/state/gegenprobe", "git add data", "git add nimmt"),
    ],
)
def test_jede_bruchstelle_meldet_sich(tmp_path, alt, neu, meldung):
    assert alt in BEISPIEL
    wurzel = _baum(tmp_path, BEISPIEL.replace(alt, neu))
    meldungen = wg.gegenprobe_haelt_zeit_und_grenzen(wurzel)
    assert len(meldungen) == 1 and meldung in meldungen[0]


def test_regel_steht_in_der_leiter():
    assert wg.gegenprobe_haelt_zeit_und_grenzen in wv.REGELN
