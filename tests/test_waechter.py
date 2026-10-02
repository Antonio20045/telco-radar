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
    _schreibe(wurzel, "pruef/rot-bekannt.txt", "tests/test_a.py::test_x\n")
    _schreibe(wurzel, "pruef/tests-anzahl.txt", "10\n")
    _schreibe(wurzel, "pruef/tests-uebersprungen.txt", "2\n")
    _schreibe(wurzel, ".importlinter", _IMPORTLINTER)
    _schreibe(wurzel, "pyproject.toml", _PYPROJECT)
    monkeypatch.setattr(waechter, "ANKER", _commit(wurzel, "anker"))
    return wurzel


def _anker_neu(wurzel, monkeypatch):
    """Antonios Handweg: Bestand committen und den Anker auf diesen Commit legen."""
    monkeypatch.setattr(waechter, "ANKER", _commit(wurzel, "Bestand"))


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
        ("pruef/rot-bekannt.txt", "tests/test_a.py::test_x\nt::neu\n", "neu: t::neu"),
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
    # Ein späterer Commit macht die Lockerung nicht wieder unsichtbar.
    _schreibe(projekt, "README", "x\n")
    _commit(projekt)
    assert len(_rot(projekt)) == 1


def test_strengere_listen_sind_gruen(projekt):
    _schreibe(projekt, "pruef/ruff-basis.json", '{"src/a.py": {"F401": 1}}\n')
    _schreibe(projekt, "pruef/rot-bekannt.txt", "")
    _schreibe(projekt, "pruef/tests-anzahl.txt", "12\n")
    _schreibe(projekt, "pruef/tests-uebersprungen.txt", "0\n")
    _schreibe(projekt, ".importlinter", _IMPORTLINTER.rsplit("ignore_imports", 1)[0])
    _commit(projekt)
    assert _rot(projekt) == []


_LOCKERUNG = (
    ("src/telco_radar/a.py", "import os  # noqa: F401\n"),
    ("pruef/waechter-basis.txt", "src/telco_radar/a.py noqa:F401 1\n"),
    ("pruef/rot-bekannt.txt", "tests/test_a.py::test_x\nt::neu\n"),
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


def test_verschobener_anker_ist_die_einzige_lockerung_und_wird_genannt(
    projekt, monkeypatch
):
    _schreibe(projekt, waechter.WAECHTER, 'ANKER = "a"\n')
    _commit(projekt, "Wächter angelegt")
    assert waechter.anker_verschiebungen(projekt) == []
    _schreibe(projekt, "pruef/tests-uebersprungen.txt", "5\n")
    _schreibe(projekt, waechter.WAECHTER, 'ANKER = "b"\n')
    commit = _commit(projekt, "Antonio lockert Skips")
    monkeypatch.setattr(waechter, "ANKER", commit)
    assert _rot(projekt) == []
    assert waechter.anker_verschiebungen(projekt) == [
        f"Anker verschoben in {commit[:7]} Antonio lockert Skips"
    ]


def test_geloeschte_und_neu_angelegte_liste_bleibt_gesperrt(projekt):
    (projekt / "pruef/rot-bekannt.txt").unlink()
    _commit(projekt)
    _schreibe(projekt, "pruef/rot-bekannt.txt", "tests/test_a.py::test_x\n")
    assert _rot(projekt) == [
        "pruef/rot-bekannt.txt lockerer (Arbeitsstand): neu: tests/test_a.py::test_x"
    ]


def test_fehlender_verlauf_ist_rot(projekt, monkeypatch):
    monkeypatch.setattr(waechter, "ANKER", "0" * 40)
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
    ],
)
def test_neuer_befund_der_waechter_basis_ist_rot(projekt, pfad, text, code):
    _schreibe(projekt, pfad, text)
    rot = _rot(projekt)
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
        ("src/telco_radar/report/anbieter_farben.py", "ROT = '#e60000'\n"),
        ("src/telco_radar/report/a.j2", "<p>&#123; Seite#abc</p>\n"),
        ("tests/conftest.py", "def pytest_collection_modifyitems(items):\n    pass\n"),
        (".github/workflows/a.yml", "    continue-on-error: false\n"),
        (".github/workflows/a.yml", "  python-version-file: .python-version\n"),
    ],
)
def test_erlaubte_stellen_bleiben_gruen(projekt, pfad, text):
    _schreibe(projekt, pfad, text)
    assert _rot(projekt) == []


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
    _schreibe(projekt, waechter.WAECHTER, 'ANKER = "c"\n')
    assert waechter.anker_verschiebungen(projekt) == [
        f"Anker verschoben in {commit[:7]} verschoben",
        "Anker verschoben in Arbeitsstand",
    ]
    _schreibe(projekt, waechter.WAECHTER, 'ANKER = "b" + "c"\n')
    assert (
        waechter.anker_verschiebungen(projekt)[-1]
        == "Anker in Arbeitsstand nicht lesbar"
    )


def test_unlesbarer_verlauf_ist_rot_statt_keine_lockerung(projekt, monkeypatch):
    def kaputt(wurzel, paare):
        raise waechter.subprocess.CalledProcessError(128, ["git", "cat-file"])

    monkeypatch.setattr(waechter, "_inhalte", kaputt)
    assert _rot(projekt) == [f"Inhalte ab {waechter.ANKER[:7]} nicht lesbar"]


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
