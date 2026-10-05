import importlib.util
import subprocess
import sys
from collections import Counter
from pathlib import Path

import pytest

_PFAD = Path(__file__).resolve().parents[1] / "scripts" / "waechter.py"
sys.path.insert(0, str(_PFAD.parent))
_spec = importlib.util.spec_from_file_location("waechter", _PFAD)
waechter = importlib.util.module_from_spec(_spec)
sys.modules["waechter"] = waechter
_spec.loader.exec_module(waechter)
waechter_regeln = sys.modules["waechter_regeln"]

_REPORT = Path("src/telco_radar/report")
_IMPORTLINTER = """[importlinter]
root_packages =
    telco_radar

[importlinter:contract:report]
name = Report rechnet nur
type = forbidden
source_modules =
    telco_radar.report
forbidden_modules =
    telco_radar.collect
ignore_imports =
    telco_radar.report.html -> telco_radar.collect.lieferzeit
"""
_SPECNAME = (
    "import pytest\n\n\n"
    "@pytest.hookimpl(specname='pytest_runtest_makereport')\n"
    "def umschreiben(item):\n"
    "    pass\n"
)
_VERSUCH = "try:\n    x = 1\nexcept {}:\n    x = 2\n"
_ADDOPTS = '\n[tool.pytest.ini_options]\naddopts = "{}"\n'
_NATIV = "\n[tool.pytest]\naddopts = [{}]\n"
_OHNE_TYPCHECK = (
    "import typing as t\nfrom typing import no_type_check as ntc\n\n\n"
    "@{}\ndef f():\n    pass\n"
)
_PYPROJECT = """[tool.ruff]
include = ["src/**/*.py"]

[tool.ruff.lint]
select = ["E", "F"]

[tool.ruff.lint.per-file-ignores]
"tests/**" = ["D1"]

[tool.mypy]
check_untyped_defs = true
"""


def _git(wurzel, *argumente):
    return subprocess.run(
        ["git", *argumente], cwd=wurzel, check=True, capture_output=True, text=True
    ).stdout.strip()


def _schreibe(wurzel, pfad, text):
    datei = wurzel / pfad
    datei.parent.mkdir(parents=True, exist_ok=True)
    datei.write_text(text, encoding="utf-8")


def _commit(wurzel, nachricht="stand"):
    _git(wurzel, "add", "-A")
    _git(wurzel, "commit", "-q", "-m", nachricht)
    return _git(wurzel, "rev-parse", "HEAD")


@pytest.fixture()
def projekt(tmp_path, monkeypatch):
    """Ein Repo mit leeren Basen am Anker; die Wächter laufen echt darin."""
    wurzel = tmp_path / "projekt"
    wurzel.mkdir()
    _git(wurzel, "init", "-q")
    _git(wurzel, "config", "user.email", "t@example.org")
    _git(wurzel, "config", "user.name", "T")
    _schreibe(wurzel, _REPORT / "seite.py", "WERT = 1\n")
    _schreibe(wurzel, _REPORT / "templates/style.css", ":root{--rot:#e60000}\n")
    _schreibe(wurzel, "pruef/ruff-basis.json", '{"src/a.py": {"F401": 2}}\n')
    _schreibe(wurzel, "pruef/mypy-basis.txt", "src/a.py attr-defined 1\n")
    for name in ("privat-basis", "riesendateien", "waechter-basis"):
        _schreibe(wurzel, f"pruef/{name}.txt", "")
    _schreibe(wurzel, "pruef/tests-basis.txt", "pyproject.toml pytest-pflicht 3\n")
    _schreibe(wurzel, "pruef/tests-anzahl.txt", "10\n")
    _schreibe(wurzel, "pruef/tests-uebersprungen.txt", "2\n")
    _schreibe(wurzel, ".importlinter", _IMPORTLINTER)
    _schreibe(wurzel, "pyproject.toml", _PYPROJECT)
    _setze_anker(wurzel, _commit(wurzel, "anker"))
    return wurzel


def _setze_anker(wurzel, wert):
    _schreibe(wurzel, waechter.WAECHTER, f'ANKER = "{wert}"\n')


def _anker_neu(wurzel, monkeypatch=None):
    """Antonios Handweg: Bestand committen, Anker darauf legen, den roten Stand
    selbst committen; ab dem nächsten Commit ist die Leiter wieder grün."""
    bestand = _commit(wurzel, "Bestand")
    _setze_anker(wurzel, bestand)
    _commit(wurzel, "Antonio verschiebt den Anker")
    _git(wurzel, "commit", "-q", "--allow-empty", "-m", "weiter")
    return bestand


