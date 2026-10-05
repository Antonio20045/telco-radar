import importlib
import json
import os
import signal
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

leiter_schnell = importlib.import_module("leiter_schnell")
waechter_speicher = importlib.import_module("waechter_speicher")


@pytest.mark.parametrize(
    ("pfad", "namen"),
    [
        ("src/telco_radar/report/html.py", {"telco_radar.report.html"}),
        ("src/telco_radar/report/__init__.py", {"telco_radar.report"}),
        ("scripts/waechter.py", {"scripts.waechter", "waechter"}),
        (
            "scripts/newsletter/versand.py",
            {"scripts.newsletter.versand", "newsletter.versand", "versand"},
        ),
        ("tests/bestand_pfad.py", {"tests.bestand_pfad", "bestand_pfad"}),
        ("service/signup/app.py", {"service.signup.app"}),
        ("src/telco_radar/report/templates/style.css", set()),
    ],
)
def test_modulnamen_je_ort(pfad, namen):
    assert leiter_schnell.modulnamen(pfad) == namen


def test_importe_kennt_import_from_und_laden_ueber_den_namen():
    text = (
        "import os, telco_radar.models\n"
        "from telco_radar.report import html as h\n"
        "import importlib.util\n"
        'spec = importlib.util.spec_from_file_location("stand", "x.py")\n'
        'modul = importlib.import_module("waechter")\n'
    )
    assert {
        "os",
        "telco_radar.models",
        "telco_radar.report",
        "telco_radar.report.html",
        "stand",
        "waechter",
    } <= leiter_schnell.importe(text)


def test_marker_seite_am_test_oder_am_modul():
    assert leiter_schnell.hat_marker_seite("@pytest.mark.seite\ndef test_a(): pass\n")
    assert leiter_schnell.hat_marker_seite("pytestmark = [pytest.mark.seite]\n")
    assert not leiter_schnell.hat_marker_seite("@pytest.mark.browser\ndef test(): 1\n")


@pytest.fixture()
def projekt(tmp_path):
    tests = tmp_path / "tests"
    (tests / "orakel").mkdir(parents=True)
    (tests / "test_html.py").write_text(
        "from telco_radar.report import html\n", "utf-8"
    )
    (tests / "test_modelle.py").write_text("import telco_radar.models\n", "utf-8")
    (tests / "orakel/test_seite.py").write_text(
        "import pytest\n\n\n@pytest.mark.seite\ndef test_a():\n    pass\n", "utf-8"
    )
    (tests / "test_leiter.py").write_text(
        'import importlib.util\nimportlib.util.spec_from_file_location("stand", "")\n',
        "utf-8",
    )
    (tests / "hilfe.py").write_text("import telco_radar.models\n", "utf-8")
    return tmp_path


def test_geaendertes_modul_zieht_nur_seine_direkten_importeure(projekt):
    auswahl = leiter_schnell.betroffene(projekt, ["src/telco_radar/models.py"])
    assert auswahl.dateien == ["tests/test_modelle.py"]
    assert auswahl.alle == []


def test_vorlage_zieht_marker_seite_und_die_importeure_von_report_html(projekt):
    auswahl = leiter_schnell.betroffene(
        projekt, ["src/telco_radar/report/templates/app.js"]
    )
    assert auswahl.dateien == ["tests/orakel/test_seite.py", "tests/test_html.py"]


def test_skript_und_geaenderter_test_ziehen_ihre_dateien(projekt):
    auswahl = leiter_schnell.betroffene(
        projekt, ["scripts/stand.py", "tests/test_modelle.py"]
    )
    assert auswahl.dateien == ["tests/test_leiter.py", "tests/test_modelle.py"]


@pytest.mark.parametrize(
    "pfad",
    [
        "config/settings.yaml",
        "pyproject.toml",
        "requirements-dev.txt",
        "tests/conftest.py",
        "tests/orakel/conftest.py",
    ],
)
def test_konfiguration_betrifft_alle_tests(projekt, pfad):
    assert leiter_schnell.betroffene(projekt, [pfad]).alle == [pfad]


