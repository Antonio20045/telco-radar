import importlib
import os
import subprocess
import sys
from collections import Counter
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
mutation = importlib.import_module("mutation")

KERN = "def verdopple(x):\n    return x\n\n\ndef bleibt(x):\n    return x + 1\n"
GEBAUT = "def verdopple(x):\n    return x * 2\n\n\ndef bleibt(x):\n    return x + 1\n"
TEST = (
    "from telco_radar.kern import verdopple\n\n\n"
    "def test_verdopple():\n    assert verdopple(3) > 3\n"
)


def _git(ort, *argumente):
    umgebung = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    subprocess.run(["git", *argumente], cwd=ort, env=umgebung, check=True)


@pytest.fixture
def repo(tmp_path):
    wurzel = tmp_path / "repo"
    dateien = {
        ".gitignore": ".venv\n",
        "pyproject.toml": '[tool.pytest.ini_options]\npythonpath = ["src"]\n',
        "src/telco_radar/__init__.py": "",
        "src/telco_radar/kern.py": KERN,
        "tests/test_kern.py": TEST,
    }
    for name, text in dateien.items():
        (wurzel / name).parent.mkdir(parents=True, exist_ok=True)
        (wurzel / name).write_text(text)
    _python(wurzel, sys.executable)
    _git(wurzel, "init", "-q", "-b", "main")
    _git(wurzel, "config", "user.name", "Mensch")
    _git(wurzel, "config", "user.email", "m@example.invalid")
    _git(wurzel, "add", "--", *dateien)
    _git(wurzel, "commit", "-q", "-m", "Start")
    return wurzel


def _python(wurzel, ziel):
    python = wurzel / ".venv/bin/python"
    python.parent.mkdir(parents=True, exist_ok=True)
    python.write_text(f'#!/bin/sh\nexec {ziel} "$@"\n')
    python.chmod(0o755)


def _bauen(repo, text=GEBAUT):
    (repo / "src/telco_radar/kern.py").write_text(text)
    _git(repo, "commit", "-q", "-am", "Bau")


def test_neue_zeilen_nimmt_den_rand_einer_reinen_loeschung():
    diff = "@@ -3,0 +4,2 @@\n+a\n+b\n@@ -9 +11 @@\n-x\n+y\n@@ -20,2 +21,0 @@\n"

    assert mutation.neue_zeilen(diff) == {4, 5, 11, 21}


def test_funktionen_nennt_nur_beruehrte_funktionen_und_methoden():
    quelle = (
        "X = 1\n"
        "def a():\n"
        "    def innen():\n"
        "        return 1\n"
        "    return innen\n"
        "class K:\n"
        "    @staticmethod\n"
        "    def m():\n"
        "        return 2\n"
        "    def n(self):\n"
        "        return 3\n"
    )

    assert mutation.funktionen(quelle, {4, 7}) == ["x_a", "xǁKǁm"]
    assert mutation.funktionen(quelle, {1, 6}) == []
    assert mutation.funktionen(quelle, {11}) == ["xǁKǁn"]


def test_urteil_zaehlt_erkannte_und_nennt_ueberlebende():
    ausgabe = (
        "    telco_radar.kern.x_verdopple__mutmut_1: killed\n"
        "    telco_radar.kern.x_verdopple__mutmut_2: survived\n"
        "    telco_radar.kern.x_bleibt__mutmut_1: not checked\n"
    )
    muster = ["telco_radar.kern.x_verdopple__mutmut_*"]

    zustaende, fremd = mutation.auszaehlen(ausgabe, muster)

    assert zustaende == Counter({"killed": 1, "survived": 1})
    assert fremd == []
    text = mutation.urteil(zustaende, fremd, ausgabe)
    assert text == "1 von 2 Mutanten erkannt, überlebt: verdopple#2"


@pytest.mark.parametrize(
    ("zustaende", "fremd", "grund"),
    [
        (Counter({"killed": 1}), ["telco_radar.kern.x_bleibt__mutmut_1"], "nicht gew"),
        (Counter(), [], "keine Mutanten"),
        (Counter({"killed": 1, "suspicious": 1}), [], "ohne Ergebnis (suspicious)"),
    ],
)
def test_urteil_laesst_die_pruefung_mit_grund_entfallen(zustaende, fremd, grund):
    text = mutation.urteil(zustaende, fremd, "")

    assert text.startswith("entfällt: ")
    assert grund in text


def test_kurzname_kuerzt_methoden_und_funktionen():
    assert mutation.kurzname("a.b.xǁKǁm__mutmut_3") == "K.m#3"
    assert mutation.kurzname("a.b.x_f__mutmut_12") == "f#12"


