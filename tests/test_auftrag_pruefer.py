"""Ein Prüferbefund zählt nur, wenn seine Reproduktion im Worktree scheitert."""

import importlib
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
pruefer_ = importlib.import_module("auftrag_pruefer")

KOERPER = {
    "rot": "assert 2 == 3, 'Fehlwert als 0'",
    "nackt": "wert = 0\n    assert wert is None",
    "fail": "import pytest\n    pytest.fail('unbekannt als neu')",
    "gruen": "assert True",
    "import": "import gibt_es_nicht",
    "fehler": "raise ValueError('kaputt')",
}


@pytest.fixture
def orte(tmp_path):
    wt, ordner = tmp_path / "wt", tmp_path / "pruefer"
    (wt / ".venv/bin").mkdir(parents=True)
    (wt / "src").mkdir()
    python = wt / ".venv/bin/python"
    python.write_text(f'#!/bin/sh\nexec {sys.executable} "$@"\n')
    python.chmod(0o755)
    ordner.mkdir()
    for art, koerper in KOERPER.items():
        (ordner / f"test_{art}.py").write_text(f"def test_x():\n    {koerper}\n")
    (ordner / "test_sammeln.py").write_text("import gibt_es_nicht\n")
    (tmp_path / "test_draussen.py").write_text("def test_x():\n    assert 0\n")
    return wt, ordner


def _bericht(*befunde):
    return {"result": "Urteil:\n" + json.dumps({"befunde": list(befunde)})}


def _blocker(reproduktion, schwere="blocker"):
    befund = {"schwere": schwere, "datei_zeile": "kern.py:3", "beschreibung": "B"}
    return befund | {"reproduktion": reproduktion}


@pytest.mark.parametrize("art", ["rot", "fail", "nackt"])
def test_fachlich_scheiternde_reproduktion_zaehlt(orte, art):
    wt, ordner = orte
    repro = f"python -m pytest {ordner}/test_{art}.py::test_x"

    urteil = pruefer_.urteilen(_bericht(_blocker(repro)), ordner, wt)

    assert len(urteil.gezaehlt) == 1 and urteil.verworfen == []
    assert "1 Blocker mit scheiternder Reproduktion" in urteil.befund
    assert f"test_{art}.py::test_x" in urteil.befund


@pytest.mark.parametrize(
    ("reproduktion", "grund"),
    [
        ("python -m pytest {o}/test_gruen.py::test_x", "grün"),
        ("python -m pytest {o}/test_import.py", "kein fachliches Scheitern"),
        ("python -m pytest {o}/test_sammeln.py", "Exit 2"),
        ("python -m pytest {o}/test_fehler.py::test_x", "kein fachliches Scheitern"),
        ("", "ohne Reproduktion"),
        (None, "ohne Reproduktion"),
        ("python -m pytest {o}/../test_draussen.py::test_x", "ohne Reproduktion"),
        ("python -m pytest test_rot.py", "ohne Reproduktion"),
        ("python -m pytest {o}/test_rot.py; rm -rf /", "ohne Reproduktion"),
        ("python -m pytest {o}/fehlt.py", "ohne Reproduktion"),
        ("bash -c 'exit 1'", "ohne Reproduktion"),
    ],
)
def test_befund_ohne_fachlich_scheiternde_reproduktion_wird_verworfen(
    orte, reproduktion, grund
):
    wt, ordner = orte
    repro = reproduktion.format(o=ordner) if reproduktion else reproduktion

    urteil = pruefer_.urteilen(_bericht(_blocker(repro)), ordner, wt)

    assert urteil.gezaehlt == [] and urteil.befund == ""
    assert grund in urteil.verworfen[0]


def test_nur_ein_blocker_haelt_den_auftrag_auf(orte):
    wt, ordner = orte
    repro = f"python -m pytest {ordner}/test_rot.py::test_x"

    urteil = pruefer_.urteilen(_bericht(_blocker(repro, "sollte")), ordner, wt)

    assert urteil.befund == ""
    assert "kein Blocker" in urteil.verworfen[0]


@pytest.mark.parametrize(
    ("bericht", "grund"),
    [
        ({}, "kein Feld result"),
        ({"result": "alles gut"}, "kein JSON"),
        ({"result": '{"befunde": "keine"}'}, "befunde ist keine Liste"),
        ({"result": '{"befunde": [1]}'}, "befunde ist keine Liste"),
        (None, "kein Feld result"),
    ],
)
def test_unlesbares_urteil_ist_kein_bestanden(orte, bericht, grund):
    wt, ordner = orte

    urteil = pruefer_.urteilen(bericht, ordner, wt)

    assert urteil.befund.startswith(f"Prüfer ohne lesbares Urteil: {grund}")


def test_leere_befundliste_besteht(orte):
    wt, ordner = orte

    urteil = pruefer_.urteilen(_bericht(), ordner, wt)

    assert urteil.befund == "" and "Verworfen:" in urteil.protokoll


def test_reproduktion_nutzt_das_python_des_hauptbaums(orte, tmp_path):
    wt, ordner = orte
    haupt = tmp_path / "haupt"
    (haupt / ".venv/bin").mkdir(parents=True)
    (wt / ".venv/bin/python").replace(haupt / ".venv/bin/python")
    (wt / ".venv/bin/python").write_text("#!/bin/sh\nexit 0\n")
    (wt / ".venv/bin/python").chmod(0o755)
    repro = f"python -m pytest {ordner}/test_rot.py::test_x"

    urteil = pruefer_.urteilen(_bericht(_blocker(repro)), ordner, wt, haupt)

    assert len(urteil.gezaehlt) == 1, urteil.protokoll