def _rot(wurzel):
    return waechter.pruefe(wurzel, Counter())[0]


def test_sauberer_stand_ist_gruen(projekt):
    assert _rot(projekt) == []


def test_neue_datei_mit_401_zeilen_ist_rot_mit_400_gruen(projekt):
    _schreibe(projekt, "src/telco_radar/neu.py", "x = 1\n" * 400)
    assert _rot(projekt) == []
    _schreibe(projekt, "scripts/neu.py", "x = 1\n" * 401)
    assert _rot(projekt) == [
        "scripts/neu.py [zeilen] erwartet höchstens 0, gefunden 401"
        " (pruef/riesendateien.txt)"
    ]


def test_letzte_zeile_ohne_umbruch_zaehlt_mit(projekt):
    _schreibe(projekt, "src/telco_radar/neu.py", "x = 1\n" * 400 + "x = 1")
    assert _rot(projekt)[0].startswith("src/telco_radar/neu.py [zeilen]")


def test_gelistete_riesendatei_darf_nicht_wachsen_und_sinkt_selbst(
    projekt, monkeypatch
):
    _schreibe(projekt, "pruef/riesendateien.txt", "src/gross.py zeilen 500\n")
    _anker_neu(projekt, monkeypatch)
    _schreibe(projekt, "src/gross.py", "x = 1\n" * 501)
    assert len(_rot(projekt)) == 1
    _schreibe(projekt, "src/gross.py", "x = 1\n" * 450)
    assert waechter.pruefe(projekt, Counter()) == (
        [],
        [projekt / "pruef/riesendateien.txt"],
    )
    assert (projekt / "pruef/riesendateien.txt").read_text() == (
        "src/gross.py zeilen 450\n"
    )


@pytest.mark.parametrize(
    ("pfad", "text", "erwartet"),
    [
        (
            "pruef/ruff-basis.json",
            '{"src/a.py": {"F401": 3}}\n',
            "src/a.py F401 von 2 auf 3",
        ),
        ("pruef/mypy-basis.txt", "src/b.py misc 1\nsrc/a.py attr-defined 1\n", "misc"),
        (
            "pruef/tests-basis.txt",
            "pyproject.toml pytest-pflicht 3\ntests/test_a.py uhr 1\n",
            "tests/test_a.py uhr von 0 auf 1",
        ),
        ("pruef/tests-anzahl.txt", "9\n", "10 -> 9"),
        ("pruef/tests-uebersprungen.txt", "3\n", "2 -> 3"),
        ("pruef/tests-anzahl.txt", None, "10 -> fehlt"),
        (
            ".importlinter",
            _IMPORTLINTER + "    telco_radar.report.promo -> telco_radar.collect\n",
            "neue Ausnahme telco_radar.report.promo -> telco_radar.collect",
        ),
        (".importlinter", "[importlinter]\n", "importlinter:contract:report fehlt"),
        (
            "pyproject.toml",
            _PYPROJECT.replace('["D1"]', '["D1", "F401"]'),
            "ruff geändert",
        ),
        ("pyproject.toml", _PYPROJECT.replace('"E", "F"', '"E"'), "ruff geändert"),
        (
            "pyproject.toml",
            _PYPROJECT.replace("true", "false"),
            "mypy geändert",
        ),
        (
            "pyproject.toml",
            _PYPROJECT + '[tool.pytest.ini_options]\naddopts = "--deselect t::x"\n',
            "pytest addopts neu: --deselect",
        ),
    ],
)
def test_von_hand_gelockerte_liste_ist_rot_im_arbeitsstand_und_committet(
    projekt, pfad, text, erwartet
):
    if text is None:
        (projekt / pfad).unlink()
    else:
        _schreibe(projekt, pfad, text)
    rot = _rot(projekt)
    assert len(rot) == 1
    assert rot[0].startswith(f"{pfad} lockerer (Arbeitsstand): ")
    assert erwartet in rot[0]
    commit = _commit(projekt)
    assert _rot(projekt)[0].startswith(f"{pfad} lockerer ({commit[:7]}): ")
    _schreibe(projekt, "README", "x\n")
    _commit(projekt)
    assert len(_rot(projekt)) == 1


