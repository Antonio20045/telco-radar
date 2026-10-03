import importlib
import json
import os
import signal
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
geaenderte_tests = importlib.import_module("geaenderte_tests")
leiter_schnell = importlib.import_module("leiter_schnell")

GROSS = "tests/test_gross.py"
INHALT = """import pytest

GRENZE = 3


def _hilfe():
    return 1


def _kette():
    return _hilfe()


@pytest.fixture(autouse=True)
def _auto():
    yield


def test_a():
    assert True


@pytest.mark.parametrize("x", [1, 2])
def test_b(x):
    assert x


def test_c():
    assert _hilfe() == 1


def test_e():
    assert _kette()


class TestGruppe:
    def test_d(self):
        assert GRENZE
"""


def _git(ort, *argumente):
    rein = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid", *argumente],
        cwd=ort,
        env=rein,
        capture_output=True,
        check=True,
    )


@pytest.fixture()
def repo(tmp_path):
    (tmp_path / "tests").mkdir()
    (tmp_path / GROSS).write_text(INHALT, "utf-8")
    _git(tmp_path, "init", "-q", "-b", "main")
    _git(tmp_path, "add", GROSS)
    _git(tmp_path, "commit", "-q", "-m", "a")
    return tmp_path


def _aendere(repo, alt, neu):
    datei = repo / GROSS
    datei.write_text(datei.read_text("utf-8").replace(alt, neu, 1), "utf-8")


def test_unveraendert_ist_kein_test_geaendert(repo):
    assert geaenderte_tests.geaenderte_tests(repo, [GROSS]) == []


def test_geaenderte_zeile_trifft_ihren_test(repo):
    _aendere(repo, "assert x\n", "assert not x\n")
    assert geaenderte_tests.geaenderte_tests(repo, [GROSS]) == [f"{GROSS}::test_b"]


def test_geaenderter_dekorator_trifft_seinen_test(repo):
    _aendere(repo, "[1, 2]", "[1, 0]")
    assert geaenderte_tests.geaenderte_tests(repo, [GROSS]) == [f"{GROSS}::test_b"]


def test_geaenderte_hilfe_und_konstante_treffen_ihre_nutzer(repo):
    _aendere(repo, "return 1", "return 2")
    _aendere(repo, "GRENZE = 3", "GRENZE = 0")
    assert geaenderte_tests.geaenderte_tests(repo, [GROSS]) == [
        f"{GROSS}::TestGruppe",
        f"{GROSS}::test_c",
        f"{GROSS}::test_e",
    ]


def test_autouse_und_anweisung_ohne_namen_treffen_die_ganze_datei(repo):
    _aendere(repo, "    yield\n", "    raise RuntimeError\n    yield\n")
    assert geaenderte_tests.geaenderte_tests(repo, [GROSS]) == [f"{GROSS}::"]
    _git(repo, "checkout", "--", GROSS)
    _aendere(repo, "GRENZE = 3\n", "GRENZE = 3\nprint(GRENZE)\n")
    assert geaenderte_tests.geaenderte_tests(repo, [GROSS]) == [f"{GROSS}::"]


def test_farbiger_oder_fremder_diff_aendert_nichts(repo):
    _git(repo, "config", "color.diff", "always")
    _git(repo, "config", "diff.external", "false")
    _aendere(repo, "assert x\n", "assert not x\n")
    assert geaenderte_tests.geaenderte_tests(repo, [GROSS]) == [f"{GROSS}::test_b"]


def test_geloeschte_zeile_trifft_ihren_test(repo):
    _aendere(repo, '@pytest.mark.parametrize("x", [1, 2])\n', "")
    assert geaenderte_tests.geaenderte_tests(repo, [GROSS]) == [f"{GROSS}::test_b"]


