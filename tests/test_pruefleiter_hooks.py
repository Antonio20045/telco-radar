import importlib
import io
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

pruefleiter = importlib.import_module("pruefleiter")
waechter_vertraege = importlib.import_module("waechter_vertraege")


def _gruen(log):
    return pruefleiter.Ergebnis("0 Wächter", True)


@pytest.fixture()
def lauf_ordner(tmp_path, monkeypatch):
    monkeypatch.setattr(pruefleiter, "LAUF_ORDNER", tmp_path)
    return tmp_path


def test_vor_push_bricht_vor_den_stufen_ab(lauf_ordner, monkeypatch, capsys):
    gestartet = []
    monkeypatch.setattr(pruefleiter, "STUFEN_PUSH", [gestartet.append])
    monkeypatch.setattr(
        pruefleiter.pruefstempel,
        "vor_push",
        lambda w, z: (1, "pre-push: origin/main ist neuer"),
    )
    monkeypatch.setattr(sys, "stdin", io.StringIO("x y z w\n"))
    assert pruefleiter.main(["--vor-push", "origin", "url"]) == 1
    assert gestartet == []
    assert capsys.readouterr().out.startswith("pre-push: origin/main ist neuer")


def test_vor_push_laeuft_push_stufen_und_stempelt_nicht(lauf_ordner, monkeypatch):
    monkeypatch.setattr(pruefleiter, "STUFEN_PUSH", [_gruen])
    monkeypatch.setattr(pruefleiter, "STUFEN_VOLL", [lambda log: pytest.fail("voll")])
    monkeypatch.setattr(pruefleiter.pruefstempel, "vor_push", lambda w, z: None)
    monkeypatch.setattr(
        pruefleiter.pruefstempel, "stemple_lauf", lambda *a: pytest.fail("Stempel")
    )
    monkeypatch.setattr(sys, "stdin", io.StringIO(""))
    assert pruefleiter.main(["--vor-push"]) == 0
    assert "--vor-push" in (lauf_ordner / "zeiten.csv").read_text("utf-8")


def test_push_stufe_faehrt_nur_die_betroffenen_tests(monkeypatch):
    leiter_push = importlib.import_module("leiter_push")
    monkeypatch.setattr(leiter_push, "geaendert", lambda w: ["src/a.py"])
    auswahl = leiter_push.leiter_schnell.Auswahl(dateien=["tests/test_a.py"])
    monkeypatch.setattr(leiter_push.leiter_schnell, "betroffene", lambda w, d: auswahl)
    befehle = []

    def lauf(log, befehl, zusatz):
        befehle.append(befehl)
        return pruefleiter.subprocess.CompletedProcess(befehl, 0, "", "")

    def voll(log):
        pytest.fail("Volllauf trotz betroffener Einzeldateien")

    ergebnis = leiter_push.stufe(io.StringIO(), Path("."), lauf, voll, 300)
    assert ergebnis.gruen
    assert befehle[0][-1] == "tests/test_a.py"
    assert "tests" not in befehle[0]


def test_push_stufe_faehrt_alles_wenn_alle_betroffen(monkeypatch):
    leiter_push = importlib.import_module("leiter_push")
    monkeypatch.setattr(leiter_push, "geaendert", lambda w: ["config/a.yaml"])
    auswahl = leiter_push.leiter_schnell.Auswahl(alle=["config/a.yaml"])
    monkeypatch.setattr(leiter_push.leiter_schnell, "betroffene", lambda w, d: auswahl)
    voll = []
    leiter_push.stufe(io.StringIO(), Path("."), None, voll.append, 300)
    assert len(voll) == 1


def test_roter_volllauf_stempelt_nicht(lauf_ordner, monkeypatch):
    def rot(log):
        return pruefleiter.Ergebnis("5 Voll", False, ["FAILED t.py::t"])

    monkeypatch.setattr(pruefleiter, "STUFEN_VOLL", [_gruen, rot])
    monkeypatch.setattr(pruefleiter.pruefstempel, "baum_oder_nichts", lambda w: "b")
    gestempelt = []
    monkeypatch.setattr(
        pruefleiter.pruefstempel,
        "stemple_lauf",
        lambda *a: gestempelt.append(a) or "",
    )
    assert pruefleiter.main(["--voll"]) == 1
    assert gestempelt == []


