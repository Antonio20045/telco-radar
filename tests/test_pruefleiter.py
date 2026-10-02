import importlib.util
import json
import subprocess
import sys
from collections import Counter
from pathlib import Path

import pytest

_PFAD = Path(__file__).resolve().parents[1] / "scripts" / "pruefleiter.py"
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


_KOPF = "==== short test summary info ====\n"


def _lauf_mit(monkeypatch, returncode, stdout, stderr=""):
    def falscher_lauf(log, befehl):
        return subprocess.CompletedProcess(befehl, returncode, stdout, stderr)

    monkeypatch.setattr(pruefleiter, "_lauf", falscher_lauf)


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
    _lauf_mit(monkeypatch, code, stdout, "kaputte Konfiguration\n")
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
