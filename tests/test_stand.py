import contextlib
import importlib.util
import os
import subprocess
import sys
from datetime import UTC, date, datetime
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
    (tmp_path / "pruef/tests-basis.txt").write_text(
        "tests/test_a.py uhr 2\ntests/test_b.py uhr 1\n"
        "tests/test_a.py chromium-eigenes 1\n",
        "utf-8",
    )
    (tmp_path / "pruef/tests-mit-bestand.txt").write_text("tests/test_a.py\n", "utf-8")
    (tmp_path / ".importlinter").write_text(_VERTRAEGE, "utf-8")
    monkeypatch.setattr(stand, "W", tmp_path)
    monkeypatch.setattr(stand, "rot_proben", lambda: ["Rot-Proben gemessen"])
    monkeypatch.setattr(stand, "zeitreihen_probe", lambda: ["Zeitreihe gemessen"])
    monkeypatch.setattr(stand, "live_datum", lambda: [])
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
        "src/telco_radar/pipeline.py fehlt",
        "breite except 40, Ziel 39",
    ]
    assert "src/telco_radar/report/html.py fehlt" in offen["9 Lader, render_site"]


def test_hermetische_tests_nennen_altlasten_umgehungen_und_laufzeit(projekt):
    assert stand.offen()["4 Hermetische Tests"] == [
        "Testdateien mit Bestand 1, Ziel 0",
        "chromium-eigenes in Tests 1, Ziel 0",
        "uhr in Tests 3, Ziel 0",
        "keine Teststufe in .pruefleiter/zeiten.csv",
        "tests/fixtures/bestand fehlt",
    ]
    (projekt / ".pruefleiter").mkdir()
    (projekt / ".pruefleiter/zeiten.csv").write_text(
        "t1,Tests,250.4,gruen\nt2,1 Lint,3.0,gruen\nt3,Tests,239.6,gruen\n", "utf-8"
    )
    (projekt / "tests/fixtures/bestand").mkdir(parents=True)
    (projekt / "pruef/tests-mit-bestand.txt").write_text("", "utf-8")
    (projekt / "pruef/tests-basis.txt").write_text("", "utf-8")
    assert stand.offen()["4 Hermetische Tests"] == []
    (projekt / ".pruefleiter/zeiten.csv").write_text("t1,Tests,240.6,rot\n", "utf-8")
    assert stand.offen()["4 Hermetische Tests"] == [
        "Sekunden der letzten Teststufe 241, Ziel 240"
    ]


def test_uhr_in_der_einstiegsdatei_ausserhalb_der_funktion_zaehlt_mit(projekt):
    pipeline = projekt / "src/telco_radar/pipeline.py"
    pipeline.parent.mkdir(parents=True)
    pipeline.write_text("def run():\n    pass\n\n\nx = date.today()\n", "utf-8")
    assert "Uhraufrufe 4, Ziel 0" in stand.offen()["10 run, Uhr, Fehler, Netzweg"]


def test_schritt_zwei_und_drei_messen_ihr_plankriterium_statt_eines_logs(projekt):
    (projekt / ".pruefleiter").mkdir()
    log = projekt / ".pruefleiter/letzter-lauf.log"
    log.write_text("Prüfleiter grün (0 Wächter 0 s, 1 Lint 0 s)\n", "utf-8")
    offen = stand.offen()
    assert offen["3 Format, Werkzeuge, Basen"] == ["Rot-Proben gemessen"]
    assert offen["2 Workflows, Python"] == ["Zeitreihe gemessen"]


class _Abruf:
    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode, self.stdout, self.stderr = returncode, stdout, stderr


def _baum(monkeypatch, tmp_path, *laeufe):
    @contextlib.contextmanager
    def wegwerf():
        yield tmp_path

    antworten = iter(laeufe)
    monkeypatch.setattr(stand, "_wegwerf_baum", wegwerf)
    monkeypatch.setattr(stand, "_python", lambda baum, *a: next(antworten))


@pytest.mark.parametrize(
    ("heute", "seite", "erfuellt"),
    [
        (date(2026, 10, 2), "2026-10-02", True),
        (date(2026, 10, 2), "2026-10-01", True),
        (date(2026, 10, 2), "2026-09-30", False),
        (date(2026, 10, 2), "2026-10-03", False),
        (date(2026, 3, 1), "2026-02-28", True),
        (date(2026, 1, 1), "2025-12-31", True),
    ],
)
def test_live_datum_verlangt_heute_oder_gestern(monkeypatch, heute, seite, erfuellt):
    antwort = _Abruf(0, f"<p>Stand {seite}</p>")
    monkeypatch.setattr(stand.subprocess, "run", lambda *a, **k: antwort)
    assert (stand.live_datum(heute) == []) is erfuellt


