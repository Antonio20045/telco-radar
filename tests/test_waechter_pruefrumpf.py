"""Stufe 0: Eine neue oder geänderte Testfunktion ohne Prüfung ist rot, auch wenn die
Änderung schon committet ist; unveränderter Bestand bleibt grün."""

import importlib
import os
import subprocess
import sys
from collections import Counter
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
rumpf = importlib.import_module("waechter_pruefrumpf")

BESTAND = (
    "def test_prueft():\n    assert 1 + 1 == 2\n\n\n"
    "def test_alt_ohne():\n    print('Bestand ohne Prüfung')\n\n\n"
    "class TestKlasse:\n    def test_methode(self):\n        assert True\n"
)


def _git(ort, *argumente):
    umgebung = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    kennung = ["-c", "user.name=M", "-c", "user.email=m@x.invalid"]
    subprocess.run(["git", *kennung, *argumente], cwd=ort, env=umgebung, check=True)


@pytest.fixture
def repo(tmp_path):
    wurzel = tmp_path / "repo"
    (wurzel / "tests").mkdir(parents=True)
    (wurzel / "tests/test_a.py").write_text(BESTAND)
    _git(wurzel, "init", "-q", "-b", "main")
    _git(wurzel, "add", "--", "tests/test_a.py")
    _git(wurzel, "commit", "-qm", "Bestand")
    _git(tmp_path, "init", "-q", "--bare", "-b", "main", "origin.git")
    _git(wurzel, "remote", "add", "origin", str(tmp_path / "origin.git"))
    _git(wurzel, "push", "-q", "origin", "main")
    _git(wurzel, "fetch", "-q", "origin")
    return wurzel


def _aendere(repo, alt, neu):
    datei = repo / "tests/test_a.py"
    datei.write_text(datei.read_text().replace(alt, neu))


def test_unveraenderter_bestand_ohne_pruefung_bleibt_gruen(repo):
    assert rumpf.leere_tests(repo) == []


@pytest.mark.parametrize(
    ("alt", "neu", "name"),
    [
        ("    assert 1 + 1 == 2\n", "    pass\n", "test_prueft"),
        ("        assert True\n", "        return\n", "TestKlasse.test_methode"),
        ("print('Bestand ohne Prüfung')", "print('anders')", "test_alt_ohne"),
        (
            "def test_prueft",
            "def test_dummy():\n    pass\n\n\ndef test_prueft",
            "test_dummy",
        ),
    ],
)
def test_geleerter_oder_neuer_test_ohne_pruefung_ist_rot(repo, alt, neu, name):
    _aendere(repo, alt, neu)

    rot = rumpf.leere_tests(repo)

    assert len(rot) == 1 and rot[0].startswith(f"tests/test_a.py::{name} prüft nichts")


def test_geleerter_rumpf_bleibt_rot_nach_dem_commit(repo):
    _aendere(repo, "    assert 1 + 1 == 2\n", "    pass\n")
    _git(repo, "commit", "-qam", "geleert")

    assert len(rumpf.leere_tests(repo)) == 1


@pytest.mark.parametrize(
    "rumpf_neu",
    [
        "    assert 2 == 2\n",
        "    import pytest\n    with pytest.raises(ValueError):\n        int('x')\n",
        "    import pytest\n    pytest.fail('nein')\n",
        "    raise AssertionError('nein')\n",
        "    _assert_gleich(1, 1)\n",
    ],
)
def test_geaenderter_test_mit_pruefung_bleibt_gruen(repo, rumpf_neu):
    _aendere(repo, "    assert 1 + 1 == 2\n", rumpf_neu)

    assert rumpf.leere_tests(repo) == []


def test_verschobener_bestand_bleibt_gruen(repo):
    datei = repo / "tests/test_a.py"
    teile = datei.read_text().split("\n\n\n")
    datei.write_text("\n\n\n".join(reversed(teile)))

    assert rumpf.leere_tests(repo) == []


def test_stufe_null_meldet_den_geleerten_rumpf(repo):
    waechter = importlib.import_module("waechter")
    for basis in (waechter.RIESEN_BASIS, waechter.PRIVAT_BASIS):
        (repo / basis).parent.mkdir(exist_ok=True)
        (repo / basis).write_text("")
    for basis in (waechter.WAECHTER_BASIS, waechter.TESTS_BASIS):
        (repo / basis).write_text("")
    _aendere(repo, "    assert 1 + 1 == 2\n", "    pass\n")

    rot, _ = waechter.pruefe(repo, Counter(), schreiben=False)

    assert any(z.startswith("tests/test_a.py::test_prueft prüft nichts") for z in rot)
