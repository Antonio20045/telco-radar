import importlib.util
import json
import os
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path

import pytest

_PFAD = Path(__file__).resolve().parents[1] / "scripts" / "pruefleiter.py"
sys.path.insert(0, str(_PFAD.parent))
_spec = importlib.util.spec_from_file_location("pruefleiter", _PFAD)
pruefleiter = importlib.util.module_from_spec(_spec)
sys.modules["pruefleiter"] = pruefleiter
_spec.loader.exec_module(pruefleiter)

Befund = pruefleiter.Befund


def _befunde(*schluessel):
    return [
        Befund(pfad, nr, code, "text") for nr, (pfad, code) in enumerate(schluessel)
    ]


def test_verschobene_zeile_ist_kein_neuer_befund():
    basis = Counter({("a.py", "F401"): 2})
    befunde = [Befund("a.py", 90, "F401", "x"), Befund("a.py", 91, "F401", "y")]
    assert pruefleiter.neue_befunde(befunde, basis) == []


def test_ein_befund_mehr_meldet_alle_befunde_der_datei_und_des_codes():
    basis = Counter({("a.py", "F401"): 1, ("b.py", "E501"): 1})
    befunde = _befunde(("a.py", "F401"), ("a.py", "F401"), ("b.py", "E501"))
    neu = pruefleiter.neue_befunde(befunde, basis)
    assert [b.schluessel for b in neu] == [("a.py", "F401")] * 2


def test_neue_datei_oder_neuer_code_ist_neu():
    basis = Counter({("a.py", "F401"): 1})
    befunde = _befunde(("a.py", "F401"), ("a.py", "E741"), ("neu.py", "F401"))
    neu = pruefleiter.neue_befunde(befunde, basis)
    assert {b.schluessel for b in neu} == {("a.py", "E741"), ("neu.py", "F401")}


def test_basis_sinkt_auf_den_heutigen_stand_und_verschwundenes_faellt_weg():
    basis = Counter({("a.py", "F401"): 3, ("weg.py", "E501"): 2, ("b.py", "B007"): 1})
    befunde = _befunde(("a.py", "F401"), ("b.py", "B007"), ("b.py", "B007"))
    gesenkt = pruefleiter.gesenkte_basis(befunde, basis)
    assert gesenkt == Counter({("a.py", "F401"): 1, ("b.py", "B007"): 1})


@pytest.mark.parametrize("endung", [".json", ".txt"])
def test_basis_liest_sich_so_wie_sie_geschrieben_wurde(tmp_path, endung):
    pfad = tmp_path / f"basis{endung}"
    basis = Counter(
        {("src/a.py", "F401"): 2, ("src/a.py", "E501"): 1, ("b.py", "x-y"): 4}
    )
    pruefleiter.schreibe_zaehlbasis(pfad, basis)
    assert pruefleiter.lies_zaehlbasis(pfad) == basis


def test_vergleich_senkt_die_basis_bei_gruen(tmp_path):
    pfad = tmp_path / "basis.txt"
    pruefleiter.schreibe_zaehlbasis(pfad, Counter({("a.py", "arg-type"): 2}))
    ergebnis = pruefleiter.vergleiche("2 Typen", _befunde(("a.py", "arg-type")), pfad)
    assert ergebnis.gruen
    assert pruefleiter.lies_zaehlbasis(pfad) == Counter({("a.py", "arg-type"): 1})


def test_vergleich_ist_rot_und_laesst_die_basis_stehen(tmp_path):
    pfad = tmp_path / "basis.json"
    basis = Counter({("a.py", "F401"): 1, ("b.py", "E501"): 3})
    pruefleiter.schreibe_zaehlbasis(pfad, basis)
    befunde = _befunde(("a.py", "F401"), ("a.py", "F401"))
    ergebnis = pruefleiter.vergleiche("1 Lint", befunde, pfad)
    assert not ergebnis.gruen
    assert ergebnis.zeilen[0].startswith("a.py:0 [F401] erwartet höchstens 1")
    assert pruefleiter.lies_zaehlbasis(pfad) == basis


def test_mypy_zeilen_mit_spalte_ohne_code_und_hinweise():
    ausgabe = (
        "src/a.py:12: error: Incompatible types  [assignment]\n"
        "src/a.py:12: note: See https://mypy.rtfd.io\n"
        'src/b.py:3:7: error: Name "x" is not defined  [name-defined]\n'
        "src/c.py:1: error: kaputt\n"
        "Found 3 errors in 3 files (checked 9 source files)\n"
    )
    assert pruefleiter.mypy_befunde(ausgabe) == [
        Befund("src/a.py", 12, "assignment", "Incompatible types"),
        Befund("src/b.py", 3, "name-defined", 'Name "x" is not defined'),
        Befund("src/c.py", 1, "ohne-code", "kaputt"),
    ]


def test_ruff_json_wird_relativ_zur_wurzel():
    eintrag = {
        "filename": str(pruefleiter.WURZEL / "src" / "a.py"),
        "location": {"row": 4, "column": 1},
        "code": "F401",
        "message": "`os` imported but unused",
    }
    syntax = {**eintrag, "code": None, "message": "SyntaxError"}
    befunde = pruefleiter.ruff_befunde(json.dumps([eintrag, syntax]))
    assert [b.schluessel for b in befunde] == [
        ("src/a.py", "F401"),
        ("src/a.py", "syntax"),
    ]


_KANARIE = (
    f"FAILED {pruefleiter.KANARIE}::test_muss_scheitern - AssertionError\n"
    f"PASSED {pruefleiter.KANARIE}::test_muss_bestehen\n"
    f"FAILED {pruefleiter.KANARIE}::test_bestand_muss_scheitern - Regel hermetisch\n"
    f"FAILED {pruefleiter.KANARIE}::test_netz_muss_scheitern - Regel hermetisch\n"
)
_KOPF = "==== short test summary info ====\n" + _KANARIE
# Die Hermetik aus tests/conftest.py; Angriffe im Wegwerfprojekt hängen sich dahinter.
_HERMETIK = Path(__file__).with_name("conftest.py").read_text("utf-8")


