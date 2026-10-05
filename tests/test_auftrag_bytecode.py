import importlib
import os
import py_compile
import subprocess
import sys
from pathlib import Path

WURZEL = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(WURZEL / "tools"))
sys.path.insert(0, str(WURZEL / "scripts"))
prozess = importlib.import_module("auftrag_prozess")
zaun = importlib.import_module("auftrag_zaun")
claude_hooks = importlib.import_module("claude_hooks")

HOOK_SCHLUESSEL = "core." + "hooksPath"


def _git(ort: Path, *argumente: str) -> str:
    umgebung = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    lauf = subprocess.run(
        ["git", *argumente], cwd=ort, env=umgebung, capture_output=True, check=True
    )
    return lauf.stdout.decode().strip()


def _vergifteter_bytecode(ort: Path) -> None:
    modul = ort / "modul.py"
    modul.write_text("X = 2\n", "utf-8")
    py_compile.compile(str(modul), doraise=True)
    zeit = modul.stat().st_mtime_ns
    modul.write_text("X = 1\n", "utf-8")
    os.utime(modul, ns=(zeit, zeit))


def test_gestartetes_python_liest_keinen_bytecode_aus_dem_baum(tmp_path):
    _vergifteter_bytecode(tmp_path)
    befehl = [sys.executable, "-c", "import modul; print(modul.X)"]

    lauf = prozess.starten(befehl, tmp_path)

    assert lauf.stdout.strip() == "1"


def test_gegenprobe_ohne_eigenen_ordner_liest_python_den_bytecode(tmp_path):
    _vergifteter_bytecode(tmp_path)
    befehl = [sys.executable, "-c", "import modul; print(modul.X)"]
    umgebung = prozess.ohne_git() | {"PYTHONDONTWRITEBYTECODE": "1"}
    umgebung.pop("PYTHONPYCACHEPREFIX", None)

    lauf = subprocess.run(
        befehl, cwd=tmp_path, env=umgebung, capture_output=True, text=True
    )

    assert lauf.stdout.strip() == "2"


def _repo(ort: Path) -> Path:
    ort.mkdir()
    _git(ort, "init", "-q")
    (ort / ".gitignore").write_text("__pycache__/\n*.log\n", "utf-8")
    return ort


def test_zaun_uebergeht_bytecode_im_worktree(tmp_path):
    wt = _repo(tmp_path / "wt")
    vorher = zaun.stand(wt, tmp_path)
    (wt / "paket" / "__pycache__").mkdir(parents=True)
    (wt / "paket" / "__pycache__" / "a.cpython-311.pyc").write_bytes(b"x")

    assert zaun.verletzt(vorher, zaun.stand(wt, tmp_path)) == []


def test_zaun_meldet_weiter_andere_ignorierte_dateien(tmp_path):
    wt = _repo(tmp_path / "wt")
    vorher = zaun.stand(wt, tmp_path)
    (wt / "spur.log").write_text("x", "utf-8")

    assert zaun.verletzt(vorher, zaun.stand(wt, tmp_path)) == ["wt:spur.log"]


def test_sitzung_laesst_git_config_bei_gleichem_hook_ordner_unberuehrt(tmp_path):
    repo = _repo(tmp_path / "repo")
    (repo / claude_hooks.HOOKS).mkdir(parents=True)
    (repo / claude_hooks.HOOKS / "pre-commit").write_text("", "utf-8")
    python = repo / ".venv" / "bin" / "python"
    python.parent.mkdir(parents=True)
    python.write_text("#!/bin/sh\nexit 0\n", "utf-8")
    python.chmod(0o755)
    (repo / "scripts").mkdir()
    _git(repo, "config", HOOK_SCHLUESSEL, claude_hooks.HOOKS)
    config = repo / ".git" / "config"
    vorher = (config.stat().st_ino, config.stat().st_ctime_ns)

    claude_hooks.sitzung({}, repo)

    assert (config.stat().st_ino, config.stat().st_ctime_ns) == vorher
    assert _git(repo, "config", "--get", HOOK_SCHLUESSEL) == claude_hooks.HOOKS


def test_sitzung_setzt_einen_abweichenden_hook_ordner(tmp_path):
    repo = _repo(tmp_path / "repo")
    (repo / claude_hooks.HOOKS).mkdir(parents=True)
    (repo / claude_hooks.HOOKS / "pre-commit").write_text("", "utf-8")
    python = repo / ".venv" / "bin" / "python"
    python.parent.mkdir(parents=True)
    python.write_text("#!/bin/sh\nexit 0\n", "utf-8")
    python.chmod(0o755)
    (repo / "scripts").mkdir()

    claude_hooks.sitzung({}, repo)

    assert _git(repo, "config", "--get", HOOK_SCHLUESSEL) == claude_hooks.HOOKS
