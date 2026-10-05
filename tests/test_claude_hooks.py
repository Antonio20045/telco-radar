import importlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
claude_hooks = importlib.import_module("claude_hooks")
waechter_claude = importlib.import_module("waechter_claude")


def _bash(befehl):
    return claude_hooks.befehl({"tool_input": {"command": befehl}})


@pytest.mark.parametrize(
    "befehl",
    [
        "git commit --no-verify -m x",
        "git push --no-verify",
        "git push --no-ver",
        'bash -c "git push --no-verify origin main"',
        "git -c core.hooksPath=/dev/null push",
        "git config CORE.HOOKSPATH /tmp",
        "git commit -n -m x",
        "git commit -nm x",
        "git commit -m x -n",
        "git add a && git commit -an",
        'git commit --no-"verify" -m x',
        'git config core.hooks"Path" /dev/null',
        "sh -c 'git commit -n -m x'",
        'bash -c "git commit -nm x"',
        "git -c alias.ci=commit ci -n -m x",
        "chmod -x .githooks/pre-commit",
        "git push origin main --force",
        "git push --force-with-lease",
        "git push origin +main",
        "git push -fu origin main",
        "git add --all",
        "git add -A",
        "git add .",
    ],
)
def test_befehle_die_hooks_umgehen_sind_gesperrt(befehl):
    assert _bash(befehl) is not None


@pytest.mark.parametrize(
    "befehl",
    [
        "git status",
        "git commit -m x",
        "git commit -am x",
        'git commit -m "-n im Text"',
        "git commit -mn",
        "git push origin HEAD:main",
        "grep -n --no-messages x y",
        "grep -rn core.hooksPath scripts/",
        "git commit -m x -- -n",
        "git add scripts/a.py tests/b.py",
        "git -C /tmp/x status",
        "git restore site data",
    ],
)
def test_gewoehnliche_befehle_laufen(befehl):
    assert _bash(befehl) is None


def _datei(tmp_path, zeilen):
    pfad = tmp_path / "gross.py"
    pfad.write_text("x = 1\n" * zeilen, "utf-8")
    return str(pfad)


def test_grosse_datei_ohne_limit_ist_gesperrt(tmp_path):
    pfad = _datei(tmp_path, claude_hooks.GROSS_AB_ZEILEN + 1)
    grund = claude_hooks.datei_lesen({"tool_input": {"file_path": pfad}})
    assert grund.startswith("gross.py hat 801 Zeilen")


def test_grosse_datei_mit_kleinem_limit_ist_frei(tmp_path):
    pfad = _datei(tmp_path, 5000)
    eingabe = {"file_path": pfad, "limit": claude_hooks.GROSS_AB_ZEILEN}
    assert claude_hooks.datei_lesen({"tool_input": eingabe}) is None
    eingabe["limit"] = claude_hooks.GROSS_AB_ZEILEN + 1
    assert claude_hooks.datei_lesen({"tool_input": eingabe}) is not None


def test_binaerdateien_sind_frei(tmp_path):
    bild = tmp_path / "shot.png"
    bild.write_bytes(b"\x89PNG\0" + b"\n" * 5000)
    assert claude_hooks.datei_lesen({"tool_input": {"file_path": str(bild)}}) is None


def test_kleine_und_fehlende_dateien_sind_frei(tmp_path):
    pfad = _datei(tmp_path, claude_hooks.GROSS_AB_ZEILEN)
    assert claude_hooks.datei_lesen({"tool_input": {"file_path": pfad}}) is None
    fehlt = str(tmp_path / "fehlt.py")
    assert claude_hooks.datei_lesen({"tool_input": {"file_path": fehlt}}) is None