@pytest.fixture(autouse=True)
def _untergrenze(tmp_path, monkeypatch):
    pfad = tmp_path / "tests-anzahl.txt"
    pfad.write_text("2\n", encoding="utf-8")
    monkeypatch.setattr(pruefleiter, "TESTS_ANZAHL", pfad)
    obergrenze = tmp_path / "tests-uebersprungen.txt"
    obergrenze.write_text("1\n", encoding="utf-8")
    monkeypatch.setattr(pruefleiter, "TESTS_UEBERSPRUNGEN", obergrenze)
    altlasten = tmp_path / "tests-mit-bestand.txt"
    altlasten.write_text("", encoding="utf-8")
    monkeypatch.setattr(pruefleiter, "TESTS_MIT_BESTAND", altlasten)
    return pfad


def _lauf_mit(monkeypatch, returncode, stdout, stderr="", gesammelt=2, uebersprungen=1):
    if gesammelt is not None:
        stdout = f"created: 4/4 workers\n4 workers [{gesammelt} items]\n" + stdout
        stdout += f"==== 1 passed, {uebersprungen} skipped in 0.12s ====\n"

    def falscher_lauf(log, befehl, zusatz=None):
        if "--collect-only" in befehl:
            rot, gruen = pruefleiter.pytest_ausgang(stdout)
            ids = "".join(f"{t}\n" for t in sorted({*rot, *gruen}))
            return subprocess.CompletedProcess(befehl, 0, ids + "\n", "")
        if zusatz:
            _roh_wie_gemeldet(
                Path(zusatz[pruefleiter.leiter_pytest.ROH_VARIABLE]), stdout
            )
        return subprocess.CompletedProcess(befehl, returncode, stdout, stderr)

    monkeypatch.setattr(pruefleiter, "_lauf", falscher_lauf)


def _roh_wie_gemeldet(ordner, stdout):
    """Schreibt die Rohaufzeichnung so, wie ein ehrlicher Lauf sie hinterließe."""
    rot, gruen = pruefleiter.pytest_ausgang(stdout)
    zeilen = [f"fehler {t}\n" for t in rot if t not in gruen]
    zeilen += [f"ok {t}\n" for t in gruen]
    (ordner / "1.txt").write_text("".join(zeilen), encoding="utf-8")
    gelaufen = "".join(f"lief {t}\n" for t in sorted({*rot, *gruen}))
    (ordner / "1.lief").write_text(gelaufen, encoding="utf-8")


def _bekannt(tmp_path, monkeypatch, *tests):
    pfad = tmp_path / "rot-bekannt.txt"
    pfad.write_text("".join(f"{t}\n" for t in tests), encoding="utf-8")
    monkeypatch.setattr(pruefleiter, "ROT_BEKANNT", pfad)
    return pfad


def test_bekannt_roter_test_bleibt_gruen_und_geheilter_faellt_aus_der_liste(
    tmp_path, monkeypatch
):
    pfad = _bekannt(tmp_path, monkeypatch, "tests/a.py::t1", "tests/a.py::t2")
    _lauf_mit(
        monkeypatch,
        1,
        "ERROR    telco_radar.x:x.py:1 Protokollzeile im Fehlerbericht\n"
        + _KOPF
        + "PASSED tests/a.py::t2\nPASSED tests/b.py::t[x - y]\n"
        "FAILED tests/a.py::t1 - AssertionError: 1 != 2\n",
    )
    ergebnis = pruefleiter.stufe_tests(None)
    assert ergebnis.gruen
    assert pfad.read_text(encoding="utf-8") == "tests/a.py::t1\n"


def test_neuer_roter_test_ist_rot_und_die_liste_bleibt(tmp_path, monkeypatch):
    pfad = _bekannt(tmp_path, monkeypatch, "tests/a.py::t1")
    _lauf_mit(
        monkeypatch,
        1,
        _KOPF + "PASSED tests/a.py::t1\nERROR tests/c.py - ImportError: x\n",
    )
    ergebnis = pruefleiter.stufe_tests(None)
    assert not ergebnis.gruen
    assert ergebnis.zeilen == ["ERROR tests/c.py - ImportError: x"]
    assert pfad.read_text(encoding="utf-8") == "tests/a.py::t1\n"


@pytest.mark.parametrize(
    ("code", "ausgabe"), [(2, "Interrupted"), (1, "kaputt"), (5, "")]
)
def test_abbruch_von_pytest_ist_nie_gruen(tmp_path, monkeypatch, code, ausgabe):
    _bekannt(tmp_path, monkeypatch)
    _lauf_mit(monkeypatch, code, ausgabe)
    assert not pruefleiter.stufe_tests(None).gruen


def test_rot_hat_hoechstens_sechzig_zeilen_gruen_eine():
    rot = pruefleiter.Ergebnis("2 Typen", False, [f"z{i}" for i in range(500)])
    zeilen = pruefleiter.zusammenfassung([pruefleiter.Ergebnis("1 Lint", True), rot])
    assert len(zeilen) == pruefleiter.MAX_ROT_ZEILEN
    assert zeilen[0].startswith("Prüfleiter rot in Stufe 2 Typen")
    assert zeilen[-2] == "… und 443 weitere Zeilen"
    gruen = pruefleiter.Ergebnis("Tests", True, gesenkt=["pruef/rot-bekannt.txt"])
    assert len(pruefleiter.zusammenfassung([gruen])) == 1


def test_leiter_bricht_nach_der_ersten_roten_stufe_ab(tmp_path):
    aufgerufen = []

    def stufe(name, gruen):
        def lauf(log):
            aufgerufen.append(name)
            return pruefleiter.Ergebnis(name, gruen)

        return lauf

    stufen = [stufe("1", True), stufe("2", False), stufe("3", True)]
    with (tmp_path / "log").open("w") as log:
        ergebnisse = pruefleiter.fuehre_aus(stufen, log)
    assert aufgerufen == ["1", "2"]
    assert not ergebnisse[-1].gruen


