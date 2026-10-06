"""Stufe-0-Vertrag des Klick-Erkundungs-Workflows an einem Beispiel im Wegwerfordner.

Das Beispiel hält den Vertrag; jeder Test bricht genau eine Stelle (Auslöser,
Concurrency, Rechte, Secret, Zeitgrenze, Chromium, Frist, ``git add``/``push``/
``pull``) und erwartet genau ihre Meldung. Fehlt der Workflow, gilt nichts; die
Leiter ruft den Vertrag über ``waechter_vertraege.pruefe``.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts import waechter_erkundung as we
from scripts import waechter_vertraege as wv

ORT = f"{we.WORKFLOW} Job erkunde"
MODUL = "ZEIT_JE_ANBIETER_S = 50 * 60\n"
BEISPIEL = """\
on:
  workflow_dispatch:
    inputs:
      anbieter:
        default: "alle"
permissions:
  contents: write
concurrency:
  group: klick-erkundung
  cancel-in-progress: false
jobs:
  erkunde:
    timeout-minutes: 75
    steps:
      - run: python -m playwright install --with-deps chromium
      - env:
          JOB_MINUTEN: 75
          RESERVE_SEKUNDEN: 600
        run: |
          frist=$(( JOB_START + JOB_MINUTEN * 60 - RESERVE_SEKUNDEN - $(date +%s) ))
          python scripts/klick_erkunden.py --anbieter "$A" \\
            --frist-sekunden "$frist"
  ablegen:
    steps:
      - run: |
          # git add -A steht hier nur im Kommentar
          git add erkundung
          git -C . commit -m "x"
          if git push origin "HEAD:refs/heads/klick-erkundung"; then exit 0; fi
          git pull --rebase origin klick-erkundung || exit 1
"""


@pytest.fixture
def projekt(tmp_path: Path) -> Path:
    _schreibe(tmp_path, we.WORKFLOW, BEISPIEL)
    _schreibe(tmp_path, we.MODUL, MODUL)
    return tmp_path


def _schreibe(wurzel: Path, pfad: str, text: str) -> None:
    ziel = wurzel / pfad
    ziel.parent.mkdir(parents=True, exist_ok=True)
    ziel.write_text(text, encoding="utf-8")


def _ersetze(wurzel: Path, pfad: str, alt: str, neu: str) -> None:
    ziel = wurzel / pfad
    text = ziel.read_text(encoding="utf-8")
    assert alt in text, alt
    ziel.write_text(text.replace(alt, neu, 1), encoding="utf-8")


def test_das_beispiel_haelt_den_vertrag(projekt):
    assert we.vertrag(projekt) == []


def test_ohne_workflow_gilt_nichts(tmp_path):
    assert we.vertrag(tmp_path) == []


@pytest.mark.parametrize(
    ("alt", "neu", "meldung"),
    [
        ("on:\n", "on:\n  push:\n", "nur workflow_dispatch"),
        ('default: "alle"', 'default: "o2"', "Eingabe anbieter ohne Vorgabe 'alle'"),
        ("group: klick-erkundung", "group: geraete", "Concurrency-Gruppe"),
        ("cancel-in-progress: false", "cancel-in-progress: true", "ohne Abbruch"),
        ("contents: write", "contents: read", "permissions {'contents': 'write'}"),
        (
            "      - env:\n",
            "      - env:\n          HOOK: ${{ secrets.RENDER_DEPLOY_HOOK }}\n",
            "Secret oder Render-Hook (RENDER_DEPLOY, secrets.)",
        ),
        (
            "timeout-minutes: 75",
            "timeout-minutes: 60",
            "JOB_MINUTEN 75 ≠ timeout-minutes 60",
        ),
        (
            "python -m playwright install --with-deps chromium",
            "pip install -r requirements.txt",
            "kein 'playwright install' vor scripts/klick_erkunden.py",
        ),
        ('--frist-sekunden "$frist"', '"$frist"', "ohne --frist-sekunden"),
        (
            "RESERVE_SEKUNDEN: 600",
            "RESERVE_SEKUNDEN: 1800",
            "lassen weniger als ZEIT_JE_ANBIETER_S 3000 s",
        ),
        ("git add erkundung", "git add erkundung data", "git add erkundung data statt"),
        ("git add erkundung", "git -C ablage add -A", "git add -A statt erkundung"),
        ("git add erkundung", "git add .", "git add . statt erkundung"),
        ('push origin "HEAD', 'push --force origin "HEAD', "git push --force origin"),
        ('"HEAD:refs/heads/klick-erkundung"', "HEAD:main", "git push origin HEAD:main"),
        (
            '"HEAD:refs/heads/klick-erkundung"',
            "+HEAD:refs/heads/klick-erkundung",
            "+HEAD",
        ),
        (
            "--rebase origin klick-erkundung",
            "--rebase origin main",
            "git pull --rebase",
        ),
        ('-m "x"', '-m "x', "nicht prüfbar"),
    ],
)
def test_jeder_bruch_nennt_seine_stelle(projekt, alt, neu, meldung):
    _ersetze(projekt, we.WORKFLOW, alt, neu)

    meldungen = we.vertrag(projekt)

    assert len(meldungen) == 1, meldungen
    assert meldung in meldungen[0]


def test_zeitgrenze_kommt_aus_dem_modul(projekt):
    _schreibe(projekt, we.MODUL, "ZEIT_JE_ANBIETER_S = 70 * 60\n")

    assert we.vertrag(projekt) == [
        f"{ORT}: 75 min minus RESERVE_SEKUNDEN lassen weniger als"
        " ZEIT_JE_ANBIETER_S 4200 s"
    ]


def test_unlesbare_zeitgrenze_ist_rot(projekt):
    _schreibe(projekt, we.MODUL, "ZEIT_JE_ANBIETER_S = int('3000')\n")

    assert we.vertrag(projekt) == [
        f"{ORT}: ZEIT_JE_ANBIETER_S in {we.MODUL} nicht lesbar"
    ]


def test_workflow_ohne_erkundungsjob_ist_rot(projekt):
    _ersetze(projekt, we.WORKFLOW, "scripts/klick_erkunden.py", "scripts/anders.py")

    assert we.vertrag(projekt) == [
        f"{we.WORKFLOW}: kein Job ruft scripts/klick_erkunden.py ohne --plan"
    ]


def test_die_leiter_ruft_den_vertrag(projekt):
    _ersetze(projekt, we.WORKFLOW, "contents: write", "contents: read")

    assert we.vertrag(projekt)[0] in wv.pruefe(projekt)