def test_strengere_listen_sind_gruen(projekt):
    _schreibe(projekt, "pruef/ruff-basis.json", '{"src/a.py": {"F401": 1}}\n')
    _schreibe(projekt, "pruef/tests-anzahl.txt", "12\n")
    _schreibe(projekt, "pruef/tests-uebersprungen.txt", "0\n")
    _schreibe(projekt, ".importlinter", _IMPORTLINTER.rsplit("ignore_imports", 1)[0])
    _commit(projekt)
    assert _rot(projekt) == []


_LOCKERUNG = (
    ("src/telco_radar/a.py", "import os  # noqa: F401\n"),
    ("pruef/waechter-basis.txt", "src/telco_radar/a.py noqa:F401 1\n"),
    ("pruef/tests-anzahl.txt", "1\n"),
    ("pruef/tests-uebersprungen.txt", "999\n"),
    (
        ".importlinter",
        _IMPORTLINTER + "    telco_radar.report.b -> telco_radar.collect\n",
    ),
    ("pyproject.toml", _PYPROJECT.replace('"E", "F"', '"E"')),
)


@pytest.mark.parametrize("nachricht", ["chore: aufräumen", "x\n\nLockerung: x"])
def test_keine_commitzeile_erlaubt_eine_lockerung(projekt, nachricht):
    for pfad, text in _LOCKERUNG:
        _schreibe(projekt, pfad, text)
    commit = _commit(projekt, nachricht)[:7]
    rot = _rot(projekt)
    assert [z.split(" ")[0] for z in rot] == [p for p, _ in _LOCKERUNG[1:]]
    assert all(f"lockerer ({commit})" in z for z in rot)


def test_verschobener_anker_ist_rot_im_einfuehrenden_stand_dann_gruen(projekt):
    """Rot-Probe der dritten Session: vorher blieb eine Verschiebung grün."""
    alt = _git(projekt, "rev-parse", "HEAD")[:7]
    _commit(projekt, "Wächter angelegt")
    assert waechter.anker_verschiebungen(projekt) == []
    _schreibe(projekt, "pruef/tests-uebersprungen.txt", "5\n")
    lockerung = _commit(projekt, "Antonio lockert Skips")
    _setze_anker(projekt, lockerung)
    nur_antonio = (
        f"{alt} -> {lockerung[:7]}; lockern darf nur Antonio von Hand, indem er"
        " diesen roten Stand selbst committet"
    )
    assert _rot(projekt) == [f"Anker verschoben im Arbeitsstand: {nur_antonio}"]
    verschiebung = _commit(projekt, "Anker auf die Lockerung")
    assert _rot(projekt) == [
        f"Anker verschoben im HEAD {verschiebung[:7]}: {nur_antonio}"
    ]
    _schreibe(projekt, "README", "weiter\n")
    _commit(projekt, "weiter")
    assert _rot(projekt) == []
    datum = _git(projekt, "log", "-1", "--format=%as", verschiebung)
    assert waechter.anker_verschiebungen(projekt) == [
        f"Anker verschoben in {verschiebung[:7]} ({datum}, T) Anker auf die"
        f" Lockerung: {alt} -> {lockerung[:7]}"
    ]


def test_anker_auf_head_gesetzt_ist_rot(projekt):
    _commit(projekt, "Wächter angelegt")
    _setze_anker(projekt, _git(projekt, "rev-parse", "HEAD"))
    assert _rot(projekt)[0].startswith("Anker verschoben im Arbeitsstand: ")


def test_anker_wird_aus_der_datei_gelesen_nicht_aus_dem_modul(projekt, monkeypatch):
    _schreibe(projekt, "pruef/tests-uebersprungen.txt", "5\n")
    lockerung = _commit(projekt, "lockert")
    monkeypatch.setattr(waechter, "ANKER", lockerung)
    assert _rot(projekt) == [
        f"pruef/tests-uebersprungen.txt lockerer ({lockerung[:7]}): 2 -> 5"
    ]


_ZWEITE_BINDUNG = [
    'ANKER = "{a}"\nANKER = "{b}"\n',
    'ANKER = "{a}"\nif True:\n    ANKER = "{b}"\n',
    'ANKER = "{a}"\nglobals()["ANKER"] = "{b}"\n',
    'import sys\nANKER = "{a}"\nsetattr(sys.modules[__name__], "ANKER", "{b}")\n',
    'ANKER = "{a}"\nANKER += ""\n',
    'ANKER = "{a}"\nfor ANKER in ["{b}"]:\n    pass\n',
    'ANKER = "{a}"\nimport os as ANKER\n',
    'ANKER = "{a}"\n\n\ndef ANKER():\n    pass\n',
    'ANKER = "{a}"\n(ANKER := "{b}")\n',
    'ANKER = "{a}"\n\n\ndef f():\n    global ANKER\n',
    'import waechter\nANKER = "{a}"\nwaechter.ANKER = "{b}"\n',
    'ANKER = "{a}"\ndel ANKER\n',
]