def _uhr(jetzt):
    class Uhr(datetime):
        @classmethod
        def now(cls, tz=None):
            return jetzt.astimezone(tz)

    return Uhr


def test_live_datum_ohne_bezugstag_nimmt_den_tag_in_utc(monkeypatch):
    antwort = _Abruf(0, "<p>Stand 2026-10-01</p>")
    monkeypatch.setattr(stand.subprocess, "run", lambda *a, **k: antwort)
    monkeypatch.setattr(stand, "datetime", _uhr(datetime(2026, 10, 2, 23, tzinfo=UTC)))
    assert stand.live_datum() == []
    monkeypatch.setattr(stand, "datetime", _uhr(datetime(2026, 10, 4, 1, tzinfo=UTC)))
    assert stand.live_datum() == ["Live-Seite trägt weder 2026-10-04 noch 2026-10-03"]


def test_unlesbare_live_seite_ist_offen(monkeypatch):
    fehler = _Abruf(56, "", "curl: (56) 403")
    monkeypatch.setattr(stand.subprocess, "run", lambda *a, **k: fehler)
    assert stand.live_datum() == ["Live-Seite nicht lesbar (curl: (56) 403)"]


@pytest.mark.parametrize(
    ("ausgabe", "erwartet"),
    [
        ("EXIT 1 AUSFALL True\n", []),
        ("EXIT 0 AUSFALL True\n", ["kaputte Zeitreihe endet nicht rot"]),
        ("EXIT 1 AUSFALL False\n", ["Seite nennt den Ausfall nicht"]),
        ("", ["kaputte Zeitreihe endet nicht rot"]),
    ],
)
def test_zeitreihen_probe_liest_exit_und_seite(
    monkeypatch, tmp_path, ausgabe, erwartet
):
    _baum(monkeypatch, tmp_path, _Abruf(0, ausgabe))
    assert stand.zeitreihen_probe() == erwartet


def test_rot_proben_brauchen_gruene_gegenprobe_und_rot_in_der_richtigen_stufe(
    monkeypatch, tmp_path
):
    for ordner in ("src/telco_radar/report", "scripts"):
        (tmp_path / ordner).mkdir(parents=True)
    _baum(monkeypatch, tmp_path, _Abruf(1))
    assert stand.rot_proben() == ["Leiter Stufen 0–3 auf HEAD nicht grün"]
    erwartungen = [e for *_, e in stand.ROT_PROBEN.values()]
    rot = [_Abruf(1, f"Prüfleiter rot in {e[0]}\n" + " ".join(e)) for e in erwartungen]
    _baum(monkeypatch, tmp_path, _Abruf(0), *rot)
    assert stand.rot_proben() == []
    falsch = [_Abruf(1, "Prüfleiter rot in Stufe 0 Wächter\n")] * len(rot)
    _baum(monkeypatch, tmp_path, _Abruf(0), *falsch)
    assert len(stand.rot_proben()) == len(rot)
    assert list(tmp_path.rglob("rotprobe.py")) == []


def test_zeilen_einer_funktion_aus_dem_syntaxbaum(projekt):
    (projekt / "m.py").write_text("x = 1\n\n\ndef f():\n    a = 1\n    return a\n")
    assert stand._zeilen("m.py", "f") == 3
    assert stand._zeilen("m.py") == 6
    assert stand._zeilen("fehlt.py") == 0


@pytest.mark.parametrize("name", list(stand.ROT_PROBEN))
def test_rot_probe_scheitert_nur_an_ihrer_regel_nicht_an_der_formatierung(name):
    _, text, _ = stand.ROT_PROBEN[name]
    ruff = Path(sys.executable).parent / "ruff"
    lauf = subprocess.run(
        [ruff, "format", "--check", "-"], input=text, capture_output=True, text=True
    )
    assert lauf.returncode == 0, lauf.stdout


_UHR_2030 = """import datetime as d


class Uhr(d.datetime):
    @classmethod
    def now(cls, tz=None):
        return d.datetime(2030, 1, 1, 12, tzinfo=tz)


def pytest_collection_finish(session):
    for item in session.items:
        item.module.stand.datetime = Uhr
"""


def test_live_datum_test_haengt_nicht_an_der_uhr(tmp_path):
    """Gegen 6ceb9cd rot: der Test rechnete sein Erwartungsdatum aus der Wanduhr."""
    (tmp_path / "uhr_2030.py").write_text(_UHR_2030, "utf-8")
    befehl = [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider"]
    befehl += ["-p", "uhr_2030", __file__, "-k", "live_datum_verlangt"]
    umgebung = {**os.environ, "PYTHONPATH": str(tmp_path)}
    lauf = subprocess.run(befehl, capture_output=True, text=True, env=umgebung)
    assert lauf.returncode == 0, lauf.stdout[-2000:]
    assert "6 passed" in lauf.stdout
