"""Die Hermetik aus tests/conftest.py: Bestand und Netz sind gesperrt, mit Regelmeldung.

Geprüft wird in eigenen Prozessen, weil ein Audit-Hook nicht wieder zu entfernen ist und
ein Verstoß hier im Prozess den Test im Abbau rot machen würde.
"""

import datetime as dt
import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

WURZEL = Path(__file__).resolve().parents[1]
CONFTEST = WURZEL / "tests" / "conftest.py"
_LADEN = f"""
import importlib.util, os, socket, sys
from pathlib import Path
spec = importlib.util.spec_from_file_location("hermetik", {str(CONFTEST)!r})
hermetik = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hermetik)
os.environ["PYTEST_CURRENT_TEST"] = os.environ.pop("PROBE_TEST", "")
W = Path({str(WURZEL)!r})
"""


def _lauf(code, test="tests/test_neu.py::test_x (call)", **umgebung):
    env = {k: v for k, v in os.environ.items() if not k.startswith("TELCO_TESTS")}
    env.update(PROBE_TEST=test, **umgebung)
    return subprocess.run(
        [sys.executable, "-c", _LADEN + textwrap.dedent(code)],
        capture_output=True,
        text=True,
        env=env,
        cwd=WURZEL,
        timeout=60,
    )


def test_zugriff_ueber_den_helfer_einer_anderen_testdatei_scheitert(tmp_path):
    code = _stapel(tmp_path) + "test_neu.test_x(W)\n"
    assert "Regel hermetisch" in _lauf(code).stderr


@pytest.mark.parametrize(
    ("zugriff", "pfad"),
    [
        ("(W / 'data/state/seen.jsonl').read_bytes()", "data/state/seen.jsonl"),
        ("open('data/state/seen.jsonl')", "data/state/seen.jsonl"),
        ("os.listdir(W / 'data/reports')", "data/reports"),
        ("(W / 'site/neu.html').write_text('x')", "site/neu.html"),
        ("os.open(str(W / 'site/index.html'), os.O_RDONLY)", "site/index.html"),
        ("sorted((W / 'data').glob('*'))", "data"),
        ("os.remove(W / 'site/gibt-es-nicht.html')", "site/gibt-es-nicht.html"),
    ],
)
def test_zugriff_auf_den_bestand_scheitert_mit_regel(zugriff, pfad):
    lauf = _lauf(zugriff)
    assert lauf.returncode != 0
    assert "HermetikVerstoss: Regel hermetisch: Tests lesen nur Schnappschüsse" in (
        lauf.stderr
    )
    assert f"(tests/test_neu.py griff auf {pfad})" in lauf.stderr
    assert not (WURZEL / "site" / "neu.html").exists()


def test_andere_pfade_und_schnappschuss_bleiben_offen(tmp_path):
    (tmp_path / "data").mkdir()
    lauf = _lauf(
        f"""
        (Path({str(tmp_path)!r}) / 'data' / 'x.txt').write_text('ok')
        print((W / 'config/settings.yaml').read_text()[:1])
        print(len(list((W / 'tests/fixtures/bestand').iterdir())))
        """
    )
    assert lauf.returncode == 0, lauf.stderr


def _stapel(tmp_path):
    """Eine Datei mit Helfer und eine neue Datei, die ihn ruft."""
    tests = tmp_path / "tests"
    tests.mkdir()
    (tests / "test_alt.py").write_text(
        "def lies(w):\n    return (w / 'data/state/seen.jsonl').read_bytes()\n"
    )
    (tests / "test_neu.py").write_text(
        "import test_alt\n\n\ndef test_x(w):\n    return test_alt.lies(w)\n"
    )
    return f"""
        hermetik.TESTS = {str(tests)!r} + os.sep
        hermetik.WURZEL = Path({str(tmp_path)!r})
        sys.path.insert(0, {str(tests)!r})
        import test_neu
        """


def test_beim_sammeln_zaehlt_die_aeusserste_testdatei(tmp_path):
    lauf = _lauf(_stapel(tmp_path) + "test_neu.test_x(W)\n", test="")
    assert "(tests/test_neu.py griff auf data/state/seen.jsonl)" in lauf.stderr


@pytest.mark.parametrize(
    ("zugriff", "pfad"),
    [
        ("Path('/proc/self/cwd/data/state/seen.jsonl').read_bytes()", "data/state"),
        ("os.chdir(W / 'data/state')", "data/state"),
        (
            "import subprocess as s; s.run(['head', str(W / 'data/state/seen.jsonl')])",
            "data/state/seen.jsonl",
        ),
        (
            "import subprocess as s; s.run('head ' + str(W / 'site/a'), shell=True)",
            "site/a",
        ),
        ("import subprocess; subprocess.run(['ls'], cwd=W / 'data')", "data"),
    ],
)
def test_umwege_ueber_proc_chdir_und_kindprozess_scheitern(zugriff, pfad):
    lauf = _lauf(zugriff)
    assert "HermetikVerstoss: Regel hermetisch" in lauf.stderr
    assert f"griff auf {pfad}" in lauf.stderr