@pytest.mark.parametrize("text", _ZWEITE_BINDUNG)
def test_zweite_bindung_des_ankers_ist_rot(projekt, text):
    """Gegen 6ceb9cd grün: der Wächter las nur die erste Zuweisung."""
    anker = _git(projekt, "rev-parse", "HEAD")
    _schreibe(projekt, waechter.WAECHTER, text.format(a=anker, b="0" * 40))
    assert _rot(projekt) == [
        "Anker in scripts/waechter.py nicht eindeutig: der Name darf nur einmal"
        " gebunden werden"
    ]


def test_lesen_des_ankers_bleibt_gruen(projekt):
    anker = _git(projekt, "rev-parse", "HEAD")
    _schreibe(projekt, waechter.WAECHTER, f'ANKER = "{anker}"\nKURZ = ANKER[:7]\n')
    assert _rot(projekt) == []


def test_anker_ausserhalb_der_geschichte_von_head_ist_rot(projekt):
    _git(projekt, "checkout", "-q", "-b", "neben")
    _schreibe(projekt, "README", "x\n")
    neben = _commit(projekt, "neben")
    _git(projekt, "checkout", "-q", "-")
    _setze_anker(projekt, neben)
    assert _rot(projekt) == [f"Anker {neben[:7]} ist kein Vorfahre von HEAD"]


@pytest.mark.parametrize("pfad", waechter.ABGESCHAFFT)
@pytest.mark.parametrize("inhalt", ["", "tests/test_a.py::test_x\n"])
def test_abgeschaffte_liste_wieder_anlegen_ist_rot_auch_leer(projekt, pfad, inhalt):
    _schreibe(projekt, pfad, inhalt)
    assert _rot(projekt) == [
        f"{pfad} ist abgeschafft; rote Tests werden repariert, nicht gelistet"
    ]


@pytest.mark.parametrize("pfad", waechter.ABGESCHAFFT)
def test_abgeschaffte_liste_mit_eintrag_meldet_auch_lockerer(projekt, pfad):
    _schreibe(projekt, pfad, "")
    _setze_anker(projekt, _commit(projekt, "Liste"))
    _schreibe(projekt, pfad, "tests/test_a.py\n")
    assert f"{pfad} lockerer (Arbeitsstand): neu: tests/test_a.py" in _rot(projekt)


def test_fehlender_verlauf_ist_rot(projekt):
    _setze_anker(projekt, "0" * 40)
    assert _rot(projekt) == ["Verlauf ab 0000000 fehlt; erst `git fetch --unshallow`"]