def test_statischer_lauf_stempelt_nicht(lauf_ordner, monkeypatch):
    monkeypatch.setattr(pruefleiter, "STUFEN_STATISCH", [_gruen])
    monkeypatch.setattr(
        pruefleiter.pruefstempel, "stemple_lauf", lambda *a: pytest.fail("Stempel")
    )
    assert pruefleiter.main(["--statisch"]) == 0


def test_schneller_lauf_nimmt_die_vorgemerkten_dateien(lauf_ordner, monkeypatch):
    gefragt = []

    def dateien(wurzel, nur_vorgemerkt):
        gefragt.append(nur_vorgemerkt)
        return []

    monkeypatch.setattr(pruefleiter.leiter_schnell, "geaenderte_dateien", dateien)
    monkeypatch.setattr(pruefleiter, "stufe_waechter", _gruen)
    assert pruefleiter.main(["--schnell", "--nur-vorgemerkt"]) == 0
    assert gefragt == [True]
    zeilen = (lauf_ordner / "zeiten.csv").read_text("utf-8").splitlines()
    assert [z.split(",")[1] for z in zeilen] == [
        "--pre-commit",
        "0 Wächter",
        "1 Lint",
        "4 Betroffen",
    ]


def test_werkzeuge_sehen_keine_git_umgebung_eines_hooks():
    umgebung = pruefleiter.umgebung(
        {"GIT_INDEX_FILE": ".git/index.lock", "GIT_DIR": ".git", "HOME": "/h"}
    )
    assert "GIT_INDEX_FILE" not in umgebung
    assert "GIT_DIR" not in umgebung
    assert umgebung["HOME"] == "/h"


def _hooks(wurzel, **inhalte):
    ordner = wurzel / ".githooks"
    ordner.mkdir()
    for name, text in inhalte.items():
        datei = ordner / name.replace("_", "-")
        datei.write_text(text, "utf-8")
        datei.chmod(0o755)
    return ordner


def test_hooks_der_leiter_sind_gruen(tmp_path):
    inhalt = waechter_vertraege.HOOK_INHALT
    _hooks(tmp_path, pre_commit=inhalt["pre-commit"], pre_push=inhalt["pre-push"])
    assert waechter_vertraege.git_hooks(tmp_path) == []


def test_fehlende_hooks_sind_kein_vertragsbruch(tmp_path):
    assert waechter_vertraege.git_hooks(tmp_path) == []


def test_ausgehebelter_hook_ist_rot(tmp_path):
    inhalt = waechter_vertraege.HOOK_INHALT
    ordner = _hooks(
        tmp_path, pre_commit="#!/bin/sh\nexit 0\n", pre_push=inhalt["pre-push"]
    )
    (ordner / "pre-push").chmod(0o644)
    (ordner / "post-commit").write_text("#!/bin/sh\n", "utf-8")
    assert waechter_vertraege.git_hooks(tmp_path) == [
        ".githooks/pre-commit weicht vom Hook der Leiter ab",
        ".githooks/pre-push ist nicht ausführbar",
        ".githooks/post-commit ist kein Hook der Leiter",
    ]


def test_vor_push_mit_roter_stufe_ist_rot(lauf_ordner, monkeypatch):
    def rot(log):
        return pruefleiter.Ergebnis("5 Push", False, ["FAILED t.py::t"])

    monkeypatch.setattr(pruefleiter, "STUFEN_PUSH", [rot])
    monkeypatch.setattr(pruefleiter.pruefstempel, "vor_push", lambda w, z: None)
    monkeypatch.setattr(sys, "stdin", io.StringIO(""))
    assert pruefleiter.main(["--vor-push"]) == 1