def test_probe_laeuft_nur_auf_der_geaenderten_funktion(repo, tmp_path):
    _bauen(repo)
    protokoll = tmp_path / "mutation.log"

    probe = mutation.probe(repo, "HEAD~1", protokoll)

    assert probe.exit == 0, protokoll.read_text()
    assert probe.sekunden > 0
    assert probe.ergebnis.startswith("1 von 2 Mutanten erkannt, überlebt: verdopple#")
    assert "x_bleibt__mutmut_1: not checked" in protokoll.read_text()
    assert (
        subprocess.run(
            ["git", "worktree", "list"], cwd=repo, capture_output=True, text=True
        ).stdout.count("\n")
        == 1
    ), "der Wegwerf-Worktree ist wieder weg"


@pytest.mark.parametrize(
    ("vorbereitung", "grund"),
    [
        ("ohne_funktion", "entfällt: keine geänderte Funktion unter src/"),
        ("ohne_test", "entfällt: kein Test importiert die geänderten Module"),
        ("frist", "entfällt: mutmut nach 0 s abgebrochen"),
        ("ohne_mutmut", "entfällt: mutmut fehlt im .venv"),
        ("roter_test", "entfällt: mutmut Exit 1 (failed to collect stats"),
    ],
)
def test_probe_nennt_den_grund_wenn_sie_nicht_laufen_kann(
    repo, tmp_path, vorbereitung, grund
):
    frist = mutation.FRIST
    if vorbereitung == "ohne_funktion":
        _bauen(repo, KERN + "\nY = 2\n")
    elif vorbereitung == "ohne_test":
        (repo / "tests/test_kern.py").write_text("def test_nichts():\n    pass\n")
        _bauen(repo)
    elif vorbereitung == "ohne_mutmut":
        leer = tmp_path / "leer"
        subprocess.run(
            [sys.executable, "-m", "venv", "--without-pip", leer], check=True
        )
        _python(repo, leer / "bin/python")
        _bauen(repo)
    elif vorbereitung == "roter_test":
        _bauen(repo, GEBAUT.replace("x * 2", "x * 0"))
    else:
        frist = 0.01
        _bauen(repo)

    probe = mutation.probe(repo, "HEAD~1", tmp_path / "mutation.log", frist)

    assert probe.ergebnis.startswith(grund), probe.ergebnis


@pytest.mark.parametrize(
    ("mutation", "echt", "erfuellt"),
    [
        ({"ergebnis": "3 von 4 Mutanten erkannt", "sekunden": "12.5"}, True, True),
        ({"ergebnis": "entfällt: mutmut fehlt im .venv", "sekunden": ""}, True, True),
        ({"ergebnis": "entfällt: ", "sekunden": "3"}, True, False),
        ({"ergebnis": "3 von 4 Mutanten erkannt", "sekunden": "0"}, True, False),
        ({"ergebnis": "erkannt", "sekunden": "4"}, True, False),
        ({"ergebnis": "3 von 4 Mutanten erkannt", "sekunden": "12.5"}, False, False),
        (None, True, False),
    ],
)
def test_stand_schritt_6_verlangt_eine_mutationsprobe_mit_zeit_oder_grund(
    tmp_path, monkeypatch, mutation, echt, erfuellt
):
    stand = importlib.import_module("stand")
    monkeypatch.setattr(stand, "W", tmp_path)
    format_ = stand.auftrag_format
    leer = dict.fromkeys(format_.SPALTEN, "") | {"auftrag": "M1", "agent": "claude"}
    kosten = {"modell": "claude-opus-x", "kosten_usd": "0.4"}
    zeilen = [leer | kosten | {"rolle": r} for r in ("bau", "pruefer")]
    if not echt:
        zeilen[1]["modell"] = "ersatz"
    if mutation is not None:
        zeilen.append(leer | {"rolle": "mutation", "agent": "mutmut"} | mutation)
    zeilen.append(leer | {"rolle": "ende", "ergebnis": format_.GEMERGT})
    format_.kosten_schreiben(zeilen, tmp_path)

    gruende = stand.mutationsprobe()

    assert (gruende == []) is erfuellt, gruende


def test_probe_nennt_einen_git_fehler_statt_abzubrechen(tmp_path):
    probe = mutation.probe(tmp_path, "HEAD~1", tmp_path / "mutation.log")

    assert probe.ergebnis.startswith("gescheitert: git diff"), probe.ergebnis
    stand = importlib.import_module("stand")
    zeile = {"ergebnis": probe.ergebnis, "sekunden": str(probe.sekunden)}
    assert not stand._probe_belegt(zeile), "ein git-Fehler belegt keine Probe"
