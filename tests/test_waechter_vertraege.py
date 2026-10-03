"""Verträge der Stufe 0 ohne Basis: jeder Verstoß ist rot und nennt Ort und Regel.

Geprüft wird an einem kleinen Projekt im Wegwerfordner, das alle Verträge hält;
jeder Test bricht genau eine Stelle und erwartet genau ihre Meldung.
"""

from __future__ import annotations

import gzip
import hashlib
import json
from pathlib import Path

import pytest

from scripts import waechter_vertraege as wv

RADAR = """\
jobs:
  radar:
    timeout-minutes: 60
"""
GERAETE = """\
on:
  schedule:
    - cron: "17 2 * * *"
    - cron: "47 9 * * *"
    - cron: "47 15 * * *"
  workflow_dispatch:
    inputs:
      frist:
        default: "1500"
jobs:
  geraete:
    steps:
      - name: Heute schon gemessen?
        id: heute
        run: echo
      - name: Run geraete stage
        if: steps.heute.outputs.fertig != 'true'
        run: python -m x --frist "${{ github.event.inputs.frist || 1500 }}"
      - name: Commit state
        if: steps.heute.outputs.fertig != 'true'
        run: |
          git add data/state/geraete_db.json data/state/geraete_preise.jsonl \\
            data/state/geraete_tco.json data/state/geraete_tco_historie.jsonl
      - name: Render site
        if: steps.heute.outputs.fertig != 'true'
        run: python -m render
      - name: Commit site
        id: commit_site
        if: steps.heute.outputs.fertig != 'true'
        run: |
          git push || {
            git reset --hard origin/main
            python -m render || exit 1
            git push || echo "Seite konnte nicht gepusht werden"
          }
          echo "fertig"
      - name: Trigger Render deploy
        if: >-
          steps.heute.outputs.fertig != 'true' &&
          steps.commit_site.outcome == 'success'
        run: bash scripts/render_deploy.sh geraete.html
      - name: Buendelabdeckung pruefen
        if: always() && steps.heute.outputs.fertig != 'true'
        run: python scripts/geraete_abdeckungswaechter.py
"""
DEPLOY = """\
for versuch in 1 2 3; do
  heute=$(date -u +%Y-%m-%d)
done
exit 1
"""
PIPELINE = "FRIST_STANDARD = 900.0\nFRIST_TAGESLAUF = 1500.0\n"


def _schreibe(wurzel: Path, pfad: str, inhalt: str | bytes) -> Path:
    ziel = wurzel / pfad
    ziel.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(inhalt, bytes):
        ziel.write_bytes(inhalt)
    else:
        ziel.write_text(inhalt, encoding="utf-8")
    return ziel


def _herkunft(wurzel: Path, ordner: str, eintraege: list[dict]) -> None:
    _schreibe(wurzel, f"{ordner}/_herkunft.json", json.dumps({"eintraege": eintraege}))


def _eintrag(datei: str, roh: bytes, **mehr) -> dict:
    return {
        "datei": datei,
        "url": "https://x.test/a",
        "sha256_roh": hashlib.sha256(roh).hexdigest(),
        **mehr,
    }


@pytest.fixture
def projekt(tmp_path: Path) -> Path:
    _schreibe(tmp_path, wv.CLAUDE_MD, "# Regeln\n")
    for ordner in wv.waechter_claude.ORDNER_CLAUDE_MD:
        _schreibe(tmp_path, f"{ordner}/CLAUDE.md", "# Ordner\n")
    _schreibe(tmp_path, wv.RADAR, RADAR)
    _schreibe(tmp_path, wv.GERAETE, GERAETE)
    _schreibe(tmp_path, wv.SETTINGS, "job_frist_sekunden: 3600\n")
    _schreibe(tmp_path, wv.DEPLOY, DEPLOY)
    _schreibe(tmp_path, wv.GERAETE_PIPELINE, PIPELINE)
    _schreibe(tmp_path, "tests/test_a.py", "def test_a():\n    assert True\n")
    roh = b"<html>echt</html>"
    _schreibe(tmp_path, "tests/fixtures/x/seite.html.gz", gzip.compress(roh))
    _herkunft(tmp_path, "tests/fixtures/x", [_eintrag("seite.html.gz", roh)])
    _schreibe(tmp_path, "tests/fixtures/bestand/2026-10-03/state/a.json", "{}")
    return tmp_path