def test_nach_edit_meldet_neuen_lintbefund(tmp_path):
    datei = tmp_path / "src" / "rotprobe.py"
    datei.parent.mkdir()
    datei.write_text('"""Probe."""\n\nimport os\n', "utf-8")
    grund = claude_hooks.nach_edit({"tool_input": {"file_path": str(datei)}}, tmp_path)
    assert "[F401]" in grund
    datei.write_text('"""Probe."""\n\nimport os\n\nPFAD = os.sep\n', "utf-8")
    assert (
        claude_hooks.nach_edit({"tool_input": {"file_path": str(datei)}}, tmp_path)
        is None
    )


def test_nach_edit_ueberspringt_andere_dateien(tmp_path):
    datei = tmp_path / "notiz.md"
    datei.write_text("import os\n", "utf-8")
    assert (
        claude_hooks.nach_edit({"tool_input": {"file_path": str(datei)}}, tmp_path)
        is None
    )


def test_stop_ist_dreimal_rot_dann_endet_die_sitzung(tmp_path, capsys):
    ereignis = {"session_id": "s1", "stop_hook_active": True}
    ausgabe = ["Prüfleiter rot in Stufe 1 Lint", "a.py:1 [F401]"]
    codes = [
        claude_hooks.stop_ausgang(tmp_path, False, ausgabe, ereignis) for _ in "1234"
    ]
    assert codes == [2, 2, 2, 0]
    assert "[F401]" in capsys.readouterr().err
    befund = (tmp_path / claude_hooks.STOP_BEFUND).read_text("utf-8")
    assert befund.splitlines() == ausgabe
    assert claude_hooks.stop_ausgang(tmp_path, False, ausgabe, ereignis) == 2


def test_zwei_sitzungen_zaehlen_getrennt_und_enden_beide(tmp_path):
    codes = [
        claude_hooks.stop_ausgang(tmp_path, False, [], {"session_id": sitzung})
        for _ in "1234"
        for sitzung in ("s1", "s2")
    ]
    assert codes == [2, 2, 2, 2, 2, 2, 0, 0]


def test_neuer_stopp_ohne_erzwungene_fortsetzung_zaehlt_von_vorn(tmp_path):
    def stopp(aktiv):
        ereignis = {"session_id": "s1", "stop_hook_active": aktiv}
        return claude_hooks.stop_ausgang(tmp_path, False, [], ereignis)

    assert [stopp(False), stopp(True), stopp(False)] == [2, 2, 2]
    assert [stopp(True), stopp(True), stopp(True)] == [2, 2, 0]


def test_zaehler_behaelt_nur_die_juengsten_sitzungen(tmp_path):
    for nummer in range(claude_hooks.STOP_SITZUNGEN + 5):
        claude_hooks.stop_ausgang(tmp_path, False, [], {"session_id": f"s{nummer}"})
    stand = json.loads((tmp_path / claude_hooks.STOP_ZAEHLER).read_text("utf-8"))
    assert len(stand) == claude_hooks.STOP_SITZUNGEN
    assert "s0" not in stand
    assert stand[f"s{claude_hooks.STOP_SITZUNGEN + 4}"] == [1, 1]


def test_stopps_ohne_erzwungene_fortsetzung_enden_nach_der_obergrenze(tmp_path):
    ereignis = {"session_id": "s1", "stop_hook_active": False}
    codes = [
        claude_hooks.stop_ausgang(tmp_path, False, [], ereignis)
        for _ in range(claude_hooks.STOP_HOECHSTENS_GESAMT + 2)
    ]
    assert codes == [2] * claude_hooks.STOP_HOECHSTENS_GESAMT + [0, 0]
    assert claude_hooks.stop_ausgang(tmp_path, True, [], ereignis) == 0
    assert claude_hooks.stop_ausgang(tmp_path, False, [], ereignis) == 0
    assert claude_hooks.stop_ausgang(tmp_path, False, [], {"session_id": "s2"}) == 2


@pytest.mark.parametrize("inhalt", ["kaputt", "[1]", '{"s1": "x"}'])
def test_unlesbarer_zaehler_zaehlt_von_vorn(tmp_path, inhalt):
    (tmp_path / claude_hooks.STOP_ZAEHLER).write_text(inhalt, "utf-8")
    ereignis = {"session_id": "s1"}
    codes = [claude_hooks.stop_ausgang(tmp_path, False, [], ereignis) for _ in "1234"]
    assert codes == [2, 2, 2, 0]