@pytest.mark.parametrize(
    ("pfad", "text", "code"),
    [
        ("src/telco_radar/a.py", "import os  # noqa: F401\n", "noqa:F401"),
        ("tests/test_a.py", "x = 1  # noqa\n", "noqa:alle"),
        ("src/telco_radar/a.py", "x: int = ''  # type: ignore[assignment]\n", ""),
        ("src/telco_radar/a.py", "# mypy: ignore-errors\n", "werkzeug-aus"),
        ("src/telco_radar/a.py", "x = datetime.now(UTC)\n", "uhr"),
        ("src/telco_radar/a.py", "x = _datum.today()\n", "uhr"),
        ("src/telco_radar/a.py", "x = time.time()\n", "uhr"),
        ("src/telco_radar/collect/http.py", "x = time.time()\n", "uhr"),
        ("src/telco_radar/report/a.py", "x = Path('d').read_text()\n", ""),
        ("src/telco_radar/report/a.py", "x = open('d')\n", "dateizugriff"),
        ("src/telco_radar/a.py", _VERSUCH.format("Exception"), "breite"),
        ("src/telco_radar/a.py", _VERSUCH.format("(OSError, BaseException)"), ""),
        ("src/telco_radar/report/templates/a.j2", '<i style="color:#E60000">', ""),
        ("src/telco_radar/a.py", "x = 1 +\n", "syntaxfehler"),
        ("tests/conftest.py", "def pytest_runtest_makereport(item):\n    pass\n", ""),
        ("tests/conftest.py", "pytest_plugins = ['umschreiber']\n", "pytest-plugins"),
        ("conftest.py", "def pytest_runtest_makereport(item):\n    pass\n", ""),
        ("tests/conftest.py", _SPECNAME, "pytest-hook"),
        ("src/telco_radar/a.py", "import os  # NOQA: F401\n", "noqa:F401"),
        ("ruff.toml", "[lint]\nignore = ['F401']\n", "fremde-konfig"),
        (".mypy.ini", "[mypy]\nignore_errors = True\n", "fremde-konfig"),
        (".github/workflows/a.yml", "    continue-on-error: true\n", ""),
        (".github/workflows/a.yml", "        run: make || true\n", "oder-true"),
        (".github/workflows/a.yml", "          python-version: '3.12'\n", ""),
        ("src/telco_radar/a.py", "# ruff: disable[E501]\nx = 1\n", "ruff-aus:E501"),
        ("tests/test_a.py", "# ruff: disable\nx = 1\n", "ruff-aus:alle"),
        ("src/telco_radar/a.py", '# mypy: disable-error-code="misc"\n', "mypy-aus:"),
        ("src/telco_radar/a.py", "# mypy: allow-untyped-defs\n", "mypy-aus:allow"),
        ("src/telco_radar/a.py", "# isort: skip_file\n", "werkzeug-aus"),
        ("src/telco_radar/a.py", _OHNE_TYPCHECK.format("t.no_type_check"), "kein-"),
        ("src/telco_radar/a.py", _OHNE_TYPCHECK.format("ntc"), "kein-typcheck"),
        (
            "tests/conftest.py",
            'globals()["pytest_plugins"] = ["x"]\n',
            "pytest-plugins",
        ),
        ("src/leiter_roh.py", "x = 1\n", "fremde-konfig"),
        ("leiter_roh.py", "x = 1\n", "fremde-konfig"),
        ("pyproject.toml", _PYPROJECT + _ADDOPTS.format("-p fremd"), "pytest-plugin"),
        ("pyproject.toml", _PYPROJECT + _ADDOPTS.format("-pfremd"), "pytest-plugin"),
        ("pyproject.toml", _PYPROJECT + _NATIV.format('"-p", "x"'), "pytest-plugin"),
        ("tests/conftest.py", "import _pytest.assertion.rewrite\n", "leiter-eingriff"),
        ("tests/conftest.py", "def f(i, c):\n    i.obj.__code__ = c\n", "leiter-"),
        ("tests/conftest.py", "import sys\n\nsys.modules['x'].y = 1\n", "leiter-"),
        ("tests/test_a.py", "from pluggy import HookimplMarker\n", "leiter-eingriff"),
        ("tests/test_a.py", "x = __import__('_pytest.runner')\n", "leiter-eingriff"),
        ("src/telco_radar/a.py", "import time\n\njetzt = time.time\n", "uhr"),
        ("src/telco_radar/a.py", "import time\n\nx = time.localtime()\n", "uhr"),
        ("src/telco_radar/a.py", "import time\n\nx = time.strftime('%Y')\n", "uhr"),
        ("src/telco_radar/a.py", "from time import time\nx = time()\n", "uhr"),
        ("src/telco_radar/a.py", "from time import time as t\nx = t()\n", "uhr"),
        ("src/telco_radar/a.py", "import time as t\nx = t.time_ns()\n", "uhr"),
        ("src/telco_radar/a.py", "x = __import__('time').time()\n", "uhr"),
        (
            "src/telco_radar/a.py",
            "from datetime import date as d\nx = d.today()\n",
            "uhr",
        ),
        ("src/telco_radar/a.py", "x = 1  # Minuten\n", "kommentar"),
        ("tools/a.py", "x = 1  # alt\n", "kommentar"),
        ("tests/test_a.py", "# Zehn statt sieben\nx = 1\n", "kommentar"),
        ("scripts/a.py", "# -*- coding: utf-8 -*-\nx = 1\n", "kommentar"),
        ("src/telco_radar/a.py", "x = 1\n#!/bin/sh\n", "kommentar"),
        ("src/telco_radar/a.py", "x = 1  # pragma: no cover - echt\n", "kom"),
        ("src/telco_radar/a.py", "x = 1  # ruff ist hier nicht abgeschaltet\n", "kom"),
        ("src/telco_radar/a.py", "x = 1  # siehe mypy: Doku\n", "kommentar"),
        ("src/telco_radar/a.py", "# Hinweis: ruff: disable[E501] nie nutzen\n", "kom"),
    ],
)
def test_neuer_befund_der_waechter_basis_ist_rot(projekt, pfad, text, code):
    _schreibe(projekt, pfad, text)
    lockerung = "pyproject.toml lockerer (Arbeitsstand): pytest addopts neu: "
    rot = [z for z in _rot(projekt) if not z.startswith(lockerung)]
    assert len(rot) == 1
    assert rot[0].startswith(f"{pfad} [{code}")
    assert rot[0].endswith("(pruef/waechter-basis.txt)")