def _ersetze(wurzel: Path, pfad: str, alt: str, neu: str) -> None:
    ziel = wurzel / pfad
    text = ziel.read_text(encoding="utf-8")
    assert alt in text, alt
    ziel.write_text(text.replace(alt, neu), encoding="utf-8")


def test_das_beispielprojekt_haelt_alle_vertraege(projekt):
    assert wv.pruefe(projekt) == []


def test_claude_md_mit_101_zeilen_ist_rot(projekt):
    _schreibe(projekt, wv.CLAUDE_MD, "x\n" * 101)
    assert wv.pruefe(projekt) == ["CLAUDE.md hat 101 Zeilen, erlaubt 100"]


def test_claude_md_mit_100_zeilen_ist_gruen(projekt):
    _schreibe(projekt, wv.CLAUDE_MD, "x\n" * 100)
    assert wv.pruefe(projekt) == []


def test_claude_md_ueber_10000_bytes_ist_rot(projekt):
    _schreibe(projekt, wv.CLAUDE_MD, "x" * 10001)
    assert wv.pruefe(projekt) == ["CLAUDE.md hat 10001 Bytes, erlaubt 10000"]


def test_fehlende_claude_md_ist_rot(projekt):
    (projekt / wv.CLAUDE_MD).unlink()
    assert wv.pruefe(projekt) == ["CLAUDE.md fehlt"]


def test_fixture_ohne_eintrag_ist_rot(projekt):
    _schreibe(projekt, "tests/fixtures/x/erfunden.html", "<p>nachgebaut</p>")
    assert wv.pruefe(projekt) == [
        "tests/fixtures/x/erfunden.html: kein Eintrag in _herkunft.json"
    ]


def test_fixture_in_ordner_ohne_herkunft_ist_rot(projekt):
    _schreibe(projekt, "tests/fixtures/sample.xml", "<rss/>")
    assert wv.pruefe(projekt) == [
        "tests/fixtures/sample.xml: _herkunft.json fehlt im Ordner"
    ]


def test_veraenderte_fixture_ist_rot(projekt):
    _schreibe(
        projekt, "tests/fixtures/x/seite.html.gz", gzip.compress(b"<html>neu</html>")
    )
    assert wv.pruefe(projekt) == [
        "tests/fixtures/x/seite.html.gz: sha256 weicht vom Eintrag in _herkunft.json ab"
    ]


def test_sha256_einer_gz_gilt_fuer_den_entpackten_inhalt(projekt):
    roh = b"<html>echt</html>"
    _schreibe(projekt, "tests/fixtures/x/seite.html.gz", gzip.compress(roh, mtime=1))
    assert wv.pruefe(projekt) == []


def test_eintrag_ohne_beleg_ist_rot(projekt):
    roh = b"<html>echt</html>"
    eintrag = _eintrag("seite.html.gz", roh)
    del eintrag["url"]
    _herkunft(projekt, "tests/fixtures/x", [eintrag])
    assert wv.pruefe(projekt) == [
        "tests/fixtures/x/seite.html.gz: Eintrag ohne"
        " url oder quelle oder abgeleitet_aus"
    ]


def test_abgeleitete_datei_mit_quelle_ist_gruen(projekt):
    roh = b"text aus dem pdf"
    _schreibe(projekt, "tests/fixtures/x/seite.txt", roh)
    eintraege = [
        _eintrag("seite.html.gz", b"<html>echt</html>"),
        {"datei": "seite.txt", "abgeleitet_aus": "seite.pdf"}
        | {"sha256_roh": hashlib.sha256(roh).hexdigest()},
    ]
    _herkunft(projekt, "tests/fixtures/x", eintraege)
    assert wv.pruefe(projekt) == []


def test_eingetragene_aber_fehlende_datei_ist_rot(projekt):
    roh = b"<html>echt</html>"
    _herkunft(
        projekt,
        "tests/fixtures/x",
        [_eintrag("seite.html.gz", roh), _eintrag("weg.html", roh)],
    )
    assert wv.pruefe(projekt) == [
        "tests/fixtures/x/weg.html: in _herkunft.json eingetragen, Datei fehlt"
    ]


def test_unlesbare_herkunft_ist_rot(projekt):
    _schreibe(projekt, "tests/fixtures/x/_herkunft.json", "{kaputt")
    assert wv.pruefe(projekt) == [
        "tests/fixtures/x/seite.html.gz: _herkunft.json nicht lesbar"
    ]