def test_schaetzung_ohne_langsame_tests_und_mit_einer_sekunde_je_unbekannter_datei(
    monkeypatch,
):
    monkeypatch.setattr(leiter_schnell, "TESTBUDGET_SEKUNDEN", 100.0)
    zeiten = {
        "tests/test_a.py::eins": 2.5,
        "tests/test_a.py::zwei": 5.0,
        "tests/test_a.py::lang": 5.1,
        "tests/test_b.py::fremd": 9.0,
    }
    dateien = ["tests/test_a.py", "tests/neu.py"]
    abwahl = leiter_schnell.abwahl(dateien, zeiten)
    assert abwahl == ["tests/test_a.py::lang"]
    assert leiter_schnell.schaetzung(dateien, zeiten, abwahl) == 5.0 + 5.0 + 1.0
    assert leiter_schnell.langsame(["tests/test_a.py"], zeiten) == [
        "tests/test_a.py::lang"
    ]


def test_ueber_dem_budget_laufen_die_schnellsten_und_der_rest_im_pre_push(
    monkeypatch,
):
    monkeypatch.setattr(leiter_schnell, "TESTBUDGET_SEKUNDEN", 1.0)
    zeiten = {
        "tests/test_a.py::eins": 0.4,
        "tests/test_a.py::zwei": 0.5,
        "tests/test_a.py::drei": 0.3,
        "tests/test_a.py::lang": 5.1,
        "tests/test_b.py::fremd": 0.1,
    }
    abwahl = leiter_schnell.abwahl(["tests/test_a.py"], zeiten)
    assert abwahl == ["tests/test_a.py::lang", "tests/test_a.py::zwei"]
    assert leiter_schnell.schaetzung(["tests/test_a.py"], zeiten, abwahl) == 0.9


def test_teurer_fixture_aufbau_nimmt_die_ganze_datei_aus_dem_budget(monkeypatch):
    monkeypatch.setattr(leiter_schnell, "TESTBUDGET_SEKUNDEN", 1.0)
    zeiten = {
        "tests/test_seite.py::aufbau": 4.0,
        "tests/test_seite.py::billig": 0.01,
        "tests/test_logik.py::eins": 0.2,
    }
    dateien = ["tests/test_logik.py", "tests/test_seite.py"]
    assert leiter_schnell.abwahl(dateien, zeiten) == [
        "tests/test_seite.py::aufbau",
        "tests/test_seite.py::billig",
    ]


def test_ein_langsamer_test_sperrt_die_schnellen_seiner_datei_nicht(monkeypatch):
    monkeypatch.setattr(leiter_schnell, "TESTBUDGET_SEKUNDEN", 1.0)
    zeiten = {"tests/test_a.py::lang": 30.0, "tests/test_a.py::schnell": 0.2}
    assert leiter_schnell.abwahl(["tests/test_a.py"], zeiten) == [
        "tests/test_a.py::lang"
    ]


def test_ungemessene_dateien_belegen_vorab_budget(monkeypatch):
    monkeypatch.setattr(leiter_schnell, "TESTBUDGET_SEKUNDEN", 1.5)
    zeiten = {"tests/test_a.py::eins": 0.6}
    assert leiter_schnell.abwahl(["tests/test_a.py"], zeiten) == []
    dateien = ["tests/test_a.py", "tests/test_neu.py"]
    assert leiter_schnell.abwahl(dateien, zeiten) == ["tests/test_a.py::eins"]


def test_geaenderte_testdateien_gehen_im_budget_vor(monkeypatch):
    monkeypatch.setattr(leiter_schnell, "TESTBUDGET_SEKUNDEN", 1.0)
    zeiten = {"tests/test_alt.py::a": 0.1, "tests/test_neu.py::b": 0.95}
    dateien = ["tests/test_alt.py", "tests/test_neu.py"]
    assert leiter_schnell.abwahl(dateien, zeiten) == ["tests/test_neu.py::b"]
    vorrang = ["tests/test_neu.py"]
    assert leiter_schnell.abwahl(dateien, zeiten, vorrang) == ["tests/test_alt.py::a"]