def test_verweis_auf_den_bestand_ueber_symlink_scheitert(tmp_path):
    lauf = _lauf(
        f"""
        zeiger = Path({str(tmp_path / "zeiger")!r})
        os.symlink(os.path.relpath(hermetik.GESPERRT[0], zeiger.parent), zeiger)
        (zeiger / 'state/seen.jsonl').read_bytes()
        """
    )
    assert "Regel hermetisch: Tests lesen nur Schnappschüsse" in lauf.stderr
    assert "griff auf data" in lauf.stderr


def test_relativer_pfad_im_kindprozess_gilt_in_dessen_ordner(tmp_path):
    (tmp_path / "data").mkdir()
    lauf = _lauf(
        f"import subprocess as s; s.run(['ls', 'data/'], cwd={str(tmp_path)!r})"
    )
    assert lauf.returncode == 0, lauf.stderr
    assert (
        "Regel hermetisch"
        in _lauf("import subprocess as s; s.run(['ls', 'data/'])").stderr
    )


def test_kindprozess_ohne_bestand_bleibt_offen():
    lauf = _lauf(
        "import subprocess; subprocess.run(['git', 'rev-parse', 'HEAD'], check=True)"
    )
    assert lauf.returncode == 0, lauf.stderr


@pytest.mark.parametrize(
    "zugriff",
    [
        "socket.getaddrinfo('example.com', 443)",
        "socket.gethostbyname('example.com')",
        "socket.create_connection(('192.0.2.1', 9), timeout=0.1)",
    ],
)
def test_netz_scheitert_mit_regel(zugriff):
    lauf = _lauf(zugriff)
    assert "HermetikVerstoss: Regel hermetisch: Tests rufen kein Netz" in lauf.stderr


def test_lokaler_proxy_fuehrt_nicht_an_der_sperre_vorbei():
    lauf = _lauf(
        "import httpx; httpx.get('https://example.com', timeout=5)",
        HTTPS_PROXY="http://127.0.0.1:9",
        http_proxy="http://127.0.0.1:9",
    )
    assert "HermetikVerstoss: Regel hermetisch: Tests rufen kein Netz" in lauf.stderr
    assert "wollte example.com" in lauf.stderr


def test_lokales_netz_bleibt_offen():
    lauf = _lauf(
        """
        server = socket.create_server(('127.0.0.1', 0))
        client = socket.create_connection(server.getsockname(), timeout=5)
        socket.getaddrinfo('localhost', 80)
        client.close(); server.close()
        """
    )
    assert lauf.returncode == 0, lauf.stderr


def _pytest(tmp_path, testcode, *argumente):
    (tmp_path / "test_probe.py").write_text(textwrap.dedent(testcode), "utf-8")
    env = {k: v for k, v in os.environ.items() if not k.startswith("PYTEST_")}
    env["PYTHONPATH"] = str(CONFTEST.parent)
    return subprocess.run(
        [sys.executable, "-m", "pytest", "-p", "conftest", "-p", "no:cacheprovider"]
        + ["-q", "-rfE", "--rootdir", str(tmp_path), str(tmp_path), *argumente],
        capture_output=True,
        text=True,
        env={**env, "COLUMNS": "400"},
        cwd=tmp_path,
        timeout=120,
    )


def test_geschluckter_verstoss_macht_den_test_im_abbau_rot(tmp_path):
    lauf = _pytest(
        tmp_path,
        f"""
        def test_schluckt():
            try:
                open({str(WURZEL / "data/state/seen.jsonl")!r})
            except Exception:
                pass

        def test_danach_sauber():
            pass
        """,
    )
    assert (
        "ERROR test_probe.py::test_schluckt - Failed: Regel hermetisch" in lauf.stdout
    )
    assert "2 passed, 1 error" in lauf.stdout


def test_chromium_setzt_den_marker_browser(tmp_path):
    lauf = _pytest(
        tmp_path,
        """
        def test_mit(chromium):
            pass

        def test_ohne():
            pass
        """,
        "--collect-only",
        "-m",
        "browser",
    )
    assert "1/2 tests collected (1 deselected)" in lauf.stdout, lauf.stdout


@pytest.mark.parametrize(
    "adresse",
    ["http://example.com/", "http://192.0.2.1/", "https://fonts.googleapis.com/"],
)
def test_chromium_erreicht_nur_lokale_adressen(chromium, adresse):
    seite = chromium.new_page()
    try:
        with pytest.raises(Exception, match="net::ERR_"):
            seite.goto(adresse, timeout=10_000)
    finally:
        seite.close()


def test_chromium_laedt_lokale_seite(chromium, tmp_path):
    (tmp_path / "a.html").write_text("<p>lokal</p>", "utf-8")
    seite = chromium.new_page()
    try:
        seite.goto((tmp_path / "a.html").as_uri())
        assert seite.inner_text("p") == "lokal"
    finally:
        seite.close()


def test_uhr_der_tests_ist_der_schnappschuss(jetzt, heute, herkunft, bestand):
    assert jetzt == dt.datetime.fromisoformat(herkunft["zeit"])
    assert jetzt.tzinfo is not None and jetzt.utcoffset() == dt.timedelta(0)
    assert heute == dt.date.fromisoformat(bestand.name)
    assert herkunft["autor"] == "telco-radar-bot"
    assert json.loads((bestand / "_herkunft.json").read_text("utf-8")) == herkunft