def test_bekannt_roter_test_mit_teardown_fehler_bleibt_in_der_liste(
    tmp_path, monkeypatch
):
    pfad = _bekannt(tmp_path, monkeypatch, "tests/a.py::t1")
    _lauf_mit(
        monkeypatch,
        1,
        _KOPF + "PASSED tests/a.py::t1\nERROR tests/a.py::t1 - teardown\n",
    )
    assert pruefleiter.stufe_tests(None).gruen
    assert pfad.read_text(encoding="utf-8") == "tests/a.py::t1\n"


def test_ohne_liste_der_bekannt_roten_ist_jeder_rote_test_rot(tmp_path, monkeypatch):
    monkeypatch.setattr(pruefleiter, "ROT_BEKANNT", tmp_path / "fehlt.txt")
    _lauf_mit(monkeypatch, 1, _KOPF + "FAILED tests/a.py::t - x\n")
    assert not pruefleiter.stufe_tests(None).gruen
    _lauf_mit(monkeypatch, 0, _KOPF + "PASSED tests/a.py::t\n")
    assert pruefleiter.stufe_tests(None).gruen
    assert not (tmp_path / "fehlt.txt").exists()


@pytest.mark.parametrize(
    ("stufe", "code", "stdout", "erste_zeile"),
    [
        ("stufe_lint", 2, "", "ruff format bricht ab:"),
        ("stufe_lint", 1, "Would reformat: a.py\n", "ruff format: nicht formatiert"),
        ("stufe_typen", 2, "", "mypy bricht ab:"),
        ("stufe_typen", 1, "Found 1 error\n", "mypy bricht ab:"),
        ("stufe_schichten", 1, "Broken contracts\n----\nVertrag\n", "Vertrag"),
        ("stufe_schichten", 2, "", "kaputte Konfiguration"),
    ],
)
def test_abbruch_eines_werkzeugs_ist_rot(monkeypatch, stufe, code, stdout, erste_zeile):
    _lauf_mit(monkeypatch, code, stdout, "kaputte Konfiguration\n", gesammelt=None)
    ergebnis = getattr(pruefleiter, stufe)(None)
    assert not ergebnis.gruen
    assert ergebnis.zeilen[0] == erste_zeile


def test_ruff_check_abbruch_nach_formatpruefung_ist_rot(monkeypatch):
    def falscher_lauf(log, befehl):
        code = 0 if "format" in befehl else 2
        return subprocess.CompletedProcess(befehl, code, "", "kaputt\n")

    monkeypatch.setattr(pruefleiter, "_lauf", falscher_lauf)
    ergebnis = pruefleiter.stufe_lint(None)
    assert not ergebnis.gruen
    assert ergebnis.zeilen == ["ruff check bricht ab:", "kaputt"]


def test_mypy_zeile_ohne_nummer_ist_ein_befund_in_zeile_null():
    befunde = pruefleiter.mypy_befunde("mypy: error: Cannot find implementation\n")
    assert befunde == [Befund("mypy", 0, "ohne-code", "Cannot find implementation")]


def test_main_endet_rot_mit_log_und_zeiten(tmp_path, monkeypatch, capsys):
    def rot(log):
        return pruefleiter.Ergebnis("1 Lint", False, ["a.py:1 [F401] neu"])

    monkeypatch.setattr(pruefleiter, "STUFEN_VOLL", [rot])
    monkeypatch.setattr(pruefleiter, "LAUF_ORDNER", tmp_path)
    assert pruefleiter.main(["--voll"]) == 1
    assert "a.py:1 [F401] neu" in (tmp_path / "letzter-lauf.log").read_text("utf-8")
    assert (tmp_path / "zeiten.csv").read_text("utf-8").endswith(",1 Lint,0.0,rot\n")
    assert capsys.readouterr().out.startswith("Prüfleiter rot in Stufe 1 Lint")


def test_weniger_gesammelte_tests_als_die_untergrenze_sind_rot(
    tmp_path, monkeypatch, _untergrenze
):
    _bekannt(tmp_path, monkeypatch)
    _lauf_mit(monkeypatch, 0, _KOPF + "PASSED tests/a.py::t\n", gesammelt=1)
    ergebnis = pruefleiter.stufe_tests(None)
    assert not ergebnis.gruen
    assert ergebnis.zeilen[0].startswith("1 Tests gesammelt, erwartet mindestens 2")
    assert _untergrenze.read_text(encoding="utf-8") == "2\n"


def test_mehr_gesammelte_tests_heben_die_untergrenze(
    tmp_path, monkeypatch, _untergrenze
):
    _bekannt(tmp_path, monkeypatch)
    _lauf_mit(monkeypatch, 0, _KOPF + "PASSED tests/a.py::t\n", gesammelt=5)
    ergebnis = pruefleiter.stufe_tests(None)
    assert ergebnis.gruen
    assert ergebnis.angehoben == [str(_untergrenze)]
    assert _untergrenze.read_text(encoding="utf-8") == "5\n"
    assert "angehoben" in pruefleiter.zusammenfassung([ergebnis])[0]


def test_rote_stufe_hebt_die_untergrenze_nicht(tmp_path, monkeypatch, _untergrenze):
    _bekannt(tmp_path, monkeypatch)
    _lauf_mit(monkeypatch, 1, _KOPF + "FAILED tests/a.py::t - x\n", gesammelt=5)
    assert not pruefleiter.stufe_tests(None).gruen
    assert _untergrenze.read_text(encoding="utf-8") == "2\n"


def test_unlesbare_testzahl_ist_rot(tmp_path, monkeypatch):
    _bekannt(tmp_path, monkeypatch)
    _lauf_mit(monkeypatch, 0, _KOPF + "PASSED tests/a.py::t\n", gesammelt=None)
    ergebnis = pruefleiter.stufe_tests(None)
    assert not ergebnis.gruen
    assert ergebnis.zeilen == ["Zahl der gesammelten Tests nicht lesbar"]


