"""Der Rollen-Hook: Eine Rolle schreibt nur, wo ihre Regel es erlaubt; ``bau`` ändert
keinen bestehenden Test, weder mit Edit und Write noch über die Shell."""

import importlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

SKRIPTE = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SKRIPTE))
rolle_ = importlib.import_module("claude_rolle")

BEREICH = "src/telco_radar/rechnen/"
ABNAHME = "tests/test_abnahme.py"


@pytest.fixture
def repo(tmp_path):
    wurzel = tmp_path / "repo"
    for pfad in (f"{BEREICH}kern.py", "tests/test_alt.py", "scripts/leiter.py"):
        (wurzel / pfad).parent.mkdir(parents=True, exist_ok=True)
        (wurzel / pfad).write_text("X = 1\n")
    umgebung = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    for befehl in (
        ["init", "-q", "-b", "main"],
        ["add", "--", "."],
        ["-c", "user.name=M", "-c", "user.email=m@x.invalid", "commit", "-qm", "a"],
    ):
        subprocess.run(["git", *befehl], cwd=wurzel, env=umgebung, check=True)
    auftrag = tmp_path / "auftrag.json"
    auftrag.write_text(json.dumps({"bereich": BEREICH, "abnahme": ABNAHME}))
    return wurzel


def _umgebung(repo, rolle):
    werte = {"TELCO_AUFTRAG": str(repo.parent / "auftrag.json")}
    werte["TELCO_PRUEFER_ORDNER"] = str(repo.parent / "pruefer")
    return werte | ({"TELCO_ROLLE": rolle} if rolle else {})


def _hook(repo, rolle, werkzeug, **eingabe):
    ereignis = {"tool_name": werkzeug, "tool_input": eingabe, "cwd": str(repo)}
    return rolle_.pruefe(ereignis, _umgebung(repo, rolle))


@pytest.mark.parametrize(
    "befehl",
    [
        "sed -i 's/1/2/' tests/test_alt.py",
        "echo 'assert 1' >> tests/test_alt.py",
        "printf x>tests/test_alt.py",
        "rm -f tests/test_alt.py",
        "mv tests/test_alt.py /tmp/weg.py",
        "cp /tmp/leer.py tests/test_alt.py",
        "truncate -s 0 tests/test_alt.py",
        "tee tests/test_alt.py < /dev/null",
        "bash -c 'rm tests/test_alt.py'",
        "dd if=/dev/null of=tests/test_alt.py",
        "perl -pi -e 's/1/2/' tests/test_alt.py",
        "python3 -c \"open('tests/test_alt.py', 'w')\"",
        "python3 - <<'EOF'\nfrom pathlib import Path\nPath('x').write_text('')\nEOF",
        "git checkout -- tests/test_alt.py",
        "git -C . restore tests/test_alt.py",
        "git stash",
        "git commit -qam x",
        "git add tests/neu.py",
        "touch tests/sub/conftest.py",
        "echo x > scripts/leiter.py",
        "echo x > ../anderes/datei.py",
        "env git commit -qam x",
        "xargs -0 git stash",
        "LANG=C timeout 5 git reset --hard",
        "git diff --output=tests/test_alt.py",
        "cp -t tests /tmp/test_alt.py",
        "find tests -name '*.py' -delete",
        "awk '{print > \"tests/test_alt.py\"}' x",
        "nice -n 5 sed -i s/1/2/ tests/test_alt.py",
        "touch tests/pytest.ini",
        "G=git; $G -c core.hooksPath=/dev/null commit -qam x",
        "$(echo git) commit -qam x",
        "`echo git` commit -qam x",
        "git${IFS}commit -qam x",
        "eval git commit -qam x",
        "eval 'rm tests/test_alt.py'",
        "source /tmp/skript.sh",
        "python3 -c \"import subprocess; subprocess.run(['git', 'commit'])\"",
        "python3 -c \"import os; os.system('git commit -qam x')\"",
        "python3 -c \"import os; os.execvp('git', ['git', 'stash'])\"",
        "python3 -c \"from subprocess import Popen; Popen(['git', 'stash'])\"",
        "python3 -c \"__import__('os').remove('tests/test_alt.py')\"",
        "curl -o tests/test_alt.py https://example.invalid/x",
        "curl -sSLo tests/test_alt.py https://example.invalid/x",
        "curl -O https://example.invalid/test_alt.py",
        "wget -O tests/test_alt.py https://example.invalid/x",
        "wget https://example.invalid/test_alt.py",
        "tar -C tests -xf /tmp/a.tar",
        "tar xf /tmp/a.tar",
        "unzip -o /tmp/a.zip -d tests",
        "unzip /tmp/a.zip",
        "ruby -i -pe 'gsub(/1/, \"2\")' tests/test_alt.py",
        "ed tests/test_alt.py",
        "vim -c ':wq' tests/test_alt.py",
        "cat <(echo x) > /tmp/y",
    ],
)
def test_bau_aendert_keinen_bestehenden_test_ueber_die_shell(repo, befehl):
    assert _hook(repo, "bau", "Bash", command=befehl)