def test_gruener_stop_setzt_den_zaehler_zurueck(tmp_path):
    ereignis = {"session_id": "s1"}
    assert claude_hooks.stop_ausgang(tmp_path, False, [], ereignis) == 2
    assert claude_hooks.stop_ausgang(tmp_path, False, [], ereignis) == 2
    assert claude_hooks.stop_ausgang(tmp_path, True, [], ereignis) == 0
    assert claude_hooks.stop_ausgang(tmp_path, False, [], ereignis) == 2
    assert claude_hooks.stop_ausgang(tmp_path, False, [], {"session_id": "s2"}) == 2


def test_stop_ohne_venv_endet_mit_hinweis_an_den_nutzer(tmp_path, capsys):
    assert claude_hooks.stop({"session_id": "s"}, tmp_path) == 0
    meldung = json.loads(capsys.readouterr().out)
    assert "make venv" in meldung["systemMessage"]


def _python_ohne_ruff(tmp_path, monkeypatch):
    fremd = tmp_path / "fremd" / "python3"
    fremd.parent.mkdir()
    monkeypatch.setattr(claude_hooks.sys, "executable", str(fremd))
    datei = tmp_path / "a.py"
    datei.write_text("import os\n", "utf-8")
    return {"tool_input": {"file_path": str(datei)}}


def test_nach_edit_ohne_venv_blockiert_nicht(tmp_path, monkeypatch):
    ereignis = _python_ohne_ruff(tmp_path, monkeypatch)
    assert claude_hooks.nach_edit(ereignis, tmp_path) is None


def test_nach_edit_ausserhalb_des_venv_ruft_sich_im_venv(tmp_path, monkeypatch):
    ereignis = _python_ohne_ruff(tmp_path, monkeypatch)
    python = tmp_path / ".venv" / "bin" / "python"
    python.parent.mkdir(parents=True)
    python.write_text("#!/bin/sh\ncat >&2\nexit 2\n", "utf-8")
    python.chmod(0o755)
    assert claude_hooks.nach_edit(ereignis, tmp_path) is None
    (python.parent / "ruff").touch()
    assert json.loads(claude_hooks.nach_edit(ereignis, tmp_path)) == ereignis


def test_unlesbares_ereignis_ist_leer():
    assert claude_hooks.lies_ereignis("kein json") == {}
    assert claude_hooks.lies_ereignis("[1]") == {}
    assert claude_hooks.lies_ereignis('{"a": 1}') == {"a": 1}


def _einstellungen(tmp_path, hooks, deny):
    ordner = tmp_path / ".claude"
    ordner.mkdir(exist_ok=True)
    daten = {"permissions": {"deny": deny}, "hooks": hooks}
    (ordner / "settings.json").write_text(json.dumps(daten), "utf-8")


def _volle_hooks():
    hooks = {}
    for ereignis, matcher, befehl in waechter_claude.PFLICHT_HOOKS:
        kommando = f'python3 "$CLAUDE_PROJECT_DIR"/{befehl}'
        hook = {"type": "command", "command": kommando, "timeout": 300}
        gruppe = {"hooks": [hook]}
        if matcher:
            gruppe["matcher"] = matcher
        hooks.setdefault(ereignis, []).append(gruppe)
    return hooks


def _ordner(tmp_path):
    for ordner in waechter_claude.ORDNER_CLAUDE_MD:
        (tmp_path / ordner).mkdir(parents=True)
        (tmp_path / ordner / "CLAUDE.md").write_text("# Kurz\n", "utf-8")
    skript = tmp_path / waechter_claude.HOOK_SKRIPT
    skript.parent.mkdir(exist_ok=True)
    skript.write_text("", "utf-8")