@pytest.mark.parametrize(
    ("ausgabe", "anzahl"),
    [
        ("created: 1/1 worker\n1 worker [1 item]\n", 1),
        ("collected 3 items / 1 deselected / 2 selected\n", 2),
        ("collected 7 items\n", 7),
        ("bringing up nodes...\n", None),
    ],
)
def test_gesammelte_tests_aus_der_kopfzeile(ausgabe, anzahl):
    assert pruefleiter.gesammelte_tests(ausgabe) == anzahl


def test_werkzeuge_sehen_keine_steuernde_umgebung(tmp_path, monkeypatch):
    for name, wert in [
        ("PYTEST_ADDOPTS", "-k irgendwas"),
        ("PYTEST_PLUGINS", "fremd"),
        ("PYTEST_DISABLE_PLUGIN_AUTOLOAD", "1"),
        ("RUFF_OUTPUT_FORMAT", "concise"),
        ("MYPYPATH", "/fremd"),
        ("PYTHONPATH", "/fremd"),
        ("PY_COLORS", "1"),
    ]:
        monkeypatch.setenv(name, wert)
    monkeypatch.setenv("HOME_BLEIBT", "ja")
    befehl = [
        sys.executable,
        "-c",
        "import json, os; print(json.dumps(dict(os.environ)))",
    ]
    with (tmp_path / "log").open("w") as log:
        lauf = pruefleiter._lauf(log, befehl)
    gesehen = json.loads(lauf.stdout)
    assert not [n for n in gesehen if n.startswith(("PYTEST_", "RUFF_", "MYPY", "PY_"))]
    assert gesehen["PYTHONPATH"] == str(pruefleiter.WURZEL / "src")
    assert gesehen["HOME_BLEIBT"] == "ja"


def test_ueberschrittene_stufenfrist_bricht_den_lauf_rot_ab(tmp_path, monkeypatch):
    monkeypatch.setattr(pruefleiter, "STUFE_FRIST_SEKUNDEN", 1)
    befehl = [
        sys.executable,
        "-c",
        "import time; print('los', flush=True); time.sleep(60)",
    ]
    start = time.monotonic()
    with (tmp_path / "log").open("w") as log:
        lauf = pruefleiter._lauf(log, befehl)
    assert time.monotonic() - start < 30
    assert lauf.returncode not in (0, 1)
    assert lauf.stdout == "los\n"
    assert lauf.stderr.endswith("abgebrochen nach 1 s\n")


@pytest.fixture()
def kleines_projekt(tmp_path, monkeypatch):
    """Ein Projekt mit zwei grünen und einem roten Test; die Leiter läuft echt darin."""
    wurzel = tmp_path / "projekt"
    (wurzel / "tests").mkdir(parents=True)
    (wurzel / "pytest.ini").write_text("[pytest]\ntestpaths = tests\n", "utf-8")
    (wurzel / "tests" / "test_gruen.py").write_text(
        "def test_eins():\n    pass\n\n\ndef test_zwei():\n    pass\n", "utf-8"
    )
    (wurzel / "tests" / "test_rot.py").write_text(
        "def test_kaputt():\n    assert 1 == 2\n", "utf-8"
    )
    kanarie = Path(__file__).with_name("kanarie_leiter.py").read_text("utf-8")
    (wurzel / pruefleiter.KANARIE).write_text(kanarie, "utf-8")
    (wurzel / "tests" / "conftest.py").write_text(_HERMETIK, "utf-8")
    pruef = tmp_path / "pruef"
    pruef.mkdir()
    (pruef / "rot-bekannt.txt").write_text("", "utf-8")
    (pruef / "tests-anzahl.txt").write_text("7\n", "utf-8")
    (pruef / "tests-uebersprungen.txt").write_text("0\n", "utf-8")
    (pruef / "tests-mit-bestand.txt").write_text("", "utf-8")
    # tests/conftest.py liest die Altlasten aus <wurzel>/pruef wie die Leiter.
    (wurzel / "pruef").symlink_to(pruef)
    monkeypatch.setattr(pruefleiter, "WURZEL", wurzel)
    monkeypatch.setattr(pruefleiter, "ROT_BEKANNT", pruef / "rot-bekannt.txt")
    monkeypatch.setattr(pruefleiter, "TESTS_ANZAHL", pruef / "tests-anzahl.txt")
    monkeypatch.setattr(
        pruefleiter, "TESTS_UEBERSPRUNGEN", pruef / "tests-uebersprungen.txt"
    )
    monkeypatch.setattr(
        pruefleiter, "TESTS_MIT_BESTAND", pruef / "tests-mit-bestand.txt"
    )
    return wurzel


def test_testauswahl_ueber_die_umgebung_versteckt_keinen_roten_test(
    kleines_projekt, monkeypatch, tmp_path
):
    monkeypatch.setenv("PYTEST_ADDOPTS", "-k 'eins or zwei'")
    with (tmp_path / "log").open("w") as log:
        ergebnis = pruefleiter.stufe_tests(log)
    assert not ergebnis.gruen
    assert [z.split(" - ")[0] for z in ergebnis.zeilen] == [
        "FAILED tests/test_rot.py::test_kaputt"
    ]


def test_altlast_ohne_zugriff_wird_gestrichen():
    altlasten = pruefleiter.TESTS_MIT_BESTAND
    altlasten.write_text("tests/test_a.py\ntests/test_b.py\n", encoding="utf-8")
    assert pruefleiter.senke_altlasten({"tests/test_b.py", "tests/test_neu.py"})
    assert altlasten.read_text(encoding="utf-8") == "tests/test_b.py\n"
    assert not pruefleiter.senke_altlasten({"tests/test_b.py"})