@pytest.mark.parametrize(
    ("pfad", "text"),
    [
        ("src/telco_radar/pipeline.py", "x = datetime.now(UTC)\n"),
        ("src/telco_radar/a.py", "x = time.monotonic()\n"),
        ("src/telco_radar/a.py", "x = Path('d').read_text()\n"),
        ("src/telco_radar/a.py", _VERSUCH.format("ValueError")),
        ("src/telco_radar/a.py", "x = 'kein noqa im Text'  # pragma: no cover\n"),
        ("scripts/a.py", "#!/usr/bin/env python3\nx = 1  # pragma: no cover\n"),
        ("src/telco_radar/report/anbieter_farben.py", "ROT = '#e60000'\n"),
        ("src/telco_radar/report/a.j2", "<p>&#123; Seite#abc</p>\n"),
        ("tests/conftest.py", "def pytest_collection_modifyitems(items):\n    pass\n"),
        (".github/workflows/a.yml", "    continue-on-error: false\n"),
        (".github/workflows/a.yml", "  python-version-file: .python-version\n"),
        ("src/telco_radar/a.py", "from time import monotonic\nx = monotonic()\n"),
        ("src/telco_radar/a.py", "from time import sleep\nsleep(0)\n"),
        ("src/telco_radar/a.py", "def time():\n    pass\n\n\ntime()\n"),
        ("pyproject.toml", _PYPROJECT + _ADDOPTS.format("--strict-markers")),
        ("scripts/leiter_plugin/leiter_roh.py", "x = 1\n"),
        ("src/telco_radar/a.py", "import time\n\nx = time.localtime(0)\n"),
        ("src/telco_radar/a.py", "x = tag.strftime('%Y')\n"),
        ("tests/test_a.py", "import sys\n\nsys.modules['x'] = None\n"),
    ],
)
def test_erlaubte_stellen_bleiben_gruen(projekt, pfad, text):
    _schreibe(projekt, pfad, text)
    assert _rot(projekt) == []


_SCHAERFER = "--strict-markers --disable-socket --allow-hosts=127.0.0.1 -n auto"
_MARKER = '\nmarkers = ["seite: x", "netz: y"]\n'


@pytest.mark.parametrize(
    ("ini", "erwartet"),
    [
        (_ADDOPTS.format("--deselect t::x"), ["addopts neu: --deselect", "t::x"]),
        (_ADDOPTS.format("-k 'not x'"), ["addopts neu: -k", "not x"]),
        (_ADDOPTS.format("-m 'not netz'"), ["addopts neu: -m", "not netz"]),
        (_ADDOPTS.format("--ignore=tests/a.py"), ["addopts neu: --ignore=tests/a.py"]),
        (_ADDOPTS.format("--allow-hosts=10.0.0.1"), ["addopts neu: --allow-hosts=10"]),
        (
            '[tool.pytest.ini_options]\ntestpaths = ["tests/a"]\n',
            ["testpaths geändert"],
        ),
        ('[tool.pytest.ini_options]\npython_functions = "x_*"\n', ["python_functions"]),
        ('[tool.pytest]\nnorecursedirs = ["tests"]\n', ["norecursedirs geändert"]),
        (_NATIV.format('"--deselect", "t::x"'), ["addopts neu: --deselect"]),
    ],
)
def test_abwahl_in_den_pytest_einstellungen_ist_eine_lockerung(projekt, ini, erwartet):
    _schreibe(projekt, "pyproject.toml", _PYPROJECT + ini)
    rot = [z for z in _rot(projekt) if "pyproject.toml lockerer" in z]
    assert rot
    assert all(any(e in z for z in rot) for e in erwartet), rot