def test_volle_einstellungen_halten_den_vertrag(tmp_path):
    _ordner(tmp_path)
    _einstellungen(tmp_path, _volle_hooks(), list(waechter_claude.PFLICHT_SPERREN))
    assert waechter_claude.vertrag(tmp_path) == []


def test_fehlender_stop_hook_und_fehlende_sperre_sind_rot(tmp_path):
    _ordner(tmp_path)
    hooks = _volle_hooks()
    del hooks["Stop"]
    deny = [s for s in waechter_claude.PFLICHT_SPERREN if s != "Bash(*--no-verify*)"]
    _einstellungen(tmp_path, hooks, deny)
    assert waechter_claude.vertrag(tmp_path) == [
        ".claude/settings.json: Hook Stop * ruft nicht scripts/claude_hooks.py stop",
        ".claude/settings.json: Sperre Bash(*--no-verify*) fehlt",
    ]


@pytest.mark.parametrize(
    "sperre",
    [
        "Edit(scripts/claude_rolle.py)",
        "Edit(scripts/claude_rolle_shell.py)",
        "Edit(.claude/agents/**)",
    ],
)
def test_rollenregel_und_agenten_ohne_sperre_sind_rot(tmp_path, sperre):
    _ordner(tmp_path)
    deny = [s for s in waechter_claude.PFLICHT_SPERREN if s != sperre]
    _einstellungen(tmp_path, _volle_hooks(), deny)
    assert waechter_claude.vertrag(tmp_path) == [
        f".claude/settings.json: Sperre {sperre} fehlt"
    ]


def test_falscher_matcher_zaehlt_nicht(tmp_path):
    _ordner(tmp_path)
    hooks = _volle_hooks()
    hooks["PreToolUse"][1]["matcher"] = "Glob"
    _einstellungen(tmp_path, hooks, list(waechter_claude.PFLICHT_SPERREN))
    (meldung,) = waechter_claude.vertrag(tmp_path)
    assert "PreToolUse Read" in meldung


@pytest.mark.parametrize("zusatz", [" || true", "; exit 0", " | cat", " & ", "$(x)"])
def test_entschaerfter_hook_bricht_den_vertrag(tmp_path, zusatz):
    _ordner(tmp_path)
    hooks = _volle_hooks()
    hook = hooks["Stop"][0]["hooks"][0]
    hook["command"] = hook["command"] + zusatz
    _einstellungen(tmp_path, hooks, list(waechter_claude.PFLICHT_SPERREN))
    meldung, fremd = waechter_claude.vertrag(tmp_path)
    assert "Hook Stop" in meldung
    assert fremd == ".claude/settings.json: fremder Hook unter Stop"


@pytest.mark.parametrize(
    ("ereignis", "stelle", "frist", "befehl", "noetig"),
    [
        ("Stop", 0, 200, "stop", 285),
        ("Stop", 0, "300", "stop", 285),
        ("PostToolUse", 0, 1, "nach_edit", 30),
        ("PreToolUse", 0, 0, "befehl", 5),
        ("PreToolUse", 1, True, "datei_lesen", 5),
        ("SessionStart", 0, 60, "sitzung", 300),
    ],
)
def test_zu_kurze_frist_eines_hooks_ist_rot(
    tmp_path, ereignis, stelle, frist, befehl, noetig
):
    _ordner(tmp_path)
    hooks = _volle_hooks()
    hooks[ereignis][stelle]["hooks"][0]["timeout"] = frist
    _einstellungen(tmp_path, hooks, list(waechter_claude.PFLICHT_SPERREN))
    assert waechter_claude.vertrag(tmp_path) == [
        f".claude/settings.json: Frist von scripts/claude_hooks.py {befehl}"
        f" unter {noetig} s"
    ]


def test_fehlende_frist_gilt_als_vorgabe_von_claude_code(tmp_path):
    _ordner(tmp_path)
    hooks = _volle_hooks()
    for gruppen in hooks.values():
        for gruppe in gruppen:
            del gruppe["hooks"][0]["timeout"]
    _einstellungen(tmp_path, hooks, list(waechter_claude.PFLICHT_SPERREN))
    assert waechter_claude.vertrag(tmp_path) == []