def test_gruener_lauf_streicht_altlasten_und_ohne_eintrag_scheitert_der_zugriff(
    kleines_projekt, tmp_path
):
    (kleines_projekt / "data").mkdir()
    (kleines_projekt / "data" / "x.txt").write_text("x", "utf-8")
    (kleines_projekt / "tests" / "test_alt.py").write_text(
        "from pathlib import Path\n\n\ndef test_liest():\n"
        "    assert (Path(__file__).parents[1] / 'data/x.txt').read_text() == 'x'\n",
        "utf-8",
    )
    (kleines_projekt / "tests" / "test_rot.py").unlink()
    pruef = tmp_path / "pruef"
    altlasten = pruef / "tests-mit-bestand.txt"
    altlasten.write_text("tests/test_alt.py\ntests/test_gruen.py\n", "utf-8")
    with (tmp_path / "log").open("w") as log:
        ergebnis = pruefleiter.stufe_tests(log)
    assert ergebnis.gruen, ergebnis.zeilen
    assert str(altlasten) in ergebnis.gesenkt
    assert altlasten.read_text("utf-8") == "tests/test_alt.py\n"
    altlasten.write_text("", "utf-8")
    with (tmp_path / "log").open("w") as log:
        ergebnis = pruefleiter.stufe_tests(log)
    assert not ergebnis.gruen
    assert " tests/test_alt.py::test_liest - " in ergebnis.zeilen[0]
    assert "Regel hermetisch: Tests lesen nur Schnappschüsse" in ergebnis.zeilen[0]


def test_geloeschter_test_macht_die_teststufe_rot(kleines_projekt, tmp_path):
    (kleines_projekt / "tests" / "test_rot.py").unlink()
    (tmp_path / "pruef" / "tests-anzahl.txt").write_text("7\n", "utf-8")
    with (tmp_path / "log").open("w") as log:
        ergebnis = pruefleiter.stufe_tests(log)
    assert not ergebnis.gruen
    assert ergebnis.zeilen[0].startswith("6 Tests gesammelt, erwartet mindestens 7")
    # Gegenprobe: mit beiden grünen Tests als Untergrenze ist dieselbe Suite grün.
    (tmp_path / "pruef" / "tests-anzahl.txt").write_text("4\n", "utf-8")
    with (tmp_path / "log").open("a") as log:
        assert pruefleiter.stufe_tests(log).gruen


def test_haengender_test_wird_rot_statt_die_leiter_anzuhalten(
    kleines_projekt, monkeypatch, tmp_path
):
    (kleines_projekt / "tests" / "test_rot.py").write_text(
        "import time\n\n\ndef test_haengt():\n    time.sleep(60)\n", "utf-8"
    )
    monkeypatch.setattr(pruefleiter, "TEST_FRIST_SEKUNDEN", 2)
    start = time.monotonic()
    with (tmp_path / "log").open("w") as log:
        ergebnis = pruefleiter.stufe_tests(log)
    assert time.monotonic() - start < 50
    assert not ergebnis.gruen
    assert ergebnis.zeilen[0].startswith("FAILED tests/test_rot.py::test_haengt")


def _obergrenze():
    return pruefleiter.TESTS_UEBERSPRUNGEN.read_text(encoding="utf-8")


def test_mehr_uebersprungene_tests_als_die_obergrenze_sind_rot(tmp_path, monkeypatch):
    _bekannt(tmp_path, monkeypatch)
    _lauf_mit(monkeypatch, 0, _KOPF + "PASSED tests/a.py::t\n", uebersprungen=2)
    ergebnis = pruefleiter.stufe_tests(None)
    assert not ergebnis.gruen
    assert ergebnis.zeilen[0].startswith("2 Tests übersprungen oder xfail")
    assert _obergrenze() == "1\n"


def test_weniger_uebersprungene_tests_senken_die_obergrenze(tmp_path, monkeypatch):
    _bekannt(tmp_path, monkeypatch)
    _lauf_mit(monkeypatch, 0, _KOPF + "PASSED tests/a.py::t\n", uebersprungen=0)
    ergebnis = pruefleiter.stufe_tests(None)
    assert ergebnis.gruen
    assert ergebnis.gesenkt == [str(pruefleiter.TESTS_UEBERSPRUNGEN)]
    assert _obergrenze() == "0\n"


@pytest.mark.parametrize(
    ("ausgabe", "anzahl"),
    [
        (
            "== 20 failed, 4024 passed, 6 skipped, 11 warnings in 238.18s (0:03:58) ==",
            6,
        ),
        ("=== 1 passed, 2 skipped, 3 xfailed, 1 xpassed in 0.33s ===", 5),
        ("==== 3 passed in 0.12s ====", 0),
        ("3 passed, 9 skipped\n", None),
    ],
)
def test_nicht_ausgefuehrte_tests_aus_der_schlusszeile(ausgabe, anzahl):
    assert pruefleiter.nicht_ausgefuehrte_tests(ausgabe) == anzahl


def test_stufenfrist_beendet_auch_kindprozesse(tmp_path, monkeypatch):
    monkeypatch.setattr(pruefleiter, "STUFE_FRIST_SEKUNDEN", 1)
    pid_datei = tmp_path / "kind.pid"
    eltern = (
        "import subprocess, sys, time\n"
        "schlaf = 'import time; time.sleep(60)'\n"
        "kind = subprocess.Popen([sys.executable, '-c', schlaf])\n"
        f"open({str(pid_datei)!r}, 'w').write(str(kind.pid))\n"
        "time.sleep(60)\n"
    )
    start = time.monotonic()
    with (tmp_path / "log").open("w") as log:
        lauf = pruefleiter._lauf(log, [sys.executable, "-c", eltern])
    assert time.monotonic() - start < 30
    assert lauf.returncode not in (0, 1)
    kind = int(pid_datei.read_text())
    for _ in range(50):
        if _zustand(kind) in ("", "Z"):
            break
        time.sleep(0.1)
    else:
        pytest.fail(f"Kindprozess {kind} lebt nach dem Abbruch weiter")


