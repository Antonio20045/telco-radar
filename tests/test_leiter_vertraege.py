import importlib.util
import io
import subprocess
import sys
from pathlib import Path

import pytest

_PFAD = Path(__file__).resolve().parents[1] / "scripts" / "pruefleiter.py"
sys.path.insert(0, str(_PFAD.parent))
_spec = importlib.util.spec_from_file_location("pruefleiter", _PFAD)
pruefleiter = importlib.util.module_from_spec(_spec)
sys.modules["pruefleiter"] = pruefleiter
_spec.loader.exec_module(pruefleiter)
leiter_vertraege = importlib.import_module("leiter_vertraege")
waechter = sys.modules["waechter"]

_GEHALTEN = "    mini.a.x -> mini.b\n"
_VERWAIST = "    mini.a.weg -> mini.b\n"
_VERTRAEGE = """[importlinter]
root_packages =
    mini

[importlinter:contract:eins]
name = A kennt B nicht
type = forbidden
source_modules =
    mini.a
forbidden_modules =
    mini.b
ignore_imports =
{ausnahmen}
[importlinter:contract:zwei]
name = B kennt A nicht
type = forbidden
source_modules =
    mini.b
forbidden_modules =
    mini.a
ignore_imports =
    mini.b.alt -> mini.a
"""


def _git(wurzel, *argumente):
    return subprocess.run(
        ["git", *argumente], cwd=wurzel, check=True, capture_output=True, text=True
    ).stdout.strip()


def _schreibe(wurzel, pfad, text):
    datei = wurzel / pfad
    datei.parent.mkdir(parents=True, exist_ok=True)
    datei.write_text(text, encoding="utf-8")


def _vertraege(ausnahmen):
    return _VERTRAEGE.format(ausnahmen=ausnahmen)


@pytest.fixture()
def mini(tmp_path, monkeypatch):
    """Ein Mini-Paket, in dem ``mini.a.x`` ``mini.b`` importiert, als Git-Repo."""
    for modul in ("mini", "mini/a", "mini/b"):
        _schreibe(tmp_path, f"src/{modul}/__init__.py", "")
    _schreibe(tmp_path, "src/mini/a/x.py", "import mini.b\n")
    _schreibe(tmp_path, ".importlinter", _vertraege(_GEHALTEN + _VERWAIST))
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "t@example.org")
    _git(tmp_path, "config", "user.name", "T")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-q", "-m", "anker")
    anker = _git(tmp_path, "rev-parse", "HEAD")
    _schreibe(tmp_path, waechter.WAECHTER, f'ANKER = "{anker}"\n')
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-q", "-m", "anker gesetzt")
    monkeypatch.setattr(pruefleiter, "WURZEL", tmp_path)
    return tmp_path


def test_stufe_drei_streicht_genau_die_verwaisten_ausnahmen_und_ist_gruen(mini):
    ergebnis = pruefleiter.stufe_schichten(io.StringIO())

    assert ergebnis.gruen, ergebnis.zeilen
    assert ergebnis.gesenkt == [".importlinter"]
    assert ergebnis.hinweise == [
        "verwaiste Ausnahme gestrichen: mini.a.weg -> mini.b",
        "verwaiste Ausnahme gestrichen: mini.b.alt -> mini.a",
    ]
    erwartet = _vertraege(_GEHALTEN).replace("    mini.b.alt -> mini.a\n", "")
    assert (mini / ".importlinter").read_text(encoding="utf-8") == erwartet
    assert waechter.lockerungen(mini) == []


def test_ohne_verwaiste_ausnahme_bleibt_die_datei_unberuehrt(mini):
    pruefleiter.stufe_schichten(io.StringIO())
    vorher = (mini / ".importlinter").read_text(encoding="utf-8")

    ergebnis = pruefleiter.stufe_schichten(io.StringIO())

    assert ergebnis.gruen, ergebnis.zeilen
    assert ergebnis.gesenkt == []
    assert (mini / ".importlinter").read_text(encoding="utf-8") == vorher


def test_gebrochener_vertrag_bleibt_rot_nach_dem_streichen(mini):
    _schreibe(mini, "src/mini/a/y.py", "import mini.b\n")

    ergebnis = pruefleiter.stufe_schichten(io.StringIO())

    assert not ergebnis.gruen
    assert ergebnis.gesenkt == [".importlinter"]
    assert any("mini.a.y -> mini.b" in z for z in ergebnis.zeilen)


def test_hinzugefuegte_ausnahme_ist_in_stufe_null_weiter_rot(mini):
    pruefleiter.stufe_schichten(io.StringIO())
    _schreibe(
        mini,
        ".importlinter",
        _vertraege(_GEHALTEN + "    mini.a.neu -> mini.b\n"),
    )

    rot = waechter.lockerungen(mini)

    assert rot == [
        ".importlinter lockerer (Arbeitsstand): importlinter:contract:eins:"
        " neue Ausnahme mini.a.neu -> mini.b"
    ]


def test_streichen_beruehrt_nur_zeilen_unter_ignore_imports():
    text = (
        "[importlinter:contract:eins]\nsource_modules =\n    mini.a -> mini.b\n"
        "ignore_imports =\n    mini.a  ->  mini.b\n    mini.c -> mini.b\n"
    )

    neu = leiter_vertraege.streiche(text, ["mini.a -> mini.b"])

    assert neu == (
        "[importlinter:contract:eins]\nsource_modules =\n    mini.a -> mini.b\n"
        "ignore_imports =\n    mini.c -> mini.b\n"
    )


def test_meldung_von_lint_imports_wird_zur_ausnahme():
    ausgabe = (
        "No matches for ignored import mini.a.z -> mini.b.\n"
        "No matches for ignored import mini.*.y -> mini.b.c.\n"
    )

    assert leiter_vertraege.verwaiste_ausnahmen(ausgabe) == [
        "mini.a.z -> mini.b",
        "mini.*.y -> mini.b.c",
    ]