def test_frist_des_edit_hooks_deckt_seinen_unterlauf():
    nach_edit = waechter_claude.MINDESTFRIST["nach_edit"]
    assert nach_edit > claude_hooks.NACH_EDIT_SEKUNDEN


@pytest.mark.parametrize("art", ["prompt", "bogus", None])
def test_hook_ohne_type_command_ist_rot(tmp_path, art):
    _ordner(tmp_path)
    hooks = _volle_hooks()
    hooks["Stop"][0]["hooks"][0]["type"] = art
    _einstellungen(tmp_path, hooks, list(waechter_claude.PFLICHT_SPERREN))
    assert waechter_claude.vertrag(tmp_path) == [
        ".claude/settings.json: Hook Stop * ruft nicht scripts/claude_hooks.py stop",
        ".claude/settings.json: fremder Hook unter Stop",
    ]


@pytest.mark.parametrize("datei", ["settings.json", "settings.local.json"])
def test_env_in_den_einstellungen_ist_rot(tmp_path, datei):
    umgebung = {"env": {"PYTHONPATH": "/tmp/x"}}
    if datei == "settings.local.json":
        (tmp_path / ".claude").mkdir()
        (tmp_path / ".claude" / datei).write_text(json.dumps(umgebung), "utf-8")
        meldungen = _voll_mit(tmp_path, lambda d: None)
    else:
        meldungen = _voll_mit(tmp_path, lambda d: d.update(umgebung))
    assert meldungen == [f".claude/{datei}: env ist verboten"]


def test_hooks_als_liste_ist_rot_statt_absturz(tmp_path):
    _voll_mit(tmp_path, lambda d: d.update(hooks=[]))
    meldungen = waechter_claude.einstellungen(tmp_path)
    assert meldungen[0] == ".claude/settings.json: hooks kein Objekt"
    assert len(meldungen) == 1 + len(waechter_claude.PFLICHT_HOOKS)


@pytest.mark.parametrize(
    "kommando",
    [
        'echo "$CLAUDE_PROJECT_DIR"/scripts/claude_hooks.py stop',
        ': "$CLAUDE_PROJECT_DIR"/scripts/claude_hooks.py stop',
        'python3 -c 1 "$CLAUDE_PROJECT_DIR"/scripts/claude_hooks.py stop',
        'python3 "$CLAUDE_PROJECT_DIR"/scripts/claude_hooks.py stop x',
        "python3 scripts/claude_hooks.py stop",
    ],
)
def test_fremder_anfang_des_hooks_bricht_den_vertrag(tmp_path, kommando):
    _ordner(tmp_path)
    hooks = _volle_hooks()
    hooks["Stop"][0]["hooks"][0]["command"] = kommando
    _einstellungen(tmp_path, hooks, list(waechter_claude.PFLICHT_SPERREN))
    meldung, fremd = waechter_claude.vertrag(tmp_path)
    assert "Hook Stop" in meldung
    assert fremd == ".claude/settings.json: fremder Hook unter Stop"


def test_venv_python_im_hook_ist_erlaubt(tmp_path):
    _ordner(tmp_path)
    hooks = _volle_hooks()
    hook = hooks["PostToolUse"][0]["hooks"][0]
    hook["command"] = (
        '"$CLAUDE_PROJECT_DIR"/.venv/bin/python'
        ' "$CLAUDE_PROJECT_DIR"/scripts/claude_hooks.py nach_edit'
    )
    _einstellungen(tmp_path, hooks, list(waechter_claude.PFLICHT_SPERREN))
    assert waechter_claude.vertrag(tmp_path) == []