def test_schnappschuss_zaehlt_hier_nicht(projekt):
    _schreibe(projekt, "tests/fixtures/bestand/2026-10-03/state/b.json", "{}")
    assert wv.pruefe(projekt) == []


@pytest.mark.parametrize(
    ("code", "name"),
    [
        ("import inspect\nq = inspect.getsource(int)\n", "getsource"),
        ("from inspect import getsourcelines\n", "getsourcelines"),
        ("import linecache\n", "linecache"),
        ("import inspect as i\nq = i.findsource(int)\n", "findsource"),
    ],
)
def test_quelltext_ueber_inspect_ist_rot(projekt, code, name):
    _schreibe(projekt, "tests/test_b.py", code)
    meldungen = wv.pruefe(projekt)
    assert meldungen and all(f"liest Quelltext über {name}" in m for m in meldungen)
    assert all(m.startswith("tests/test_b.py:") for m in meldungen)


def test_inspect_ohne_quelltext_ist_gruen(projekt):
    _schreibe(
        projekt, "tests/test_b.py", "import inspect\nx = inspect.signature(int)\n"
    )
    assert wv.pruefe(projekt) == []


def test_jobfrist_ohne_passendes_timeout_ist_rot(projekt):
    _ersetze(projekt, wv.RADAR, "timeout-minutes: 60", "timeout-minutes: 75")
    assert wv.pruefe(projekt) == [
        "config/settings.yaml: job_frist_sekunden 3600 ≠"
        " .github/workflows/radar.yml timeout 75 min"
    ]


def test_fehlende_zustandsdatei_im_commit_ist_rot(projekt):
    _ersetze(projekt, wv.GERAETE, " data/state/geraete_tco_historie.jsonl", "")
    assert wv.pruefe(projekt) == [
        ".github/workflows/geraete.yml: 'git add data/state' nimmt"
        " geraete_tco_historie.jsonl nicht mit"
    ]


@pytest.mark.parametrize("schritt", ["Commit state", "Render site", "Commit site"])
def test_seitenbau_mit_continue_on_error_ist_rot(projekt, schritt):
    _ersetze(
        projekt,
        wv.GERAETE,
        f"      - name: {schritt}\n",
        f"      - name: {schritt}\n        continue-on-error: true\n",
    )
    assert wv.pruefe(projekt) == [
        f".github/workflows/geraete.yml: Schritt {schritt!r} schluckt Fehler"
        " (continue-on-error)"
    ]


def test_doppelter_schrittname_ist_nicht_pruefbar_und_rot(projekt):
    _ersetze(projekt, wv.GERAETE, "- name: Render site", "- name: Commit state")
    meldungen = wv.pruefe(projekt)
    assert any("'Commit state' 2-mal" in m for m in meldungen), meldungen


@pytest.mark.parametrize(
    ("pfad", "alt", "neu", "meldung"),
    [
        (
            wv.GERAETE,
            "steps.commit_site.outcome == 'success'",
            "steps.commit_site.outcome != 'skipped'",
            "der Render-Hook läuft auch ohne gebaute Seite",
        ),
        (wv.GERAETE, "render_deploy.sh geraete.html", "render_deploy.sh", "live"),
        (wv.DEPLOY, "1 2 3", "1 2", "versucht nicht dreimal"),
        (wv.DEPLOY, "date -u +%Y-%m-%d", "date", "Tagesdatum"),
        (wv.DEPLOY, "exit 1\n", "exit 0\n", "endet nicht rot"),
    ],
)
def test_render_hook_ohne_livepruefung_ist_rot(projekt, pfad, alt, neu, meldung):
    _ersetze(projekt, pfad, alt, neu)
    meldungen = wv.pruefe(projekt)
    assert len(meldungen) == 1 and meldung in meldungen[0], meldungen


def test_render_hook_mit_continue_on_error_ist_rot(projekt):
    _ersetze(
        projekt,
        wv.GERAETE,
        "      - name: Trigger Render deploy\n",
        "      - name: Trigger Render deploy\n        continue-on-error: true\n",
    )
    assert wv.pruefe(projekt) == [
        ".github/workflows/geraete.yml: der Render-Hook schluckt Fehler"
    ]