def test_neue_und_kaputte_dateien_gelten_ganz(repo):
    neu = "tests/test_neu.py"
    (repo / neu).write_text("def test_x():\n    pass\n", "utf-8")
    assert geaenderte_tests.geaenderte_tests(repo, [neu]) == [f"{neu}::"]
    _aendere(repo, "def test_a():", "def test_a(:")
    assert geaenderte_tests.geaenderte_tests(repo, [GROSS]) == [f"{GROSS}::"]


@pytest.mark.parametrize(
    ("nodeid", "erwartet"),
    [
        (f"{GROSS}::test_b", True),
        (f"{GROSS}::test_b[1]", True),
        (f"{GROSS}::TestGruppe::test_d", True),
        (f"{GROSS}::test_bc", False),
        (f"{GROSS}::test_a", False),
        ("tests/test_neu.py::test_x", True),
        ("tests/test_neu2.py::test_x", False),
    ],
)
def test_nodeid_gehoert_zu_seinem_praefix(nodeid, erwartet):
    praefixe = [f"{GROSS}::test_b", f"{GROSS}::TestGruppe", "tests/test_neu.py::"]
    assert geaenderte_tests.ist_geaendert(nodeid, praefixe) is erwartet


def _stufe_vier(repo, gemessen, *ausgaenge, stdout=""):
    zeiten = repo / "zeiten.json"
    zeiten.write_text(json.dumps({"tests": gemessen}), "utf-8")
    aufrufe = []
    kappe = f"\n{leiter_schnell.ABGEBROCHEN}\n"

    def lauf(log, befehl, zusatz=None, frist=None):
        aufrufe.append((befehl, frist))
        code = ausgaenge[len(aufrufe) - 1] if len(aufrufe) <= len(ausgaenge) else 0
        fehler = kappe if code == -signal.SIGKILL else ""
        return subprocess.CompletedProcess(befehl, code, stdout, fehler)

    ergebnis = leiter_schnell.stufe_betroffen(None, lauf, repo, [GROSS], zeiten)
    return ergebnis, aufrufe


def _ziele(befehl):
    return befehl[befehl.index(leiter_schnell.OHNE_MARKER) + 3 :]


def _abgewaehlt(befehl):
    return [a.removeprefix("--deselect=") for a in befehl if a.startswith("--desel")]


def test_geaenderter_langsamer_test_wird_nicht_abgewaehlt(repo):
    langsam = leiter_schnell.LANGSAM_SEKUNDEN + 1
    _aendere(repo, "assert x\n", "assert not x\n")
    gemessen = {f"{GROSS}::test_b[1]": langsam, f"{GROSS}::test_a": langsam}
    ergebnis, [(befehl, _)] = _stufe_vier(repo, gemessen)
    assert ergebnis.gruen
    assert _abgewaehlt(befehl) == [f"{GROSS}::test_a"]
    assert ergebnis.hinweise == [
        "Stufe 4: 1 langsame oder über 8 s Budget, Stufe 5 im pre-push"
    ]


def test_geaenderter_test_ueber_dem_budget_wird_nicht_abgewaehlt(repo, monkeypatch):
    monkeypatch.setattr(leiter_schnell, "TESTBUDGET_SEKUNDEN", 1.0)
    _aendere(repo, "return 1", "return 2")
    gruppe = f"{GROSS}::TestGruppe::test_d"
    gemessen = {gruppe: 0.2, f"{GROSS}::test_a": 0.3, f"{GROSS}::test_c": 0.9}
    _, [(befehl, _)] = _stufe_vier(repo, gemessen)
    assert _abgewaehlt(befehl) == [f"{GROSS}::test_a"]


def test_nach_der_kappe_laufen_die_geaenderten_tests_allein(repo):
    _aendere(repo, "return 1", "return 2")
    gemessen = {f"{GROSS}::test_c": 5.0, f"{GROSS}::test_a": 0.1}
    ergebnis, [_, (nachlauf, frist)] = _stufe_vier(repo, gemessen, -signal.SIGKILL)
    assert ergebnis.gruen
    assert _ziele(nachlauf) == [f"{GROSS}::test_c", f"{GROSS}::test_e"]
    assert "-n" in nachlauf and nachlauf[nachlauf.index("-n") + 1] == "4"
    assert frist == geaenderte_tests.NACHLAUF_SEKUNDEN