def test_stufe_vier_laesst_die_geaenderte_testdatei_zuerst_laufen(projekt, monkeypatch):
    monkeypatch.setattr(leiter_schnell, "TESTBUDGET_SEKUNDEN", 1.0)
    zeiten = projekt / "zeiten.json"
    gemessen = {"tests/test_html.py::a": 0.95, "tests/test_modelle.py::b": 0.1}
    zeiten.write_text(json.dumps({"tests": gemessen}), "utf-8")
    lauf, aufrufe = _lauf_mit(0)
    geaendert = ["src/telco_radar/models.py", "tests/test_html.py"]
    leiter_schnell.stufe_betroffen(None, lauf, projekt, geaendert, zeiten)
    assert "--deselect=tests/test_modelle.py::b" in aufrufe[0][0]
    assert "--deselect=tests/test_html.py::a" not in aufrufe[0][0]


def test_stufe_vier_waehlt_ueber_dem_budget_ab_und_sagt_es(projekt, monkeypatch):
    monkeypatch.setattr(leiter_schnell, "TESTBUDGET_SEKUNDEN", 0.5)
    zeiten = projekt / "zeiten.json"
    zeiten.write_text(
        json.dumps({"tests": {"tests/test_modelle.py::test_a": 0.6}}), "utf-8"
    )
    lauf, aufrufe = _lauf_mit(0)
    ergebnis = leiter_schnell.stufe_betroffen(
        None, lauf, projekt, ["src/telco_radar/models.py"], zeiten
    )
    assert ergebnis.gruen
    assert "--deselect=tests/test_modelle.py::test_a" in aufrufe[0][0]
    assert ergebnis.hinweise == [
        "Stufe 4: 1 langsame oder über 0.5 s Budget, Stufe 5 im pre-push"
    ]


def test_langsame_tests_werden_abgewaehlt():
    befehl = leiter_schnell.pytest_befehl(["t.py"], 1.0, ["t.py::lang[a b]"])
    assert befehl[-2:] == ["--deselect=t.py::lang[a b]", "t.py"]


def test_kaputte_zeitdatei_heisst_keine_messung(tmp_path):
    (tmp_path / "z.json").write_text("[1]", "utf-8")
    assert leiter_schnell.lies_testzeiten(tmp_path / "z.json") == {}
    assert leiter_schnell.lies_testzeiten(tmp_path / "fehlt.json") == {}


def test_ab_vier_sekunden_schaetzung_mit_vier_workern():
    assert leiter_schnell.pytest_befehl(["t.py"], 3.9)[-3:] == ["-n", "0", "t.py"]
    assert leiter_schnell.pytest_befehl(["t.py"], 4.0)[-3:] == ["-n", "4", "t.py"]
    befehl = leiter_schnell.pytest_befehl(["t.py"], 1.0)
    auswahl = "not browser and not langsam and not golden and not netz"
    assert befehl[befehl.index(auswahl) - 1] == "-m"


def test_testzeiten_aus_den_startzeiten_je_prozess(tmp_path):
    (tmp_path / "1.zeit").write_text(
        "10.000 tests/test_a.py::test_eins\n"
        "12.500 tests/test_a.py::test_zwei\n"
        "13.000 tests/test_b.py::test_drei[x y]\n",
        "utf-8",
    )
    (tmp_path / "2.zeit").write_text("5.000 tests/test_b.py::test_vier\n", "utf-8")
    ziel = tmp_path / "zeiten.json"
    leiter_schnell.schreibe_testzeiten(tmp_path, ziel)
    assert leiter_schnell.lies_testzeiten(ziel) == {
        "tests/test_a.py::test_eins": 2.5,
        "tests/test_a.py::test_zwei": 0.5,
        "tests/test_b.py::test_drei[x y]": 1.0,
        "tests/test_b.py::test_vier": 1.0,
    }


def _lauf_mit(code, stdout=""):
    aufrufe = []

    def lauf(log, befehl, zusatz=None, frist=None):
        aufrufe.append((befehl, frist))
        return subprocess.CompletedProcess(befehl, code, stdout, "")

    return lauf, aufrufe