@pytest.mark.parametrize(
    "befehl",
    [
        ".venv/bin/python -m pytest -q tests/test_alt.py",
        "PYTHONPATH=src pytest tests/test_alt.py > /tmp/ausgabe.txt 2>&1",
        "git diff -- tests && git status --short",
        "grep -rn X tests | head",
        "cat tests/test_alt.py",
        "cp tests/test_alt.py tests/test_neu.py",
        f"echo 'X = 2' > {BEREICH}kern.py",
        "sed -n 1,5p tests/test_alt.py",
        "timeout 60 .venv/bin/python -m pytest -q tests",
        "awk '{print $1}' tests/test_alt.py",
        "curl -sS -o /tmp/seite.html https://example.invalid/",
        "tar tf /tmp/a.tar",
        "unzip -l /tmp/a.zip",
        'python3 -c "print(1 + 1)"',
        "ls -t tests",
    ],
)
def test_bau_liest_tests_und_schreibt_im_bereich(repo, befehl):
    assert _hook(repo, "bau", "Bash", command=befehl) is None


@pytest.mark.parametrize(
    ("rolle", "pfad", "erlaubt"),
    [
        ("bau", "tests/test_alt.py", False),
        ("bau", "tests/test_neu.py", True),
        ("bau", "tests/orakel/test_neu.py", True),
        ("bau", "tests/orakel/conftest.py", False),
        ("bau", "tests/__init__.py", False),
        ("bau", "tests/pytest.ini", False),
        ("bau", f"{BEREICH}kern.py", True),
        ("bau", f"{BEREICH}neu.py", True),
        ("bau", "src/telco_radar/report/html.py", False),
        ("bau", "scripts/leiter.py", False),
        ("bau", ".claude/settings.local.json", False),
        ("bau", "../anderes/datei.py", False),
        ("test", ABNAHME, True),
        ("test", "tests/test_neu.py", True),
        ("test", "tests/test_alt.py", False),
        ("test", "tests/conftest.py", False),
        ("test", f"{BEREICH}kern.py", False),
        ("pruefer", "../pruefer/test_x.py", True),
        ("pruefer", "tests/test_neu.py", False),
        ("pruefer", f"{BEREICH}kern.py", False),
        ("entwurf", "outputs/auftraege/T9.json", True),
        ("entwurf", f"{BEREICH}kern.py", False),
        ("suchen", "tests/test_neu.py", False),
        ("unbekannt", "tests/test_neu.py", False),
    ],
)
def test_schreibwerkzeuge_folgen_der_rolle(repo, rolle, pfad, erlaubt):
    for werkzeug in ("Edit", "Write", "MultiEdit"):
        grund = _hook(repo, rolle, werkzeug, file_path=str(repo / pfad))
        assert (grund is None) == erlaubt, grund