def test_projektpfad_im_hook_ist_erlaubt(tmp_path):
    _ordner(tmp_path)
    hooks = _volle_hooks()
    hook = hooks["Stop"][0]["hooks"][0]
    hook["command"] = 'python3 "$CLAUDE_PROJECT_DIR"/scripts/claude_hooks.py stop'
    _einstellungen(tmp_path, hooks, list(waechter_claude.PFLICHT_SPERREN))
    assert waechter_claude.vertrag(tmp_path) == []


def test_alte_einstellungen_meldet_nur_der_stand(tmp_path):
    _ordner(tmp_path)
    _einstellungen(tmp_path, {}, [])
    assert waechter_claude.vertrag(tmp_path) == []
    assert len(waechter_claude.einstellungen(tmp_path)) == len(
        waechter_claude.PFLICHT_HOOKS
    ) + len(waechter_claude.PFLICHT_SPERREN)


def _git(ort, *argumente):
    rein = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid", *argumente],
        cwd=ort,
        env=rein,
        capture_output=True,
        check=True,
    )


def _commit(ort, *pfade):
    _git(ort, "add", *pfade)
    _git(ort, "commit", "-q", "-m", "x")


@pytest.fixture()
def eingerichtet(tmp_path):
    _ordner(tmp_path)
    _einstellungen(tmp_path, _volle_hooks(), list(waechter_claude.PFLICHT_SPERREN))
    _git(tmp_path, "init", "-q", "-b", "main")
    _commit(tmp_path, waechter_claude.HOOK_SKRIPT, waechter_claude.EINSTELLUNGEN)
    return tmp_path


def test_entfernte_hooks_bleiben_pflicht(eingerichtet):
    _einstellungen(eingerichtet, {}, list(waechter_claude.PFLICHT_SPERREN))
    _commit(eingerichtet, waechter_claude.EINSTELLUNGEN)
    meldungen = waechter_claude.vertrag(eingerichtet)
    assert len(meldungen) == len(waechter_claude.PFLICHT_HOOKS)
    assert all("ruft nicht scripts/claude_hooks.py" in m for m in meldungen)


def test_geloeschte_einstellungen_bleiben_pflicht(eingerichtet):
    (eingerichtet / waechter_claude.EINSTELLUNGEN).unlink()
    assert waechter_claude.vertrag(eingerichtet) == [
        ".claude/settings.json nicht lesbar (FileNotFoundError)"
    ]


def test_geloeschtes_skript_und_einstellungen_bleiben_pflicht(eingerichtet):
    (eingerichtet / waechter_claude.HOOK_SKRIPT).unlink()
    (eingerichtet / waechter_claude.EINSTELLUNGEN).unlink()
    _git(eingerichtet, "commit", "-q", "-am", "weg")
    assert waechter_claude.vertrag(eingerichtet) == [
        "scripts/claude_hooks.py fehlt",
        ".claude/settings.json nicht lesbar (FileNotFoundError)",
    ]


def test_nie_eingerichtete_einstellungen_meldet_nur_der_stand(tmp_path):
    _ordner(tmp_path)
    _einstellungen(tmp_path, {}, [])
    _git(tmp_path, "init", "-q", "-b", "main")
    _commit(tmp_path, waechter_claude.HOOK_SKRIPT, waechter_claude.EINSTELLUNGEN)
    assert waechter_claude.vertrag(tmp_path) == []


def test_ordner_claude_md_fehlt_oder_ist_zu_lang(tmp_path):
    _ordner(tmp_path)
    (tmp_path / waechter_claude.ORDNER_CLAUDE_MD[1] / "CLAUDE.md").unlink()
    lang = tmp_path / "src" / "x" / "CLAUDE.md"
    lang.parent.mkdir()
    lang.write_text("z\n" * (waechter_claude.ORDNER_ZEILEN + 1), "utf-8")
    assert waechter_claude.ordner_claude_md(tmp_path) == [
        "src/telco_radar/analyze/CLAUDE.md fehlt",
        "src/x/CLAUDE.md hat 41 Zeilen, erlaubt 40",
    ]