def test_roter_nachlauf_macht_stufe_vier_rot(repo):
    _aendere(repo, "assert x\n", "assert not x\n")
    zeile = f"FAILED {GROSS}::test_b[1] - assert not 1"
    ergebnis, _ = _stufe_vier(repo, {}, -signal.SIGKILL, 1, stdout=f"..F\n{zeile}\n")
    assert not ergebnis.gruen
    assert ergebnis.zeilen == [zeile]


def test_abgebrochener_nachlauf_ist_rot(repo):
    _aendere(repo, "assert x\n", "assert not x\n")
    ergebnis, _ = _stufe_vier(repo, {}, -signal.SIGKILL, -signal.SIGKILL)
    assert not ergebnis.gruen
    assert ergebnis.zeilen[0] == "geänderte Tests: pytest endet mit -9:"


def test_kappe_ohne_geaenderte_tests_bleibt_eine_warnung(repo):
    ergebnis, aufrufe = _stufe_vier(repo, {}, -signal.SIGKILL)
    assert ergebnis.gruen
    assert len(aufrufe) == 1


def test_abwahl_als_praefix_eines_geaenderten_tests_entfaellt():
    praefixe = [f"{GROSS}::test_ab", f"{GROSS}::test_x"]
    nodeids = [f"{GROSS}::test_a", f"{GROSS}::test_c", f"{GROSS}::test_x[1]"]
    assert geaenderte_tests.ohne(nodeids, praefixe) == [f"{GROSS}::test_c"]


def test_roter_geaenderter_test_mit_abgewaehltem_praefix_ist_rot(repo):
    datei = repo / "tests" / "test_praefix.py"
    datei.write_text("def test_a():\n    pass\n\n\ndef test_ab():\n    pass\n")
    _git(repo, "add", "tests/test_praefix.py")
    _git(repo, "commit", "-q", "-m", "b")
    datei.write_text(
        datei.read_text()
        .replace("pass\n", "assert 0\n")
        .replace("assert 0\n", "pass\n", 1)
    )
    zeiten = repo / "zeiten.json"
    langsam = leiter_schnell.LANGSAM_SEKUNDEN + 1
    gemessen = {"tests/test_praefix.py::test_a": langsam}
    zeiten.write_text(json.dumps({"tests": gemessen}), "utf-8")

    def lauf(log, befehl, zusatz=None, frist=None):
        rein = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
        return subprocess.run(
            befehl, cwd=repo, env=rein, capture_output=True, text=True
        )

    ergebnis = leiter_schnell.stufe_betroffen(
        None, lauf, repo, ["tests/test_praefix.py"], zeiten
    )
    assert not ergebnis.gruen
    assert ergebnis.zeilen[0].startswith("FAILED tests/test_praefix.py::test_ab")


@pytest.mark.parametrize("name", ["setup_module", "pytest_generate_tests"])
def test_modulweite_hooks_treffen_die_ganze_datei(repo, name):
    _aendere(repo, "def _kette():", f"def {name}(*a):\n    pass\n\n\ndef _kette():")
    _git(repo, "commit", "-q", "-am", "c")
    _aendere(repo, f"def {name}(*a):\n    pass", f"def {name}(*a):\n    raise KeyError")
    assert geaenderte_tests.geaenderte_tests(repo, [GROSS]) == [f"{GROSS}::"]


def test_lokale_namen_einer_hilfe_ziehen_keine_fremden_tests(repo):
    _aendere(
        repo, "def _hilfe():\n    return 1", "def _hilfe():\n    x = 1\n    return x"
    )
    assert geaenderte_tests.geaenderte_tests(repo, [GROSS]) == [
        f"{GROSS}::test_c",
        f"{GROSS}::test_e",
    ]