def _zustand(pid):
    """Gibt den Prozesszustand aus ``ps`` zurück (Linux und macOS); leer: beendet."""
    lauf = subprocess.run(
        ["ps", "-o", "stat=", "-p", str(pid)], capture_output=True, text=True
    )
    assert lauf.returncode in (0, 1), lauf.stderr
    return lauf.stdout.strip()[:1]


def test_prozesszustand_erkennt_einen_lebenden_prozess():
    assert _zustand(os.getpid()) not in ("", "Z")


def test_uebersprungene_tests_aus_einer_conftest_machen_die_stufe_rot(
    kleines_projekt, tmp_path
):
    (kleines_projekt / "tests" / "test_rot.py").unlink()
    (tmp_path / "pruef" / "tests-anzahl.txt").write_text("2\n", "utf-8")
    (kleines_projekt / "tests" / "conftest.py").write_text(
        _HERMETIK + "import pytest\n\n\n"
        "def pytest_collection_modifyitems(items):\n"
        "    for item in items:\n"
        "        item.add_marker(pytest.mark.skip)\n",
        "utf-8",
    )
    with (tmp_path / "log").open("w") as log:
        ergebnis = pruefleiter.stufe_tests(log)
    assert not ergebnis.gruen
    assert ergebnis.zeilen[0].startswith("6 Tests übersprungen oder xfail")


_UMSCHREIBEN = (
    "import pytest\n\n\n"
    "@pytest.hookimpl(hookwrapper=True)\n"
    "def pytest_runtest_makereport(item, call):\n"
    "    ergebnis = yield\n"
    "    bericht = ergebnis.get_result()\n"
    "    if bericht.failed:\n"
    "        bericht.outcome = 'passed'\n"
)


def test_conftest_die_scheitern_zu_bestanden_umschreibt_macht_die_stufe_rot(
    kleines_projekt, tmp_path
):
    (kleines_projekt / "tests" / "conftest.py").write_text(
        _HERMETIK + _UMSCHREIBEN, "utf-8"
    )
    with (tmp_path / "log").open("w") as log:
        ergebnis = pruefleiter.stufe_tests(log)
    assert not ergebnis.gruen
    assert ergebnis.zeilen == [
        "tests/kanarie_leiter.py: Ergebnisse werden umgeschrieben oder abgewählt"
    ]
    # Gegenprobe: ohne den Hook ist der rote Test rot gemeldet, nicht der Kanarienvogel.
    (kleines_projekt / "tests" / "conftest.py").write_text(_HERMETIK, "utf-8")
    (kleines_projekt / "tests" / "test_rot.py").unlink()
    (tmp_path / "pruef" / "tests-anzahl.txt").write_text("4\n", "utf-8")
    with (tmp_path / "log").open("a") as log:
        assert pruefleiter.stufe_tests(log).gruen


def test_kanarienvogel_laeuft_nicht_im_direkten_pytest_aufruf(kleines_projekt):
    lauf = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider"],
        cwd=kleines_projekt,
        capture_output=True,
        text=True,
    )
    assert "3 items" in lauf.stdout or "1 failed, 2 passed" in lauf.stdout
    assert "kanarie" not in lauf.stdout


_UMSCHREIBEN_VERSTECKT = (
    "import pytest\n\n\n"
    "def _umschreiben(item, call):\n"
    "    ergebnis = yield\n"
    "    bericht = ergebnis.get_result()\n"
    "    if bericht.failed and 'kanarie' not in item.nodeid:\n"
    "        bericht.outcome = 'passed'\n\n\n"
    'globals()["pytest_runtest_" + "makereport"] = pytest.hookimpl(hookwrapper=True)(\n'
    "    _umschreiben\n"
    ")\n"
)


def test_versteckter_hook_der_den_kanarienvogel_auslaesst_macht_die_stufe_rot(
    kleines_projekt, tmp_path
):
    conftest = kleines_projekt / "tests" / "conftest.py"
    conftest.write_text(_HERMETIK + _UMSCHREIBEN_VERSTECKT, "utf-8")
    with (tmp_path / "log").open("w") as log:
        ergebnis = pruefleiter.stufe_tests(log)
    assert not ergebnis.gruen
    assert ergebnis.zeilen == [
        "Ergebnisse umgeschrieben:",
        "tests/test_rot.py::test_kaputt: als bestanden gemeldet,"
        " die Testfunktion scheiterte",
    ]
    assert "PASSED tests/test_rot.py::test_kaputt" in (tmp_path / "log").read_text()


def test_fehlende_rohaufzeichnung_ist_rot():
    kanarie = pruefleiter.KANARIE
    rot = {f"{kanarie}::test_muss_scheitern": "FAILED"}
    gruen = {f"{kanarie}::test_muss_bestehen", "tests/a.py::t"}
    assert pruefleiter.leiter_pytest.pruefe_ergebnisse(rot, gruen, {}, kanarie) == [
        "Rohaufzeichnung fehlt: Plugin leiter_roh lief nicht"
    ]


def test_ausgelassene_testfunktion_ist_umgeschrieben(kleines_projekt, tmp_path):
    (kleines_projekt / "tests" / "conftest.py").write_text(
        _HERMETIK + "import pytest\n\n\n"
        "@pytest.hookimpl(tryfirst=True)\n"
        "def pytest_pyfunc_call(pyfuncitem):\n"
        "    return 'kanarie' not in pyfuncitem.nodeid or None\n",
        "utf-8",
    )
    with (tmp_path / "log").open("w") as log:
        ergebnis = pruefleiter.stufe_tests(log)
    assert (
        "tests/test_rot.py::test_kaputt: als bestanden gemeldet, die Testfunktion"
        " lief nie" in ergebnis.zeilen
    )


