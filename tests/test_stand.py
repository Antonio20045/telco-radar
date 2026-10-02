import importlib.util
import sys
from pathlib import Path

import pytest

_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(_SCRIPTS))
_spec = importlib.util.spec_from_file_location("stand", _SCRIPTS / "stand.py")
stand = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(stand)

_VERTRAEGE = """[importlinter:contract:report-rechnet-nur]
name = Report rechnet nur
ignore_imports =
    telco_radar.report.a -> telco_radar.collect.a
    telco_radar.report.b -> telco_radar.collect.b
    telco_radar.report.c -> telco_radar.collect.c
    telco_radar.report.d -> telco_radar.collect.d

[importlinter:contract:wurzel-unten]
name = Wurzel
type = forbidden
"""


class _Lauf:
    def __init__(self, stdout):
        self.stdout = stdout


@pytest.fixture()
def projekt(tmp_path, monkeypatch):
    """Ein Projekt mit vier Ausnahmen in report-rechnet-nur und origin nur mit main."""
    (tmp_path / "pruef").mkdir()
    (tmp_path / "pruef/waechter-basis.txt").write_text(
        "src/a.py uhr 2\nsrc/b.py uhr 1\nsrc/a.py breite-ausnahme 40\n", "utf-8"
    )
    (tmp_path / ".importlinter").write_text(_VERTRAEGE, "utf-8")
    monkeypatch.setattr(stand, "W", tmp_path)
    _origin(monkeypatch, "main")
    return tmp_path


def _origin(monkeypatch, *zweige):
    koepfe = "".join(f"abc\trefs/heads/{z}\n" for z in zweige)
    monkeypatch.setattr(stand.subprocess, "run", lambda *a, **k: _Lauf(koepfe))


def test_stand_nennt_alle_zehn_schritte_in_reihenfolge(projekt):
    schritte = list(stand.offen())
    assert [s.split(" ", 1)[0] for s in schritte] == [str(n) for n in range(1, 11)]


def test_aufraeumen_zaehlt_zweige_und_ist_ohne_origin_nie_erfuellt(
    projekt, monkeypatch
):
    assert stand.offen()["1 Aufräumen"] == []
    _origin(monkeypatch, "main", "claude/a", "claude/b")
    assert stand.offen()["1 Aufräumen"] == ["Zweige neben main 2, Ziel 0"]
    _origin(monkeypatch)
    assert "origin nicht lesbar" in stand.offen()["1 Aufräumen"]


def test_gruende_nennen_die_gemessenen_zahlen(projekt):
    offen = stand.offen()
    assert "report-rechnet-nur 4, Ziel 3" in offen["9 Lader, render_site"]
    assert offen["10 run, Uhr, Fehler, Netzweg"] == [
        "Uhraufrufe 3, Ziel 0",
        "breite except 40, Ziel 39",
    ]


def test_schritt_drei_braucht_einen_gruenen_volllauf_ab_stufe_null(projekt):
    assert stand.offen()["3 Format, Werkzeuge, Basen"] == [
        "letzter Volllauf nicht grün"
    ]
    (projekt / ".pruefleiter").mkdir()
    log = projekt / ".pruefleiter/letzter-lauf.log"
    log.write_text("Prüfleiter grün (1 Lint 0 s, Tests 2 s)\n", "utf-8")
    assert stand.offen()["3 Format, Werkzeuge, Basen"] != []
    log.write_text("Prüfleiter grün (0 Wächter 0 s, 1 Lint 0 s)\n", "utf-8")
    assert stand.offen()["3 Format, Werkzeuge, Basen"] == []


def test_zeilen_einer_funktion_aus_dem_syntaxbaum(projekt):
    (projekt / "m.py").write_text("x = 1\n\n\ndef f():\n    a = 1\n    return a\n")
    assert stand._zeilen("m.py", "f") == 3
    assert stand._zeilen("m.py") == 6
    assert stand._zeilen("fehlt.py") == 0
