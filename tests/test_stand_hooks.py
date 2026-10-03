import contextlib
import importlib.util
import sys
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(_SCRIPTS))
_spec = importlib.util.spec_from_file_location("stand_hooks", _SCRIPTS / "stand.py")
stand = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(stand)


def _zeiten(wurzel, *sekunden):
    (wurzel / ".pruefleiter").mkdir()
    zeilen = [f"2026-10-03T10:00:00Z,--pre-commit,{s},gruen\n" for s in sekunden]
    zeilen += ["2026-10-03T10:00:00Z,--pre-commit,0.1,rot\n"] * 9
    zeilen += ["2026-10-03T10:00:00Z,--schnell,0.1,gruen\n"] * 9
    zeilen.insert(1, "2026-10-03T10:00:00Z,0 Wächter,99.0,gruen\n")
    (wurzel / ".pruefleiter/zeiten.csv").write_text("".join(zeilen), "utf-8")


def test_median_der_schnellen_laeufe_unter_dem_ziel_ist_erfuellt(tmp_path, monkeypatch):
    monkeypatch.setattr(stand, "W", tmp_path)
    _zeiten(tmp_path, 2.0, 30.0, 4.9)
    assert stand._vorcommit_median() == []


def test_median_ab_fuenf_sekunden_ist_offen(tmp_path, monkeypatch):
    monkeypatch.setattr(stand, "W", tmp_path)
    _zeiten(tmp_path, 5.0, 6.0, 1.0)
    assert stand._vorcommit_median() == ["pre-commit im Median 5.0 s, Ziel unter 5 s"]


def test_ohne_schnellen_lauf_ist_der_median_offen(tmp_path, monkeypatch):
    monkeypatch.setattr(stand, "W", tmp_path)
    assert stand._vorcommit_median() == [
        "kein grüner pre-commit-Lauf in .pruefleiter/zeiten.csv"
    ]


def test_median_zaehlt_nur_die_letzten_zwanzig_laeufe(tmp_path, monkeypatch):
    monkeypatch.setattr(stand, "W", tmp_path)
    _zeiten(tmp_path, *([60.0] * 30 + [1.0] * 20))
    assert stand._vorcommit_median() == []


def test_ungepruefte_commits_werden_gekuerzt_genannt(monkeypatch):
    commits = [f"{n:040x}" for n in range(12)]
    befund = stand.pruefstempel.Ungeprueft(commits, stempel_gefunden=False)
    monkeypatch.setattr(stand.pruefstempel, "ungestempelte", lambda w: befund)
    (meldung,) = stand.ungepruefte()
    assert meldung.startswith("12 ungeprüfte Commits (0000000, 0000000")
    assert meldung.endswith("und 2 weitere, kein Stempel in diesem Klon)")


def test_ohne_ungepruefte_commits_nichts_offen(monkeypatch):
    befund = stand.pruefstempel.Ungeprueft([], stempel_gefunden=True)
    monkeypatch.setattr(stand.pruefstempel, "ungestempelte", lambda w: befund)
    assert stand.ungepruefte() == []


class _Lauf:
    def __init__(self, code, stderr=""):
        self.returncode, self.stderr = code, stderr


def _hook_antworten(monkeypatch, tmp_path, befehl, lesen, stop):
    def antwort(baum, ereignis, *argumente):
        return {"befehl": befehl, "datei_lesen": lesen, "stop": stop}[argumente[-1]]

    (tmp_path / "src/telco_radar").mkdir(parents=True)
    monkeypatch.setattr(stand, "_hook", antwort)
    monkeypatch.setattr(
        stand, "_wegwerf_baum", lambda: contextlib.nullcontext(tmp_path)
    )


def test_hook_proben_sperren_ist_erfuellt(monkeypatch, tmp_path):
    _hook_antworten(monkeypatch, tmp_path, _Lauf(2), _Lauf(2), _Lauf(2, "x [F401] y"))
    assert stand.hook_proben() == []


def test_hook_proben_nennen_jede_luecke(monkeypatch, tmp_path):
    _hook_antworten(monkeypatch, tmp_path, _Lauf(0), _Lauf(0), _Lauf(2, "Stufe 0"))
    assert stand.hook_proben() == [
        "--no-verify nicht gesperrt",
        "Read von html.py ohne limit nicht gesperrt",
        "Stop mit rotem Lint lässt die Sitzung enden",
    ]


def test_hook_probe_ruft_das_echte_skript():
    befehl = {"tool_input": {"command": "git commit --no-verify -m probe"}}
    hook = "scripts/claude_hooks.py"
    assert stand._hook(stand.W, befehl, hook, "befehl").returncode == stand.BLOCKIERT
    frei = {"tool_input": {"command": "git status"}}
    assert stand._hook(stand.W, frei, hook, "befehl").returncode == 0
