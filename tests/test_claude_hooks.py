import importlib
import json
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


def test_stop_ist_rot_bis_zum_dritten_mal_dann_endet_die_sitzung(tmp_path, capsys):
    ereignis = {"session_id": "s1"}
    ausgabe = ["Prüfleiter rot in Stufe 1 Lint", "a.py:1 [F401]"]
    codes = [
        claude_hooks.stop_ausgang(tmp_path, False, ausgabe, ereignis) for _ in "123"
    ]
    assert codes == [2, 2, 0]
    assert "[F401]" in capsys.readouterr().err
    befund = (tmp_path / claude_hooks.STOP_BEFUND).read_text("utf-8")
    assert befund.splitlines() == ausgabe
    assert claude_hooks.stop_ausgang(tmp_path, False, ausgabe, ereignis) == 2


def test_gruener_stop_setzt_den_zaehler_zurueck(tmp_path):
    ereignis = {"session_id": "s1"}
    assert claude_hooks.stop_ausgang(tmp_path, False, [], ereignis) == 2
    assert claude_hooks.stop_ausgang(tmp_path, False, [], ereignis) == 2
    assert claude_hooks.stop_ausgang(tmp_path, True, [], ereignis) == 0
    assert claude_hooks.stop_ausgang(tmp_path, False, [], ereignis) == 2
    assert claude_hooks.stop_ausgang(tmp_path, False, [], {"session_id": "s2"}) == 2


def test_stop_ohne_venv_ist_rot_mit_hinweis(tmp_path, capsys):
    assert claude_hooks.stop({"session_id": "s"}, tmp_path) == 2
    assert "make venv" in capsys.readouterr().err


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
        gruppe = {"hooks": [{"type": "command", "command": f"python {befehl}"}]}
        if matcher:
            gruppe["matcher"] = matcher
        hooks.setdefault(ereignis, []).append(gruppe)
    return hooks


def _ordner(tmp_path):
    for ordner in waechter_claude.ORDNER_CLAUDE_MD:
        (tmp_path / ordner).mkdir(parents=True)
        (tmp_path / ordner / "CLAUDE.md").write_text("# Kurz\n", "utf-8")


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
    (meldung,) = waechter_claude.vertrag(tmp_path)
    assert "Hook Stop" in meldung


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