def test_ehrlicher_lauf_mit_xdist_zeichnet_jeden_test_roh_auf(
    kleines_projekt, tmp_path
):
    (kleines_projekt / "tests" / "test_rot.py").unlink()
    (tmp_path / "pruef" / "tests-anzahl.txt").write_text("4\n", "utf-8")
    with (tmp_path / "log").open("w") as log:
        ergebnis = pruefleiter.stufe_tests(log)
    assert ergebnis.gruen, ergebnis.zeilen
    assert (
        "4 workers" in (tmp_path / "log").read_text()
        or "created:" in (tmp_path / "log").read_text()
    )


_ABWAHL = {
    "addopts_deselect": (
        "pytest.ini",
        "[pytest]\ntestpaths = tests\n"
        "addopts = --deselect tests/test_rot.py::test_kaputt\n",
    ),
    "addopts_k": (
        "pytest.ini",
        "[pytest]\ntestpaths = tests\naddopts = -k 'not kaputt'\n",
    ),
    "conftest_entfernt": (
        "tests/conftest.py",
        _HERMETIK + "\n\ndef pytest_collection_modifyitems(items):\n"
        "    items[:] = [i for i in items if 'kaputt' not in i.nodeid]\n",
    ),
}


@pytest.mark.parametrize("art", sorted(_ABWAHL))
def test_abgewaehlter_roter_test_macht_die_teststufe_rot(
    kleines_projekt, tmp_path, art
):
    pfad, text = _ABWAHL[art]
    (kleines_projekt / pfad).write_text(text, "utf-8")
    (tmp_path / "pruef" / "tests-anzahl.txt").write_text("4\n", "utf-8")
    with (tmp_path / "log").open("w") as log:
        ergebnis = pruefleiter.stufe_tests(log)
    assert not ergebnis.gruen
    assert ergebnis.zeilen == [
        "tests/test_rot.py::test_kaputt: steht im Repo, lief aber nicht (abgewählt)"
    ]
    # Gegenprobe: ohne den roten Test ist dieselbe Auswahl grün.
    (kleines_projekt / "tests" / "test_rot.py").unlink()
    with (tmp_path / "log").open("a") as log:
        assert pruefleiter.stufe_tests(log).gruen


def test_vorgetaeuschter_ablaufbeginn_versteckt_keinen_abgewaehlten_test(
    kleines_projekt, tmp_path
):
    (kleines_projekt / "tests" / "conftest.py").write_text(
        _HERMETIK + "\n\ndef pytest_collection_modifyitems(config, items):\n"
        "    for i in [i for i in items if 'kaputt' in i.nodeid]:\n"
        "        config.hook.pytest_runtest_logstart(\n"
        "            nodeid=i.nodeid, location=i.location\n"
        "        )\n"
        "    items[:] = [i for i in items if 'kaputt' not in i.nodeid]\n",
        "utf-8",
    )
    (kleines_projekt / "tests" / "test_fueller.py").write_text(
        "def test_fueller():\n    pass\n", "utf-8"
    )
    with (tmp_path / "log").open("w") as log:
        ergebnis = pruefleiter.stufe_tests(log)
    assert not ergebnis.gruen
    assert ergebnis.zeilen == [
        "1 Tests begannen ohne Lauf und ohne rotes Ergebnis, übersprungen oder xfail"
        " sind nur 0:",
        "tests/test_rot.py::test_kaputt",
    ]


def test_rohe_sammlung_die_scheitert_ist_rot(kleines_projekt, tmp_path):
    (kleines_projekt / "tests" / "test_rot.py").unlink()
    (kleines_projekt / "tests" / "conftest.py").write_text(
        _HERMETIK + "\n\ndef pytest_ignore_collect(collection_path, config):\n"
        "    return collection_path.name == 'test_kaputt_import.py' or None\n",
        "utf-8",
    )
    (kleines_projekt / "tests" / "test_kaputt_import.py").write_text(
        "def test_x(:\n", "utf-8"
    )
    (tmp_path / "pruef" / "tests-anzahl.txt").write_text("4\n", "utf-8")
    with (tmp_path / "log").open("w") as log:
        ergebnis = pruefleiter.stufe_tests(log)
    assert not ergebnis.gruen
    assert any(
        z.startswith("rohe Sammlung ohne Projekteinstellungen und conftest endet mit")
        for z in ergebnis.zeilen
    ), ergebnis.zeilen


def test_parameter_aus_einer_conftest_sind_keine_abwahl():
    abgewaehlt = pruefleiter.leiter_pytest.abgewaehlt
    roh = {"t.py::a", "t.py::b[1]"}
    assert abgewaehlt(roh, {"t.py::a[x]", "t.py::b[1-x]"}) == []
    assert abgewaehlt(roh, {"t.py::a[x]", "t.py::b[11-x]"}) == [
        "t.py::b[1]: steht im Repo, lief aber nicht (abgewählt)"
    ]
    assert abgewaehlt(roh, {"t.py::b[1]"}) == [
        "t.py::a: steht im Repo, lief aber nicht (abgewählt)"
    ]


def test_bindestrich_in_der_testid_ist_kein_umgeschriebener_fehler():
    test = "tests/a.py::t[Pro Max (256 GB) - Händler]"
    assert pruefleiter.leiter_pytest.umgeschrieben({test}, {test: "ok"}) == []
    zeile = "tests/a.py::t - assert 1 == 2"
    assert pruefleiter.leiter_pytest.umgeschrieben(
        {zeile}, {"tests/a.py::t": "fehler"}
    ) == ["tests/a.py::t: als bestanden gemeldet, die Testfunktion scheiterte"]