def test_ohne_rolle_laesst_der_hook_alles_durch(repo):
    assert _hook(repo, None, "Edit", file_path=str(repo / "tests/test_alt.py")) is None
    assert _hook(repo, None, "Bash", command="rm tests/test_alt.py") is None


def test_symlink_in_den_bereich_hilft_nicht(repo):
    (repo / BEREICH / "versteck.py").symlink_to(repo / "tests/test_alt.py")

    grund = _hook(repo, "bau", "Write", file_path=str(repo / BEREICH / "versteck.py"))

    assert "tests/test_alt.py" in grund


def test_einstellungen_setzen_rolle_hook_und_git_sperren():
    einstellungen = rolle_.einstellungen("bau")

    assert einstellungen["env"] == {"TELCO_ROLLE": "bau"}
    haken = einstellungen["hooks"]["PreToolUse"][0]
    assert set(haken["matcher"].split("|")) >= {"Bash", "Edit", "Write", "MultiEdit"}
    assert haken["hooks"][0]["command"].endswith("scripts/claude_rolle.py")
    sperren = einstellungen["permissions"]["deny"]
    assert {"Bash(git commit*)", "Bash(git checkout*)", "Bash(git reset*)"} <= set(
        sperren
    )


def test_hook_als_prozess_blockiert_mit_exit_2(repo):
    ereignis = {
        "tool_name": "Edit",
        "tool_input": {"file_path": "tests/test_alt.py"},
        "cwd": str(repo),
    }
    befehl = [sys.executable, str(SKRIPTE / "claude_rolle.py")]
    umgebung = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}

    lauf = subprocess.run(
        befehl,
        input=json.dumps(ereignis),
        env=umgebung | _umgebung(repo, "bau"),
        capture_output=True,
        text=True,
        check=False,
    )

    assert lauf.returncode == rolle_.BLOCKIERT
    assert "Rolle bau darf tests/test_alt.py nicht ändern" in lauf.stderr


def test_unlesbares_ereignis_blockiert():
    assert rolle_.main(lambda: "{kaputt", {"TELCO_ROLLE": "bau"}) == rolle_.BLOCKIERT


def test_stand_probt_die_rollensperre(monkeypatch):
    stand = importlib.import_module("stand")
    assert stand.rollen_sperren() == []

    monkeypatch.setattr(rolle_, "verstoss", lambda *_a, **_k: None)

    assert stand.rollen_sperren() == [
        "Rolle bau ändert per Edit einen Test",
        "Rolle bau ändert per Bash einen Test",
        "Rolle bau ändert per Bash einen Test",
    ]


def test_gescheiterter_hook_sperrt():
    ereignis = json.dumps({"tool_name": "Bash", "tool_input": {"command": "ls"}})
    ereignis = ereignis[:-1] + ', "cwd": "/gibt/es/nicht"}'

    assert rolle_.main(lambda: ereignis, {"TELCO_ROLLE": "bau"}) == rolle_.BLOCKIERT


@pytest.mark.parametrize(
    ("pfad", "erlaubt"),
    [
        (f"{BEREICH}kern.py", True),
        (f"{BEREICH}kern.pyc", False),
        (f"{BEREICH}nachbar.py", False),
        ("scripts/leiter.py", False),
        ("tests/test_neu.py", True),
    ],
)
def test_bau_mit_einem_modul_als_bereich_schreibt_nur_dieses_modul(repo, pfad, erlaubt):
    ziel = rolle_.Ziel("bau", f"{BEREICH}kern.py", ABNAHME)

    verstoss = rolle_.verstoss(ziel, repo, Path(pfad), neu=pfad.startswith("tests/"))

    assert (verstoss is None) is erlaubt, verstoss


@pytest.mark.parametrize("bereich", ["src/telco_radar/", "src/", "", "tests/"])
def test_bau_ohne_gueltigen_bereich_schreibt_kein_produktmodul(repo, bereich):
    ziel = rolle_.Ziel("bau", bereich, ABNAHME)

    assert rolle_.verstoss(ziel, repo, Path(f"{BEREICH}kern.py"), neu=False)