def test_stufe_vier_ist_rot_mit_den_kurzzeilen_von_pytest(projekt):
    lauf, aufrufe = _lauf_mit(1, "FAILED tests/test_modelle.py::test_a - x\nrest\n")
    ergebnis = leiter_schnell.stufe_betroffen(
        None, lauf, projekt, ["src/telco_radar/models.py"], projekt / "fehlt.json"
    )
    assert not ergebnis.gruen
    assert ergebnis.zeilen == ["FAILED tests/test_modelle.py::test_a - x"]
    assert aufrufe[0][1] == leiter_schnell.KAPPE_SEKUNDEN


def test_fremder_kill_ist_keine_kappe_sondern_rot(projekt):
    lauf, _ = _lauf_mit(-signal.SIGKILL)
    ergebnis = leiter_schnell.stufe_betroffen(
        None, lauf, projekt, ["src/telco_radar/models.py"], projekt / "fehlt.json"
    )
    assert not ergebnis.gruen


def test_stufe_vier_nach_der_kappe_ist_eine_warnung(projekt):
    def lauf(log, befehl, zusatz=None, frist=None):
        fehler = f"\nabgebrochen nach {frist} s\n"
        return subprocess.CompletedProcess(befehl, -signal.SIGKILL, "", fehler)

    ergebnis = leiter_schnell.stufe_betroffen(
        None, lauf, projekt, ["src/telco_radar/models.py"], projekt / "fehlt.json"
    )
    assert ergebnis.gruen
    assert ergebnis.hinweise[0].startswith("Warnung: Stufe 4 nach 45 s gekappt")


def test_stufe_vier_ohne_betroffene_tests_startet_kein_pytest(projekt):
    lauf, aufrufe = _lauf_mit(1)
    ergebnis = leiter_schnell.stufe_betroffen(
        None, lauf, projekt, ["pyproject.toml"], projekt / "fehlt.json"
    )
    assert ergebnis.gruen
    assert aufrufe == []
    assert "betrifft alle Tests" in ergebnis.hinweise[0]


def test_stufe_vier_bricht_pytest_ab_ist_rot(projekt):
    lauf, _ = _lauf_mit(2, "ImportError\n")
    ergebnis = leiter_schnell.stufe_betroffen(
        None, lauf, projekt, ["src/telco_radar/models.py"], projekt / "fehlt.json"
    )
    assert not ergebnis.gruen
    assert ergebnis.zeilen[0] == "pytest endet mit 2:"