def test_verschaerfte_pytest_einstellungen_bleiben_gruen_und_ihr_entfernen_ist_rot(
    projekt,
):
    scharf = _PYPROJECT + _ADDOPTS.format(_SCHAERFER + " --dist worksteal") + _MARKER
    _schreibe(projekt, "pyproject.toml", scharf)
    assert _rot(projekt) == []
    _commit(projekt)
    _schreibe(projekt, "pyproject.toml", scharf.replace("--strict-markers ", ""))
    assert _rot(projekt) == [
        "pyproject.toml lockerer (Arbeitsstand): pytest addopts entfernt:"
        " --strict-markers",
        "pyproject.toml [pytest-pflicht] erwartet höchstens 0, gefunden 1"
        " (pruef/tests-basis.txt)",
    ]


def test_hexfarbe_nur_im_root_block_von_style_css_erlaubt(projekt):
    style = projekt / _REPORT / "templates/style.css"
    style.write_text(":root{--rot:#e60000; --b:#fff}\n.a{color:#e60000}\n", "utf-8")
    assert _rot(projekt) == [
        "src/telco_radar/report/templates/style.css [hexfarbe] erwartet höchstens 0,"
        " gefunden 1 (pruef/waechter-basis.txt)"
    ]


def test_privater_import_ueber_der_basis_ist_rot(projekt):
    privat = Counter({("tests/test_a.py", "PLC2701"): 1})
    assert waechter.pruefe(projekt, privat)[0] == [
        "tests/test_a.py [PLC2701] erwartet höchstens 0, gefunden 1"
        " (pruef/privat-basis.txt)"
    ]


def test_weniger_befunde_senken_die_basis_nur_wenn_alles_gruen_ist(
    projekt, monkeypatch
):
    basis = projekt / "pruef/waechter-basis.txt"
    basis.write_text("src/telco_radar/a.py uhr 2\n", "utf-8")
    _anker_neu(projekt, monkeypatch)
    _schreibe(projekt, "src/telco_radar/a.py", "x = date.today()\n")
    _schreibe(projekt, "pruef/tests-anzahl.txt", "9\n")
    assert len(_rot(projekt)) == 1
    assert basis.read_text() == "src/telco_radar/a.py uhr 2\n"
    _schreibe(projekt, "pruef/tests-anzahl.txt", "10\n")
    assert _rot(projekt) == []
    assert basis.read_text() == "src/telco_radar/a.py uhr 1\n"
    assert waechter.pruefe(projekt, Counter(), schreiben=False) == ([], [])


@pytest.mark.parametrize(
    "pfad",
    [
        "src/telco_radar/report/ruff.toml",
        "src/telco_radar/report/.ruff.toml",
        "src/telco_radar/pyproject.toml",
        "tests/pyproject.toml",
        "mypy.ini",
        "src/.mypy.ini",
        "setup.cfg",
        "scripts/setup.cfg",
        "pytest.ini",
        ".pytest.ini",
        "pytest.toml",
        "tests/tox.ini",
        "conftest.py",
        "src/telco_radar/conftest.py",
        "src/sitecustomize.py",
        "docs/usercustomize.py",
        "src/.importlinter",
    ],
)
def test_konfiguration_neben_der_wurzel_ist_rot_ueberall_im_repo(projekt, pfad):
    _schreibe(projekt, pfad, "[lint]\nignore = ['F401']\n")
    assert _rot(projekt) == [
        f"{pfad} [fremde-konfig] erwartet höchstens 0, gefunden 1"
        " (pruef/waechter-basis.txt)"
    ]


def test_nur_benannte_umgebungs_und_worktree_ordner_bleiben_ungelesen(projekt):
    _schreibe(projekt, ".venv/lib/paket/pyproject.toml", "[tool.ruff]\n")
    _schreibe(projekt, ".claude/worktrees/lauf1/pyproject.toml", "[tool.ruff]\n")
    _schreibe(projekt, ".claude/worktrees/lauf1/tests/conftest.py", "x = 1\n")
    _schreibe(projekt, "tests/conftest.py", "import pytest\n")
    _schreibe(projekt, "tests/geraete/conftest.py", "import pytest\n")
    assert _rot(projekt) == []
    _schreibe(projekt, "src/pyvenv.cfg", "home = /usr\n")
    _schreibe(projekt, "src/ruff.toml", "[lint]\nignore = ['F401']\n")
    assert _rot(projekt)[0].startswith("src/ruff.toml [fremde-konfig]")


