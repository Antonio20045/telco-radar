"""Stufe-0-Vertrag der Gegenprobe als Matrix je Anbieter (Vorlage zu
``scripts/waechter_gegenprobe.py``): das Beispiel hält den Vertrag, jeder Test bricht
genau eine Stelle."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
wg = importlib.import_module("waechter_gegenprobe")

SKRIPT = (
    "JOB_MINUTEN = 60\nPUFFER_S = 600\nJOB_FRIST_S = JOB_MINUTEN * 60 - PUFFER_S\n"
    "MATRIX_JOB_MINUTEN = 160\n"
    "MATRIX_JOB_FRIST_S = MATRIX_JOB_MINUTEN * 60 - PUFFER_S\n"
)
GERAETE = "name: Geraete- und Preisradar\non: {workflow_dispatch: {}}\njobs: {}\n"
MATRIX = """\
name: Gegenprobe
on:
  workflow_run:
    workflows: ["Geraete- und Preisradar"]
    types: [completed]
concurrency:
  group: gegenprobe
  cancel-in-progress: false
jobs:
  plan:
    steps:
      - run: python scripts/gegenprobe.py --root . --plan
  gegenprobe:
    timeout-minutes: 160
    strategy:
      matrix:
        anbieter: ${{ fromJSON(needs.plan.outputs.jobs) }}
    steps:
      - run: |
          python scripts/gegenprobe.py --anbieter "${{ matrix.anbieter }}" \\
            --ausgabe teile/x.jsonl --job-start "$JOB_START" --job-frist-sekunden 9000
  ablegen:
    steps:
      - run: python scripts/gegenprobe_ablegen.py --root . --quelle teile
      - run: |
          git add data/state/gegenprobe
          git commit -m x
"""


def _baum(tmp_path: Path, workflow: str) -> Path:
    (tmp_path / ".github/workflows").mkdir(parents=True)
    (tmp_path / "scripts").mkdir()
    (tmp_path / wg.SKRIPT).write_text(SKRIPT, encoding="utf-8")
    (tmp_path / wg.GERAETE).write_text(GERAETE, encoding="utf-8")
    (tmp_path / wg.WORKFLOW).write_text(workflow, encoding="utf-8")
    return tmp_path


def test_matrix_haelt_den_vertrag(tmp_path):
    assert wg.gegenprobe_haelt_zeit_und_grenzen(_baum(tmp_path, MATRIX)) == []


def test_matrix_frist_ist_die_matrix_konstante(tmp_path):
    kaputt = MATRIX.replace("--job-frist-sekunden 9000", "--job-frist-sekunden 3000")
    meldungen = wg.gegenprobe_haelt_zeit_und_grenzen(_baum(tmp_path, kaputt))
    assert meldungen == [
        f"{wg.WORKFLOW}: --job-frist-sekunden ≠ MATRIX_JOB_FRIST_S in {wg.SKRIPT}"
    ]


def test_matrix_ohne_ablegen_ist_rot(tmp_path):
    kaputt = MATRIX.replace("scripts/gegenprobe_ablegen.py", "scripts/anderes.py")
    meldungen = wg.gegenprobe_haelt_zeit_und_grenzen(_baum(tmp_path, kaputt))
    assert any("ablegen" in m for m in meldungen)


def test_matrix_job_ohne_schnitt_ist_rot(tmp_path):
    kaputt = MATRIX.replace('--anbieter "${{ matrix.anbieter }}"', "")
    meldungen = wg.gegenprobe_haelt_zeit_und_grenzen(_baum(tmp_path, kaputt))
    assert any("--ausgabe" in m for m in meldungen)