_EINHUELLEN = {
    "verschluckt": (
        "def pytest_collection_modifyitems(items):\n"
        "    for item in [i for i in items if 'kanarie' not in i.nodeid]:\n"
        "        echt = item.obj\n\n"
        "        def huelle(*a, _echt=echt, **k):\n"
        "            try:\n"
        "                _echt(*a, **k)\n"
        "            except Exception:\n"
        "                pass\n\n"
        "        item.obj = huelle\n"
    ),
    "mit_wraps": (
        "import functools\n\n\n"
        "def pytest_collection_modifyitems(items):\n"
        "    for item in [i for i in items if 'kanarie' not in i.nodeid]:\n"
        "        echt = item.obj\n\n"
        "        @functools.wraps(echt)\n"
        "        def huelle(*a, _echt=echt, **k):\n"
        "            try:\n"
        "                _echt(*a, **k)\n"
        "            except Exception:\n"
        "                pass\n\n"
        "        item.obj = huelle\n"
    ),
    "im_modul": (
        "def pytest_collection_modifyitems(items):\n"
        "    for item in [i for i in items if 'kanarie' not in i.nodeid]:\n"
        "        echt = getattr(item.module, item.originalname)\n\n"
        "        def huelle(*a, _echt=echt, **k):\n"
        "            try:\n"
        "                _echt(*a, **k)\n"
        "            except Exception:\n"
        "                pass\n\n"
        "        huelle.__name__ = huelle.__qualname__ = item.originalname\n"
        "        huelle.__module__ = item.module.__name__\n"
        "        setattr(item.module, item.originalname, huelle)\n"
        "        item.obj = huelle\n"
    ),
}


@pytest.mark.parametrize("art", sorted(_EINHUELLEN))
def test_vorab_eingehuellter_roter_test_bleibt_rot_und_rot_bekannt_schrumpft_nicht(
    kleines_projekt, tmp_path, art
):
    """Gegen 6ceb9cd grün: die Hülle lag innerhalb der Aufzeichnung."""
    rot_bekannt = tmp_path / "pruef" / "rot-bekannt.txt"
    rot_bekannt.write_text("tests/test_rot.py::test_kaputt\n", "utf-8")
    conftest = kleines_projekt / "tests" / "conftest.py"
    conftest.write_text(_HERMETIK + _EINHUELLEN[art], "utf-8")
    with (tmp_path / "log").open("w") as log:
        ergebnis = pruefleiter.stufe_tests(log)
    assert not ergebnis.gruen
    assert (
        "tests/test_rot.py::test_kaputt: Testfunktion vor der Leiter umhüllt"
        " oder ersetzt" in ergebnis.zeilen
    )
    assert rot_bekannt.read_text("utf-8") == "tests/test_rot.py::test_kaputt\n"
    # Gegenprobe: ehrlich repariert, schrumpft rot-bekannt um genau diesen Test.
    conftest.write_text(_HERMETIK, "utf-8")
    (kleines_projekt / "tests" / "test_rot.py").write_text(
        "def test_kaputt():\n    assert 1 == 1  # repariert\n", "utf-8"
    )
    with (tmp_path / "log").open("a") as log:
        ergebnis = pruefleiter.stufe_tests(log)
    assert ergebnis.gruen, ergebnis.zeilen
    assert rot_bekannt.read_text("utf-8") == ""


def test_hülle_aus_einer_autouse_fixture_ersetzt_die_aufzeichnung_und_ist_rot(
    kleines_projekt, tmp_path
):
    (kleines_projekt / "tests" / "conftest.py").write_text(
        _HERMETIK + "import pytest\n\n\n"
        "@pytest.fixture(autouse=True)\n"
        "def huelle(request):\n"
        "    echt = getattr(request.module, request.node.originalname)\n\n"
        "    def schluckt(*a, **k):\n"
        "        try:\n"
        "            echt(*a, **k)\n"
        "        except Exception:\n"
        "            pass\n\n"
        "    if 'kanarie' not in request.node.nodeid:\n"
        "        request.node.obj = schluckt\n",
        "utf-8",
    )
    with (tmp_path / "log").open("w") as log:
        ergebnis = pruefleiter.stufe_tests(log)
    assert not ergebnis.gruen
    assert (
        "tests/test_rot.py::test_kaputt: als bestanden gemeldet, die Testfunktion"
        " lief nie" in ergebnis.zeilen
    )


def test_dekorierte_und_parametrisierte_tests_sind_echt(kleines_projekt, tmp_path):
    (kleines_projekt / "tests" / "test_rot.py").write_text(
        "import pytest\n\n\n"
        "@pytest.mark.parametrize('n', [1, 2])\n"
        "@pytest.mark.filterwarnings('ignore')\n"
        "def test_kaputt(n):\n    assert n\n\n\n"
        "class TestGruppe:\n"
        "    def test_methode(self):\n        assert True\n",
        "utf-8",
    )
    with (tmp_path / "log").open("w") as log:
        ergebnis = pruefleiter.stufe_tests(log)
    assert ergebnis.gruen, ergebnis.zeilen


_FALSCHES_PLUGIN = (
    "import os\n\nimport pytest\n\n\n"
    "@pytest.hookimpl(hookwrapper=True)\n"
    "def pytest_runtest_makereport(item, call):\n"
    "    ergebnis = yield\n"
    "    bericht = ergebnis.get_result()\n"
    "    ordner = os.environ['TELCO_LEITER_ROH']\n"
    "    art = 'fehler' if 'muss_scheitern' in item.nodeid else 'ok'\n"
    "    with open(os.path.join(ordner, f'{os.getpid()}.txt'), 'a') as datei:\n"
    "        datei.write(f'{art} {item.nodeid}\\n')\n"
    "    if bericht.failed and 'kanarie' not in item.nodeid:\n"
    "        bericht.outcome = 'passed'\n"
)


def test_gleichnamiges_modul_unter_src_verdeckt_das_leiterplugin_nicht(
    kleines_projekt, tmp_path
):
    """Gegen 6ceb9cd grün: src/ stand vor dem Plugin auf dem Suchpfad."""
    (kleines_projekt / "src").mkdir()
    (kleines_projekt / "src" / "leiter_roh.py").write_text(_FALSCHES_PLUGIN, "utf-8")
    with (tmp_path / "log").open("w") as log:
        ergebnis = pruefleiter.stufe_tests(log)
    assert not ergebnis.gruen
    assert [z.split(" - ")[0] for z in ergebnis.zeilen] == [
        "FAILED tests/test_rot.py::test_kaputt"
    ]