def test_zaehlung_ist_parallel_dieselbe_wie_seriell(projekt, monkeypatch):
    for n in range(5):
        _schreibe(projekt, f"src/telco_radar/m{n}.py", "x = date.today()  # noqa\n")
    seriell = waechter_regeln.waechter_zaehlung(projekt)
    monkeypatch.setattr(waechter_regeln, "PARALLEL_AB", 1)
    assert waechter_regeln.waechter_zaehlung(projekt) == seriell
    assert seriell[("src/telco_radar/m4.py", "uhr")] == 1


def test_anker_meldet_den_wert_nicht_die_schreibweise(projekt):
    _schreibe(projekt, waechter.WAECHTER, 'ANKER = "a"\n')
    _commit(projekt, "Wächter angelegt")
    _schreibe(projekt, waechter.WAECHTER, 'ANKER: str = "a"\n')
    _commit(projekt, "typ annotiert")
    assert waechter.anker_verschiebungen(projekt) == []
    _schreibe(projekt, waechter.WAECHTER, 'ANKER: str = "b"\n')
    commit = _commit(projekt, "verschoben")
    datum = _git(projekt, "log", "-1", "--format=%as")
    _schreibe(projekt, waechter.WAECHTER, 'ANKER = "c"\n')
    assert waechter.anker_verschiebungen(projekt) == [
        f"Anker verschoben in {commit[:7]} ({datum}, T) verschoben: a -> b",
        "Anker verschoben in Arbeitsstand: b -> c",
    ]
    _schreibe(projekt, waechter.WAECHTER, 'ANKER = "b" + "c"\n')
    assert (
        waechter.anker_verschiebungen(projekt)[-1]
        == "Anker in Arbeitsstand nicht lesbar"
    )


def test_unlesbare_listen_im_verlauf_sind_rot(projekt, monkeypatch):
    echt = waechter._inhalte

    def kaputt(wurzel, paare):
        if any(p in waechter.LISTEN for _, p in paare):
            raise waechter.subprocess.CalledProcessError(128, ["git", "cat-file"])
        return echt(wurzel, paare)

    monkeypatch.setattr(waechter, "_inhalte", kaputt)
    anker = _git(projekt, "rev-parse", "HEAD")
    assert _rot(projekt) == [f"Inhalte ab {anker[:7]} nicht lesbar"]


def test_unlesbare_zwischenfassung_versteckt_keine_ankerverschiebung(projekt):
    alt = _git(projekt, "rev-parse", "HEAD")
    _commit(projekt, "Wächter angelegt")
    _schreibe(projekt, waechter.WAECHTER, "ANKER = WERT\n")
    _commit(projekt, "unlesbar")
    _schreibe(projekt, "pruef/tests-uebersprungen.txt", "5\n")
    lockerung = _commit(projekt, "lockert")
    _setze_anker(projekt, lockerung)
    kopf = _commit(projekt, "Anker auf die Lockerung")
    assert _rot(projekt)[0].startswith(
        f"Anker verschoben im HEAD {kopf[:7]}: {alt[:7]} -> {lockerung[:7]};"
    )


def test_unlesbarer_verlauf_ist_rot_statt_keine_lockerung(projekt, monkeypatch):
    def kaputt(wurzel, paare):
        raise waechter.subprocess.CalledProcessError(128, ["git", "cat-file"])

    monkeypatch.setattr(waechter, "_inhalte", kaputt)
    assert _rot(projekt) == ["Verlauf von scripts/waechter.py nicht lesbar"]


def test_uhr_ausserhalb_der_einstiegsfunktion_wird_gezaehlt(projekt):
    _schreibe(
        projekt,
        "src/telco_radar/pipeline.py",
        "def run():\n    a = datetime.now(UTC)\n\n\n"
        "def neben():\n    b = date.today()\n",
    )
    _schreibe(
        projekt,
        "src/telco_radar/geraete_pipeline.py",
        "x = time.time()\n\n\ndef run_geraete_stage():\n    y = time.monotonic()\n",
    )
    assert _rot(projekt) == []
    assert waechter_regeln.uhr_ausserhalb_einstieg(projekt) == 2
    _schreibe(
        projekt,
        "src/telco_radar/geraete_pipeline.py",
        "import time as t\n\nSTART = t.time()\n",
    )
    assert waechter_regeln.uhr_ausserhalb_einstieg(projekt) == 2


def test_paket_namens_wie_das_leiterplugin_ist_rot(projekt):
    _schreibe(projekt, "src/leiter_roh/__init__.py", "")
    assert _rot(projekt)[0].startswith("src/leiter_roh [fremde-konfig]")
