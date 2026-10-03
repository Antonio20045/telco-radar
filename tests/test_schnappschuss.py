"""scripts/schnappschuss.py zieht Bestand nur aus Bot-Commits und ändert keinen Ordner;
Stufe 0 hält jeden Schnappschuss gegen seine ``_herkunft.json``."""

import hashlib
import importlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

schnappschuss = importlib.import_module("schnappschuss")
waechter_tests = importlib.import_module("waechter_tests")

_HISTORIE = (
    '{"id": "a--iphone", "datum": "2026-01-01"}\n'
    '{"id": "a--pixel", "datum": "2026-01-01"}\n'
    '{"id": "b--iphone", "datum": "2026-01-02"}\n'
)


def _git(wurzel, *argumente, autor="telco-radar-bot"):
    umgebung = {
        "GIT_AUTHOR_NAME": autor,
        "GIT_AUTHOR_EMAIL": "bot@example.org",
        "GIT_COMMITTER_NAME": autor,
        "GIT_COMMITTER_EMAIL": "bot@example.org",
        "GIT_COMMITTER_DATE": "2026-01-02T23:30:00-02:00",
        "PATH": "/usr/bin:/bin",
        "HOME": str(wurzel),
    }
    return subprocess.run(
        ["git", *argumente],
        cwd=wurzel,
        env=umgebung,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


@pytest.fixture()
def repo(tmp_path):
    wurzel = tmp_path / "repo"
    for pfad, text in {
        "data/state/a.json": '{"a": 1}\n',
        "data/state/historie.jsonl": _HISTORIE,
        "data/reports/2026-01-01.json": "{}\n",
        "data/reports/2026-01-02.json": '{"neu": 1}\n',
        "data/reports/2026-01-02.md": "# Bericht\n",
        "data/reports/promo/2026-01-02.md": "# Promo\n",
    }.items():
        (wurzel / pfad).parent.mkdir(parents=True, exist_ok=True)
        (wurzel / pfad).write_text(text, encoding="utf-8")
    _git(wurzel, "init", "-q")
    _git(wurzel, "add", "-A")
    _git(wurzel, "commit", "-q", "-m", "radar: run")
    return wurzel


def test_zieht_dateien_filtert_zeilen_und_schreibt_die_herkunft(repo):
    ordner = schnappschuss.ziehe(
        "HEAD", ["data/state/a.json"], {"data/state/historie.jsonl": "iphone"}, repo
    )
    assert ordner == repo / "tests/fixtures/bestand/2026-01-03"
    assert (ordner / "state/historie.jsonl").read_text() == (
        '{"id": "a--iphone", "datum": "2026-01-01"}\n'
        '{"id": "b--iphone", "datum": "2026-01-02"}\n'
    )
    herkunft = json.loads((ordner / "_herkunft.json").read_text())
    assert herkunft["commit"] == _git(repo, "rev-parse", "HEAD")
    assert herkunft["autor"] == "telco-radar-bot"
    assert herkunft["zeit"] == "2026-01-03T01:30:00+00:00"
    assert sorted(herkunft["dateien"]) == [
        "reports/2026-01-02.json",
        "reports/2026-01-02.md",
        "reports/promo/2026-01-02.md",
        "state/a.json",
        "state/historie.jsonl",
    ]
    eintrag = herkunft["dateien"]["state/historie.jsonl"]
    assert eintrag["quelle"] == "data/state/historie.jsonl"
    assert eintrag["filter"] == "iphone"
    roh = (ordner / "state/historie.jsonl").read_bytes()
    assert eintrag["sha256"] == hashlib.sha256(roh).hexdigest()
    assert herkunft["dateien"]["state/a.json"]["filter"] is None
    assert (
        waechter_tests.tests_zaehlung(repo)[
            ("tests/fixtures/bestand/2026-01-03", "schnappschuss-veraendert")
        ]
        == 0
    )


def test_kein_bot_commit_wird_abgelehnt(repo):
    (repo / "data/state/a.json").write_text("{}\n")
    _git(repo, "commit", "-qam", "von Hand", autor="Jemand")
    with pytest.raises(schnappschuss.SchnappschussFehler, match="kein Bot-Commit"):
        schnappschuss.ziehe("HEAD", ["data/state/a.json"], {}, repo)


def test_vorhandener_schnappschuss_wird_nie_geaendert(repo):
    schnappschuss.ziehe("HEAD", ["data/state/a.json"], {}, repo)
    vorher = (repo / "tests/fixtures/bestand/2026-01-03/_herkunft.json").read_text()
    with pytest.raises(schnappschuss.SchnappschussFehler, match="nur ersetzen"):
        schnappschuss.ziehe("HEAD", ["data/state/historie.jsonl"], {}, repo)
    assert (repo / "tests/fixtures/bestand/2026-01-03/_herkunft.json").read_text() == (
        vorher
    )


def test_nur_dateien_unter_data(repo):
    with pytest.raises(schnappschuss.SchnappschussFehler, match="nicht unter data/"):
        schnappschuss.ziehe("HEAD", ["src/x.py"], {}, repo)
    assert not (repo / "tests/fixtures/bestand").exists()


def test_main_meldet_den_fehler_mit_exit_1(repo, monkeypatch, capsys):
    monkeypatch.setattr(schnappschuss, "WURZEL", repo)
    monkeypatch.setattr(
        schnappschuss,
        "ziehe",
        lambda *a: (_ for _ in ()).throw(schnappschuss.SchnappschussFehler("x")),
    )
    assert schnappschuss.main(["HEAD"]) == 1
    assert "Schnappschuss nicht gezogen: x" in capsys.readouterr().err


@pytest.mark.parametrize(
    ("eingriff", "anzahl"),
    [
        (lambda o: (o / "state/a.json").write_text('{"a": 2}\n'), 2),
        (lambda o: (o / "state/neu.json").write_text("{}\n"), 1),
        (lambda o: (o / "state/a.json").unlink(), 1),
        (lambda o: (o / "_herkunft.json").write_text("kaputt"), 1),
    ],
)
def test_veraenderter_schnappschuss_zaehlt_in_stufe_0(repo, eingriff, anzahl):
    ordner = schnappschuss.ziehe("HEAD", ["data/state/a.json"], {}, repo)
    eingriff(ordner)
    zaehlung = waechter_tests.tests_zaehlung(repo)
    schluessel = ("tests/fixtures/bestand/2026-01-03", "schnappschuss-veraendert")
    assert zaehlung[schluessel] == anzahl