def test_lint_auf_den_dateien_ist_rot_ueber_der_basis_und_schreibt_nichts(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(leiter_schnell, "WURZEL", tmp_path)
    (tmp_path / "a.py").write_text("import os\n", "utf-8")
    basis = tmp_path / "basis.json"
    basis.write_text("{}\n", "utf-8")
    befund = [
        {
            "filename": str(tmp_path / "a.py"),
            "location": {"row": 1},
            "code": "F401",
            "message": "os",
        }
    ]
    antworten = iter([(0, ""), (1, json.dumps(befund))])

    def lauf(log, befehl, zusatz=None, frist=None):
        code, stdout = next(antworten)
        return subprocess.CompletedProcess(befehl, code, stdout, "")

    ergebnis = leiter_schnell.stufe_lint(None, lauf, "ruff", ["a.py"], basis)
    assert not ergebnis.gruen
    assert "[F401]" in ergebnis.zeilen[0]
    assert basis.read_text("utf-8") == "{}\n"


def test_lint_ohne_python_dateien_ist_gruen_ohne_ruff():
    lauf, aufrufe = _lauf_mit(1)
    assert leiter_schnell.stufe_lint(None, lauf, "ruff", ["a.css"], Path("x")).gruen
    assert aufrufe == []


def test_budget_warnung_erst_ueber_dem_budget():
    assert leiter_schnell.budget_warnung(30.0) == []
    assert leiter_schnell.budget_warnung(31.0)[0].startswith("Warnung: 31 s")


def test_speicher_rechnet_jeden_inhalt_einmal_und_vergisst_ungenutztes(tmp_path):
    datei = tmp_path / "speicher.json"
    gerechnet = []

    def rechne(text):
        gerechnet.append(text)
        return [text.upper()]

    with waechter_speicher.aktiv(datei):
        assert waechter_speicher.hole("a", "x.py", "eins", lambda: rechne("eins")) == [
            "EINS"
        ]
        waechter_speicher.hole("a", "y.py", "zwei", lambda: rechne("zwei"))
    with waechter_speicher.aktiv(datei):
        assert waechter_speicher.hole("a", "x.py", "eins", lambda: rechne("x")) == [
            "EINS"
        ]
        waechter_speicher.hole("a", "x.py", "drei", lambda: rechne("drei"))
    assert gerechnet == ["eins", "zwei", "drei"]
    gespeichert = json.loads(datei.read_text("utf-8"))["eintraege"]
    assert len(gespeichert) == 2


def test_ohne_aktiven_speicher_rechnet_jede_pruefung_neu(tmp_path):
    datei = tmp_path / "speicher.json"
    with waechter_speicher.aktiv(datei):
        waechter_speicher.hole("a", "x.py", "eins", lambda: ["alt"])
    assert waechter_speicher.hole("a", "x.py", "eins", lambda: ["neu"]) == ["neu"]


def test_geaenderte_waechter_verwerfen_den_speicher(tmp_path, monkeypatch):
    datei = tmp_path / "speicher.json"
    with waechter_speicher.aktiv(datei):
        waechter_speicher.hole("a", "x.py", "eins", lambda: ["alt"])
    monkeypatch.setattr(waechter_speicher, "version", lambda: "andere Regeln")
    with waechter_speicher.aktiv(datei):
        assert waechter_speicher.hole("a", "x.py", "eins", lambda: ["neu"]) == ["neu"]


def test_verfaelschter_speicher_trifft_nur_seinen_eigenen_inhalt(tmp_path):
    datei = tmp_path / "speicher.json"
    with waechter_speicher.aktiv(datei):
        waechter_speicher.hole("a", "x.py", "geheim", lambda: [])
    with waechter_speicher.aktiv(datei):
        assert waechter_speicher.hole("a", "x.py", "geheim!", lambda: ["rot"]) == [
            "rot"
        ]


def test_waechter_zaehlen_mit_speicher_genauso_wie_ohne(tmp_path):
    waechter_regeln = importlib.import_module("waechter_regeln")
    waechter_tests = importlib.import_module("waechter_tests")
    waechter_vertraege = importlib.import_module("waechter_vertraege")

    (tmp_path / "src/telco_radar").mkdir(parents=True)
    (tmp_path / "src/telco_radar/a.py").write_text(
        "import datetime\n\n\ndef f():\n    return datetime.datetime.now()\n", "utf-8"
    )
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests/test_a.py").write_text(
        "import inspect\nimport time\n\n\ndef test_a():\n"
        "    inspect.getsource(test_a)\n    time.time()\n",
        "utf-8",
    )

    def zaehlen():
        return (
            waechter_regeln.waechter_zaehlung(tmp_path),
            waechter_tests.tests_zaehlung(tmp_path),
            waechter_vertraege.quelltext_in_tests(tmp_path),
        )

    ohne = zaehlen()
    assert ohne[0][("src/telco_radar/a.py", "uhr")] == 1
    assert ohne[1][("tests/test_a.py", "uhr")] == 1
    assert ohne[2]
    datei = tmp_path / "speicher.json"
    with waechter_speicher.aktiv(datei):
        assert zaehlen() == ohne
    with waechter_speicher.aktiv(datei):
        assert zaehlen() == ohne


def test_kaputte_testdatei_wird_mitgewaehlt_statt_die_leiter_abzubrechen(projekt):
    (projekt / "tests/test_kaputt.py").write_text("def test_x(:\n", "utf-8")
    auswahl = leiter_schnell.betroffene(projekt, ["src/telco_radar/models.py"])
    assert auswahl.dateien == ["tests/test_kaputt.py", "tests/test_modelle.py"]