@pytest.mark.parametrize(
    ("alt", "neu", "meldung"),
    [
        ("git reset --hard origin/main", "git fetch", "der Wiederholungsweg ist weg"),
        ("|| exit 1", "|| exit 0", "verschluckt einen Renderfehler"),
        ("Seite konnte nicht gepusht werden", "x", "meldet sich nicht"),
        ('echo "fertig"', "exit 1", "endet nicht grün"),
    ],
)
def test_commit_site_ohne_lauten_abbruch_ist_rot(projekt, alt, neu, meldung):
    _ersetze(projekt, wv.GERAETE, alt, neu)
    meldungen = wv.pruefe(projekt)
    assert meldungen and all("Commit site" in m for m in meldungen), meldungen
    assert any(meldung in m for m in meldungen), meldungen


@pytest.mark.parametrize(
    ("pfad", "alt", "neu", "art"),
    [
        (wv.GERAETE, "|| 1500 }}", "|| 1800 }}", "Cron-Rückfall 1800.0"),
        (wv.GERAETE, 'default: "1500"', 'default: "1200"', "workflow_dispatch-Vorgabe"),
        (
            wv.GERAETE_PIPELINE,
            "FRIST_TAGESLAUF = 1500.0",
            "FRIST_TAGESLAUF = 900.0",
            "",
        ),
    ],
)
def test_frist_an_zwei_stellen_ist_rot(projekt, pfad, alt, neu, art):
    _ersetze(projekt, pfad, alt, neu)
    meldungen = wv.pruefe(projekt)
    assert meldungen and all("FRIST_TAGESLAUF" in m for m in meldungen), meldungen
    assert any(art in m for m in meldungen), meldungen


def test_fehlender_cron_rueckfall_ist_rot(projekt):
    _ersetze(
        projekt, wv.GERAETE, '--frist "${{ github.event.inputs.frist || 1500 }}"', ""
    )
    assert wv.pruefe(projekt) == [
        ".github/workflows/geraete.yml: Cron-Rückfall None ≠ FRIST_TAGESLAUF 1500.0"
    ]


def test_buendelwaechter_nicht_zuletzt_ist_rot(projekt):
    _ersetze(
        projekt,
        wv.GERAETE,
        "geraete_abdeckungswaechter.py\n",
        "geraete_abdeckungswaechter.py\n      - name: Danach\n"
        "        if: steps.heute.outputs.fertig != 'true'\n        run: echo\n",
    )
    meldungen = wv.pruefe(projekt)
    assert any(
        "letzter Schritt ist nicht 'Buendelabdeckung pruefen'" in m for m in meldungen
    )


def test_buendelwaechter_mit_maildaten_ist_rot(projekt):
    _ersetze(
        projekt,
        wv.GERAETE,
        "geraete_abdeckungswaechter.py\n",
        "geraete_abdeckungswaechter.py\n        env:\n          SMTP_HOST: x\n",
    )
    assert wv.pruefe(projekt) == [
        ".github/workflows/geraete.yml: der Bündelwächter bekommt Mail-Zugangsdaten"
    ]


def test_buendelwaechter_nur_bei_erfolg_ist_rot(projekt):
    _ersetze(projekt, wv.GERAETE, "if: always() && ", "if: ")
    assert wv.pruefe(projekt) == [
        ".github/workflows/geraete.yml: der Bündelwächter läuft nicht immer"
    ]


def test_zwei_termine_sind_zu_wenig(projekt):
    _ersetze(projekt, wv.GERAETE, '    - cron: "47 15 * * *"\n', "")
    assert wv.pruefe(projekt) == [
        ".github/workflows/geraete.yml: 2 Termine, mindestens 3"
    ]


def test_schritt_ohne_heute_bedingung_ist_rot(projekt):
    _ersetze(
        projekt,
        wv.GERAETE,
        "      - name: Render site\n        if: steps.heute.outputs.fertig != 'true'\n",
        "      - name: Render site\n",
    )
    assert wv.pruefe(projekt) == [
        ".github/workflows/geraete.yml: Schritt 'Render site' läuft auch, wenn heute"
        " schon gemessen ist"
    ]


def test_fehlender_workflow_ist_rot(projekt):
    (projekt / wv.GERAETE).unlink()
    meldungen = wv.pruefe(projekt)
    assert meldungen and all("nicht prüfbar" in m for m in meldungen)
    assert len(meldungen) == len(wv.REGELN) - 1


def test_fehlende_ordner_claude_md_ist_rot(projekt):
    (projekt / wv.waechter_claude.ORDNER_CLAUDE_MD[2] / "CLAUDE.md").unlink()
    assert wv.pruefe(projekt) == ["src/telco_radar/report/CLAUDE.md fehlt"]
