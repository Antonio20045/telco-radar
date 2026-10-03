"""Stufe 0 zählt an den Tests, was die Hermetik umgeht: Uhr, eigenes Chromium,
Netzfreigaben, Griffe in die Hermetik und fehlende Pflichtoptionen von pytest."""

import importlib
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
waechter_tests = importlib.import_module("waechter_tests")

_PYPROJECT = (
    "[tool.pytest.ini_options]\n"
    'addopts = "--strict-markers --disable-socket'
    " --allow-hosts=127.0.0.1 -m 'not netz'\"\n"
)


@pytest.fixture()
def projekt(tmp_path):
    (tmp_path / "tests").mkdir()
    (tmp_path / "pyproject.toml").write_text(_PYPROJECT, encoding="utf-8")
    return tmp_path


def _zaehle(projekt, text, name="tests/test_x.py"):
    (projekt / name).write_text(text, encoding="utf-8")
    return waechter_tests.tests_zaehlung(projekt)


def test_sauberer_test_zaehlt_nichts(projekt):
    text = "import datetime\n\n\ndef test_x(heute):\n    assert heute.year\n"
    assert _zaehle(projekt, text) == {}


@pytest.mark.parametrize(
    ("text", "code", "anzahl"),
    [
        ("import datetime\nx = datetime.date.today()\n", "uhr", 1),
        ("from time import time as t\nx = t()\n", "uhr", 1),
        ("from datetime import datetime\nuhr = datetime.now\n", "uhr", 1),
        (
            "from playwright.sync_api import sync_playwright\n"
            "with sync_playwright() as p:\n    p.chromium.launch()\n",
            "chromium-eigenes",
            1,
        ),
        (
            "from playwright.sync_api import sync_playwright as sp\n"
            "with sp() as p:\n    pass\n",
            "chromium-eigenes",
            1,
        ),
        (
            "import pytest\n\n\n@pytest.mark.enable_socket\ndef test_x(): ...\n",
            "netz-freigabe",
            1,
        ),
        ("def test_x(socket_enabled): ...\n", "netz-freigabe", 1),
        ("import pytest\npytest.mark.allow_hosts(['1.2.3.4'])\n", "netz-freigabe", 1),
        ("ARGS = ['--force-enable-socket']\n", "netz-freigabe", 1),
        ("import conftest\nconftest._aktiv[0] = False\n", "hermetik-eingriff", 3),
        ("from conftest import _altlasten\n", "hermetik-eingriff", 2),
        (
            "import sys\nsys.modules['conftest']._verstoesse.clear()\n",
            "hermetik-eingriff",
            2,
        ),
    ],
)
def test_umgehung_zaehlt_je_datei(projekt, text, code, anzahl):
    assert _zaehle(projekt, text)[("tests/test_x.py", code)] == anzahl


def test_conftest_selbst_und_erlaubte_dateien_zaehlen_keinen_eingriff(projekt):
    text = "import conftest\nconftest._aktiv\n"
    assert _zaehle(projekt, text, "tests/conftest.py") == {}
    assert _zaehle(projekt, text, "tests/test_hermetik.py") == {}


def test_unterordner_werden_mitgezaehlt(projekt):
    (projekt / "tests" / "orakel").mkdir()
    zaehlung = _zaehle(
        projekt, "import time\nx = time.time()\n", "tests/orakel/test_o.py"
    )
    assert zaehlung == {("tests/orakel/test_o.py", "uhr"): 1}


@pytest.mark.parametrize(
    ("addopts", "fehlend"),
    [
        ("--strict-markers --disable-socket --allow-hosts=127.0.0.1", 0),
        ("--strict-markers --allow-hosts=127.0.0.1", 1),
        ("--disable-socket", 2),
        ("", 3),
    ],
)
def test_pflichtoptionen_von_pytest(projekt, addopts, fehlend):
    (projekt / "pyproject.toml").write_text(
        f'[tool.pytest.ini_options]\naddopts = "{addopts}"\n', encoding="utf-8"
    )
    zaehlung = waechter_tests.tests_zaehlung(projekt)
    assert zaehlung[("pyproject.toml", "pytest-pflicht")] == fehlend


def test_fehlende_pytest_konfiguration_fehlt_ganz(projekt):
    (projekt / "pyproject.toml").write_text("[tool.ruff]\n", encoding="utf-8")
    zaehlung = waechter_tests.tests_zaehlung(projekt)
    assert zaehlung[("pyproject.toml", "pytest-pflicht")] == 3


@pytest.mark.parametrize(
    ("name", "text"),
    [
        ("tests/test_x.py", "class TestA:\n    __test__ = False\n"),
        ("tests/test_x.py", "def test_a(): ...\n\n\ntest_a.__test__ = False\n"),
        (
            "tests/test_x.py",
            "import pytest\npytest.skip('x', allow_module_level=True)\n",
        ),
        ("tests/build/test_x.py", "def test_a():\n    assert False\n"),
        ("tests/.weg/test_x.py", "def test_a():\n    assert False\n"),
        ("tests/geraete/venv/test_x.py", "def test_a():\n    assert False\n"),
        ("tests/pruef_x.py", "def test_a():\n    assert False\n"),
        ("tests/x.py", "class TestA:\n    def test_a(self): ...\n"),
    ],
)
def test_vor_pytest_versteckter_test_zaehlt(projekt, name, text):
    (projekt / name).parent.mkdir(parents=True, exist_ok=True)

    zaehlung = _zaehle(projekt, text, name)

    assert zaehlung == {(name, "test-versteckt"): 1}


@pytest.mark.parametrize(
    ("name", "text"),
    [
        ("tests/helfer.py", "def hilfe():\n    return 1\n"),
        ("tests/geraete/test_x.py", "def test_a():\n    assert True\n"),
        ("tests/x_test.py", "def test_a():\n    assert True\n"),
        ("tests/kanarie_leiter.py", "def test_muss_scheitern():\n    assert False\n"),
    ],
)
def test_gesammelter_test_und_hilfsmodul_zaehlen_nicht(projekt, name, text):
    (projekt / name).parent.mkdir(parents=True, exist_ok=True)

    assert _zaehle(projekt, text, name) == {}


@pytest.mark.parametrize(
    "text",
    [
        "import test_alt\n\ntest_alt.test_x = lambda: None\n",
        "import test_alt as t\n\ndel t.test_x\n",
        "from tests import test_alt\n\nsetattr(test_alt, 'test_x', None)\n",
        "import test_alt\n\n\ndef test_a(monkeypatch):\n"
        "    monkeypatch.setattr(test_alt, 'WERT', 1)\n",
    ],
)
def test_ueberschriebenes_testmodul_zaehlt(projekt, text):
    assert _zaehle(projekt, text) == {("tests/test_x.py", "test-versteckt"): 1}


def test_gelesenes_testmodul_zaehlt_nicht(projekt):
    text = "from test_alt import HEUTE\nimport test_b\n\nX = getattr(test_b, 'Y')\n"
    assert _zaehle(projekt, text) == {}