def test_testdateien_kennen_beide_muster(projekt):
    (projekt / "tests/modelle_test.py").write_text("import telco_radar.models\n")
    auswahl = leiter_schnell.betroffene(projekt, ["src/telco_radar/models.py"])
    assert auswahl.dateien == ["tests/modelle_test.py", "tests/test_modelle.py"]


def test_abgeschnittene_zeitzeile_wird_uebergangen(tmp_path):
    (tmp_path / "1.zeit").write_text(
        "1.000 tests/test_a.py::t\n3.000 tests/test_a.py::u\n4.0", "utf-8"
    )
    ziel = tmp_path / "zeiten.json"
    leiter_schnell.schreibe_testzeiten(tmp_path, ziel)
    assert leiter_schnell.lies_testzeiten(ziel) == {
        "tests/test_a.py::t": 2.0,
        "tests/test_a.py::u": 1.0,
    }


def _git(ort, *argumente, **umgebung):
    rein = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    return subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid", *argumente],
        cwd=ort,
        env={**rein, **umgebung},
        capture_output=True,
        text=True,
        check=True,
    ).stdout


@pytest.fixture()
def repo(tmp_path):
    _git(tmp_path, "init", "-q", "-b", "main")
    for name in ("a.py", "b.py", "c.py"):
        (tmp_path / name).write_text("x = 1\n", "utf-8")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-q", "-m", "a")
    return tmp_path


def test_geaenderte_dateien_vorgemerkt_liest_den_index_des_hooks(repo, monkeypatch):
    (repo / "a.py").write_text("x = 2\n", "utf-8")
    (repo / "b.py").write_text("x = 2\n", "utf-8")
    (repo / "neu.py").write_text("x = 2\n", "utf-8")
    _git(repo, "add", "a.py")
    assert leiter_schnell.geaenderte_dateien(repo, nur_vorgemerkt=True) == ["a.py"]
    assert leiter_schnell.geaenderte_dateien(repo, nur_vorgemerkt=False) == [
        "a.py",
        "b.py",
        "neu.py",
    ]
    hook_index = repo / "hook-index"
    _git(repo, "read-tree", "HEAD", GIT_INDEX_FILE=str(hook_index))
    _git(repo, "add", "c.py", GIT_INDEX_FILE=str(hook_index))
    (repo / "c.py").write_text("x = 3\n", "utf-8")
    _git(repo, "add", "c.py", GIT_INDEX_FILE=str(hook_index))
    monkeypatch.setenv("GIT_INDEX_FILE", str(hook_index))
    assert leiter_schnell.geaenderte_dateien(repo, nur_vorgemerkt=True) == ["c.py"]


def test_leckpruefung_mit_speicher_findet_einen_neuen_schluessel(repo, tmp_path):
    waechter_leck = importlib.import_module("waechter_leck")
    datei = tmp_path / "speicher.json"
    with waechter_speicher.aktiv(datei):
        assert waechter_leck.lecks(repo) == []
    muster = "x" + "keysib-" + "abc123"
    (repo / "a.py").write_text(f"k = '{muster}'\n", "utf-8")
    with waechter_speicher.aktiv(datei):
        assert waechter_leck.lecks(repo) == [
            "a.py: Brevo-Schlüssel im Repo (gehört in ein Secret)"
        ]
    _git(repo, "add", "a.py")
    with waechter_speicher.aktiv(datei):
        assert waechter_leck.lecks(repo) == [
            "a.py: Brevo-Schlüssel im Repo (gehört in ein Secret)"
        ]


def test_lauf_ohne_aufzeichnung_laesst_die_letzte_messung_stehen(tmp_path):
    ziel = tmp_path / "zeiten.json"
    ziel.write_text('{"tests": {"tests/test_a.py::t": 2.0}}', "utf-8")
    leiter_schnell.schreibe_testzeiten(tmp_path, ziel)
    assert leiter_schnell.lies_testzeiten(ziel) == {"tests/test_a.py::t": 2.0}