def test_sitzung_ohne_venv_nennt_das_scheitern_und_die_folge(tmp_path, capsys):
    assert claude_hooks.sitzung({}, tmp_path) is None
    zeile = capsys.readouterr().out
    assert "make venv gescheitert (" in zeile
    assert "Edit- und Stop-Hook prüfen nichts" in zeile


def test_sitzung_nennt_das_fehlende_python_aus_python_version(tmp_path, capsys):
    (tmp_path / ".python-version").write_text("2.9\n", "utf-8")
    claude_hooks.sitzung({}, tmp_path)
    zeile = capsys.readouterr().out
    assert "python2.9 fehlt, auf dem Mac: brew install python@2.9" in zeile


def test_gruen_setzt_die_folge_zurueck_aber_nicht_die_summe(tmp_path):
    ereignis = {"session_id": "s1"}
    for gruen in [False] * 2 + [True] + [False] * 2:
        claude_hooks.stop_ausgang(tmp_path, gruen, [], ereignis)
    stand = json.loads((tmp_path / claude_hooks.STOP_ZAEHLER).read_text("utf-8"))
    assert stand == {"s1": [2, 4]}


@pytest.mark.parametrize("alt", [2, [0, -1000], [1], [True, 1]])
def test_fremdes_oder_negatives_zaehlerformat_zaehlt_von_vorn(tmp_path, alt):
    zaehler = tmp_path / claude_hooks.STOP_ZAEHLER
    zaehler.write_text(json.dumps({"s1": alt}), "utf-8")
    claude_hooks.stop_ausgang(tmp_path, False, [], {"session_id": "s1"})
    assert json.loads(zaehler.read_text("utf-8")) == {"s1": [1, 1]}


def test_fehlendes_hook_skript_ist_rot(eingerichtet):
    (eingerichtet / waechter_claude.HOOK_SKRIPT).unlink()
    assert waechter_claude.vertrag(eingerichtet) == ["scripts/claude_hooks.py fehlt"]


def _voll_mit(tmp_path, aendern):
    _ordner(tmp_path)
    hooks = _volle_hooks()
    daten = {"permissions": {"deny": list(waechter_claude.PFLICHT_SPERREN)}}
    daten["hooks"] = hooks
    aendern(daten)
    (tmp_path / ".claude").mkdir(exist_ok=True)
    (tmp_path / ".claude/settings.json").write_text(json.dumps(daten), "utf-8")
    return waechter_claude.vertrag(tmp_path)


def test_alle_hooks_aus_ist_rot(tmp_path):
    meldungen = _voll_mit(tmp_path, lambda d: d.update(disableAllHooks=True))
    assert meldungen == [".claude/settings.json: disableAllHooks ist verboten"]


def test_async_im_stop_hook_ist_rot(tmp_path):
    meldungen = _voll_mit(
        tmp_path, lambda d: d["hooks"]["Stop"][0]["hooks"][0].update({"async": True})
    )
    assert "Hook Stop * ruft nicht" in meldungen[0]
    assert ".claude/settings.json: fremder Hook unter Stop" in meldungen


def test_zweiter_hook_neben_dem_stop_hook_ist_rot(tmp_path):
    fremd = {"type": "command", "command": "echo '{\"continue\":false}'"}

    def zweiter(daten):
        daten["hooks"]["Stop"].append({"hooks": [fremd]})
        daten["hooks"]["Stop"][0]["hooks"].append(fremd)

    meldungen = _voll_mit(tmp_path, zweiter)
    assert meldungen.count(".claude/settings.json: fremder Hook unter Stop") == 2


def test_lokale_einstellungen_duerfen_keine_hooks_setzen(tmp_path):
    lokal = tmp_path / ".claude" / "settings.local.json"
    lokal.parent.mkdir()
    lokal.write_text(json.dumps({"disableAllHooks": True, "hooks": {}}), "utf-8")
    assert _voll_mit(tmp_path, lambda d: None) == [
        ".claude/settings.local.json: disableAllHooks ist verboten",
        ".claude/settings.local.json: hooks ist verboten",
    ]
