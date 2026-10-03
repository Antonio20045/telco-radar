import csv
import importlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

SKRIPTE = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SKRIPTE.parent / "tools"))
auftrag = importlib.import_module("auftrag")
pruefstempel = importlib.import_module("pruefstempel")

ERWARTET = "verdopple: erwartet 4, erhalten 2"
AUFTRAG = {
    "id": "A1",
    "art": "verhalten",
    "ziel": "verdopple verdoppelt",
    "bereich": "src/telco_radar/rechnen/",
    "erwarteteDateien": ["src/telco_radar/rechnen/kern.py"],
    "vorbild": "src/telco_radar/rechnen/kern.py",
    "seite": [],
    "datenquelle": {},
    "abnahme": "tests/test_abnahme.py",
    "erwarteterFehler": ERWARTET,
    "abhaengigVon": [],
    "migration": None,
    "wasDarfNiePassieren": {
        "wiederholung": "ein zweiter Aufruf liefert dasselbe",
        "gleichzeitig": "zwei Aufrufe stören sich nicht",
        "zeitueberschreitung": "kein Aufruf wartet",
        "abbruch": "ein Abbruch schreibt nichts",
    },
}

LEITER = f"""import os, subprocess, sys
from pathlib import Path
sys.path.insert(0, {str(SKRIPTE)!r})
import pruefstempel
voll = sys.argv[1] == "--voll"
if voll and os.environ.get("ERSATZ_SPERRE"):
    import fcntl
    with open(os.environ["ERSATZ_SPERRE"], "a") as sperre:
        try:
            fcntl.flock(sperre, fcntl.LOCK_EX | fcntl.LOCK_NB)
            sys.exit(1)
        except BlockingIOError:
            pass
if voll and os.environ.get("ERSATZ_MENSCH"):
    Path("mensch.txt").write_text("vom Menschen")
    subprocess.run(["git", "add", "mensch.txt"], check=True)
    subprocess.run(["git", "commit", "-qm", "Mensch"], check=True)
if voll and os.environ.get("ERSATZ_BASIS"):
    Path("pruef").mkdir(exist_ok=True)
    Path("pruef/basis ä.txt").write_text("1\\n")
if voll and os.environ.get("ERSATZ_FREMD"):
    Path("scripts/fremd.txt").write_text("von der Leiter")
if voll and os.environ.get("ERSATZ_VOLL_ROT"):
    sys.exit(1)
befehl = [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "tests"]
code = subprocess.run(befehl).returncode
if code == 0 and sys.argv[1] == "--voll":
    pruefstempel.stempeln(Path.cwd(), pruefstempel.arbeitsbaum(Path.cwd()))
sys.exit(code)
"""

ERSATZAGENT = """import json, os, subprocess, sys
from pathlib import Path
modus, rolle = sys.argv[1], os.environ["TELCO_ROLLE"]
sys.stdin.read()
with (Path(__file__).parent / "argv.jsonl").open("a") as f:
    f.write(json.dumps([rolle, *sys.argv[2:]]) + "\\n")
if rolle == "pruefer":
    ordner, art = Path(os.environ["TELCO_PRUEFER_ORDNER"]), os.environ.get("PRUEFER")
    koerper = {"rot": "assert 2 == 3, 'Fehlwert als 0'", "gruen": "assert True"}
    koerper["import"] = "import gibt_es_nicht"
    repro = f"python -m pytest {ordner}/test_repro.py::test_repro"
    if art in koerper:
        quelle = f"def test_repro():\\n    {koerper[art]}\\n"
        (ordner / "test_repro.py").write_text(quelle)
    if art == "worktree":
        Path("src/telco_radar/rechnen/kern.py").write_text("X = 1\\n")
    befund = {"schwere": "blocker", "datei_zeile": "kern.py:2"}
    befund["beschreibung"] = "Fehlwert"
    befunde = [befund | {"reproduktion": "" if art == "ohne" else repro}] if art else []
    text = "kein JSON" if art == "kaputt" else json.dumps({"befunde": befunde})
    modelle = {"modelUsage": {"claude-opus-test": {}}}
    print(json.dumps({"result": text, "total_cost_usd": 0.5} | modelle))
    sys.exit(0)
abnahme = Path("tests/test_abnahme.py")
kern = Path("src/telco_radar/rechnen/kern.py")
soll = {"falsch": 5, "umbau": 2}.get(modus, 4)
aufruf = "verdopple(2, 1)" if modus == "typfehler" else "verdopple(2)"
if rolle == "test":
    modul = "fehlt" if modus == "importfehler" else "rechnen.kern"
    abnahme.write_text(
        f"from telco_radar.{modul} import verdopple\\n\\n\\n"
        "def test_verdopple():\\n"
        "    print('verdopple: erwartet 4, erhalten 2')\\n"
        f"    assert {aufruf} == {soll}, 'verdopple: erwartet 4, erhalten 2'\\n"
    )
    if modus == "testfremd":
        Path("tests/test_basis.py").write_text("def test_basis():\\n    pass\\n")
elif modus == "voraussetzung":
    Path(os.environ["TELCO_VORAUSSETZUNG"]).write_text("collect braucht eine Naht")
elif modus == "schummeln":
    abnahme.write_text("def test_verdopple():\\n    pass\\n")
elif modus == "fremd":
    Path("src/telco_radar/sonst.py").write_text("X = 1\\n")
elif modus == "leiter":
    Path("scripts/pruefleiter.py").write_text("raise SystemExit(0)\\n")
elif modus == "testaendern":
    Path("tests/test_basis.py").write_text("def test_basis():\\n    assert 1\\n")
else:
    if modus == "selbstcommit":
        Path("scripts/pruefleiter.py").write_text("raise SystemExit(0)\\n")
        subprocess.run(["git", "commit", "-qam", "eigener Commit"])
    if modus == "umbenennen":
        ziel = "src/telco_radar/rechnen/basis.py"
        subprocess.run(["git", "mv", "tests/test_basis.py", ziel], check=True)
    if modus == "haupt":
        haupt = Path(os.environ["TELCO_AUFTRAG"]).parents[3] / "scripts/pruefleiter.py"
        haupt.write_text(haupt.read_text() + "# vom Bauagenten\\n")
    if modus == "hauptcommit":
        haupt = Path(os.environ["TELCO_AUFTRAG"]).parents[3]
        (haupt / "scripts/pruefleiter.py").write_text("raise SystemExit(0)\\n")
        subprocess.run(["git", "-C", str(haupt), "commit", "-qam", "Agent"], check=True)
    if modus == "parallel":
        notiz = Path(os.environ["TELCO_AUFTRAG"]).parents[3] / "outputs/auftraege"
        notiz.mkdir(parents=True, exist_ok=True)
        (notiz / "B1-notiz.md").write_text("Notiz eines parallelen Auftrags")
    faktor = {"rot": 3, "umbau": 1}.get(modus, 2)
    kern.write_text(f"def verdopple(x):\\n    return x * {faktor}\\n")
    Path(os.environ["TELCO_COMMIT_NACHRICHT"]).write_text("rechnen: verdopple richtig")
    if modus == "gross":
        Path("src/telco_radar/rechnen/gross.py").write_text("X = 1\\n" * 400)
    if modus == "sammlung":
        Path("tests/orakel").mkdir(exist_ok=True)
        vorlage = Path(__file__).parent / "alles_bestanden.py"
        Path("tests/orakel/conftest.py").write_text(vorlage.read_text())
bericht = {"total_cost_usd": 0.25, "usage": {"input_tokens": 100, "output_tokens": 20}}
print(json.dumps(bericht))
sys.exit(3 if modus == "absturz" and rolle == "bau" else 0)
"""

ALLES_BESTANDEN = """import pytest


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    bericht = (yield).get_result()
    bericht.outcome = "passed"
"""

DATEIEN = {
    ".gitignore": ".venv/\n__pycache__/\n",
    "Makefile": "venv:\n\tmkdir -p .venv/bin\n"
    f"\tprintf '#!/bin/sh\\nexec {sys.executable} \"$$@\"\\n' > .venv/bin/python\n"
    "\tchmod +x .venv/bin/python\n",
    "pyproject.toml": '[tool.pytest.ini_options]\npythonpath = ["src"]\n',
    "scripts/pruefstempel.py": '"""Platzhalter, nur die Einführung zählt."""\n',
    "scripts/pruefleiter.py": LEITER,
    "src/telco_radar/__init__.py": "",
    "src/telco_radar/rechnen/__init__.py": "",
    "src/telco_radar/rechnen/kern.py": "def verdopple(x):\n    return x\n",
    "tests/test_basis.py": "def test_basis():\n    assert True\n",
}


def _git(ort, *argumente):
    umgebung = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    return subprocess.run(
        ["git", *argumente],
        cwd=ort,
        env=umgebung,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()


def _leiter_voll(ort, check=True):
    befehl = [str(ort / ".venv/bin/python"), "scripts/pruefleiter.py", "--voll"]
    subprocess.run(befehl, cwd=ort, capture_output=True, check=check)


@pytest.fixture
def repo(tmp_path):
    wurzel = tmp_path / "repo"
    for name, text in DATEIEN.items():
        (wurzel / name).parent.mkdir(parents=True, exist_ok=True)
        (wurzel / name).write_text(text)
    _git(tmp_path, "init", "-q", "--bare", "-b", "main", "origin.git")
    _git(wurzel, "init", "-q", "-b", "main")
    _git(wurzel, "config", "user.name", "Mensch")
    _git(wurzel, "config", "user.email", "m@example.invalid")
    _git(wurzel, "add", "--", *DATEIEN)
    _git(wurzel, "commit", "-q", "-m", "Start")
    _git(wurzel, "remote", "add", "origin", str(tmp_path / "origin.git"))
    _git(wurzel, "push", "-q", "origin", "main")
    _git(wurzel, "fetch", "-q", "origin")
    subprocess.run(["make", "venv"], cwd=wurzel, capture_output=True, check=True)
    _leiter_voll(wurzel)
    return wurzel


def _starte(repo, modus="gut", **aenderung):
    datei = repo.parent / "auftrag.json"
    datei.write_text(json.dumps(AUFTRAG | aenderung))
    agent = f"{sys.executable} {repo.parent / 'ersatz.py'} {modus}"
    (repo.parent / "ersatz.py").write_text(ERSATZAGENT)
    (repo.parent / "alles_bestanden.py").write_text(ALLES_BESTANDEN)
    return auftrag.main([str(datei), "--wurzel", str(repo), "--agent", agent])


def _kosten(ort):
    with (ort / auftrag.KOSTEN).open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


def test_ersatzagent_laeuft_vom_roten_test_bis_zum_merge(repo):
    vorher = _git(repo, "rev-parse", "HEAD")

    assert _starte(repo) == auftrag.Ende.GEMERGT

    log = _git(repo, "log", "--format=%B%x00", f"{vorher}..main").split("\x00")
    log = [eintrag.strip() for eintrag in log]
    assert log[1].startswith("rechnen: verdopple richtig")
    assert ERWARTET in log[1], "der Commit belegt den roten Abnahmetest"
    assert log[0] == "auftrag(A1): Kosten"
    assert "x * 2" in (repo / "src/telco_radar/rechnen/kern.py").read_text()
    assert (repo / "tests/test_abnahme.py").is_file()
    assert not (repo.parent / "telco-radar-wt/A1").exists()
    assert _git(repo, "branch", "--list", "auftrag/*") == ""
    baum = _git(repo, "rev-parse", "HEAD^{tree}")
    assert pruefstempel.ist_gestempelt(repo, baum), "die Leiter lief auf main"
    zeilen = _kosten(repo)
    assert [(z["rolle"], z["runde"]) for z in zeilen] == [
        ("test", "1"),
        ("bau", "1"),
        ("pruefer", "1"),
        ("ende", "0"),
    ]
    assert zeilen[1]["kosten_usd"] == "0.25" and zeilen[1]["token_ein"] == "100"
    assert zeilen[-1]["ergebnis"] == auftrag.GEMERGT
    assert _git(repo, "status", "--porcelain") == ""


@pytest.mark.parametrize("fall", [None, *AUFTRAG["wasDarfNiePassieren"]])
def test_ohne_was_darf_nie_passieren_startet_kein_auftrag(repo, fall, capsys):
    nie = dict(AUFTRAG["wasDarfNiePassieren"])
    if fall is None:
        nie = None
    else:
        nie[fall] = " "

    assert _starte(repo, wasDarfNiePassieren=nie) == auftrag.Ende.NICHT_GESTARTET

    assert "wasDarfNiePassieren" in capsys.readouterr().out
    assert not (repo.parent / "telco-radar-wt").exists()
    assert _git(repo, "branch", "--list", "auftrag/*") == ""


@pytest.mark.parametrize("ref", ["main", "origin/main"])
def test_ungestempelter_commit_sperrt_den_start(repo, ref, capsys):
    (repo / "tests/test_basis.py").write_text("def test_basis():\n    assert 1\n")
    _git(repo, "commit", "-q", "-am", "ohne Leiter")
    if ref == "origin/main":
        _git(repo, "push", "-q", "origin", "main")
        _git(repo, "fetch", "-q", "origin")
        _git(repo, "reset", "-q", "--keep", "HEAD~1")

    assert _starte(repo) == auftrag.Ende.NICHT_GESTARTET

    assert f"1 ungestempelte Commits auf {ref} " in capsys.readouterr().out
    assert not (repo.parent / "telco-radar-wt").exists()


@pytest.mark.parametrize(
    ("vorbereitung", "grund"),
    [
        (("switch", "-q", "-c", "neben"), "Hauptarbeitsbaum steht nicht auf main"),
        (("branch", "auftrag/A1"), "Auftrag A1 hat schon Worktree oder Zweig"),
    ],
)
def test_falscher_zustand_des_repos_sperrt_den_start(repo, vorbereitung, grund, capsys):
    _git(repo, *vorbereitung)

    assert _starte(repo) == auftrag.Ende.NICHT_GESTARTET

    assert grund in capsys.readouterr().out


@pytest.mark.langsam
def test_nach_einer_notiz_startet_erst_wieder_ein_sauberer_hauptarbeitsbaum(
    repo, capsys
):
    assert _starte(repo, "rot") == auftrag.Ende.NOTIZ
    _git(repo, "worktree", "remove", "--force", str(repo.parent / "telco-radar-wt/A1"))
    _git(repo, "branch", "-D", "auftrag/A1")

    assert _starte(repo) == auftrag.Ende.NICHT_GESTARTET
    assert "Hauptarbeitsbaum nicht sauber" in capsys.readouterr().out

    _git(repo, "add", "--", auftrag.AUFTRAEGE)
    _git(repo, "commit", "-q", "-m", "Notiz A1")
    _leiter_voll(repo)
    assert _starte(repo) == auftrag.Ende.GEMERGT
    ergebnisse = [z["ergebnis"] for z in _kosten(repo) if z["rolle"] == "ende"]
    assert ergebnisse == ["notiz", "gemergt"]


def test_testagent_darf_bestehende_tests_nicht_aendern(repo):
    assert _starte(repo, "testfremd") == auftrag.Ende.NOTIZ

    notiz = (repo / auftrag.AUFTRAEGE / "A1-notiz.md").read_text()
    assert "Rolle test darf nicht ändern: tests/test_basis.py" in notiz


def test_umbau_bleibt_gruen_vom_test_bis_zum_merge(repo):
    umbau = {"art": "umbau", "erwarteterFehler": None}

    assert _starte(repo, "umbau", **umbau) == auftrag.Ende.GEMERGT

    assert "x * 1" in (repo / "src/telco_radar/rechnen/kern.py").read_text()
    assert "vor dem Bau rot" not in _git(repo, "log", "-1", "--format=%B", "HEAD~1")


def test_vorhandener_roter_abnahmetest_braucht_keinen_testagenten(repo):
    (repo / "tests/test_abnahme.py").write_text(
        "from telco_radar.rechnen.kern import verdopple\n\n\n"
        "def test_verdopple():\n"
        f"    assert verdopple(2) == 4, {ERWARTET!r}\n"
    )
    _git(repo, "add", "--", "tests/test_abnahme.py")
    _git(repo, "commit", "-q", "-m", "roter Abnahmetest")
    _leiter_voll(repo, check=False)
    pruefstempel.stempeln(repo, _git(repo, "rev-parse", "HEAD^{tree}"))

    assert _starte(repo) == auftrag.Ende.GEMERGT

    assert [z["rolle"] for z in _kosten(repo)] == ["bau", "pruefer", "ende"]


def test_zwei_rote_runden_enden_mit_notiz(repo):
    vorher = _git(repo, "rev-parse", "main")

    assert _starte(repo, "rot") == auftrag.Ende.NOTIZ

    notiz = (repo / auftrag.AUFTRAEGE / "A1-notiz.md").read_text()
    assert notiz.count("## Befund") == 2
    assert "Abnahmetest rot" in notiz
    assert _git(repo, "rev-parse", "main") == vorher
    assert [z["rolle"] for z in _kosten(repo)] == ["test", "bau", "bau", "ende"]
    assert _kosten(repo)[-1]["ergebnis"] == "notiz"


def test_fehlende_voraussetzung_endet_ohne_rote_runde(repo):
    assert _starte(repo, "voraussetzung") == auftrag.Ende.VORAUSSETZUNG

    notiz = (repo / auftrag.AUFTRAEGE / "A1-notiz.md").read_text()
    assert "collect braucht eine Naht" in notiz
    assert [z["rolle"] for z in _kosten(repo)] == ["test", "bau", "ende"]


@pytest.mark.parametrize(
    ("modus", "befund"),
    [
        ("schummeln", "Abnahmetest geändert oder gelöscht"),
        ("fremd", "Rolle bau darf nicht ändern: src/telco_radar/sonst.py"),
        ("leiter", "Rolle bau darf nicht ändern: scripts/pruefleiter.py"),
        ("gross", "401 Zeilen Produktcode, höchstens 400"),
        ("absturz", "Agent Exit 3"),
    ],
)
def test_bau_ausserhalb_der_regeln_ist_eine_rote_runde(repo, modus, befund):
    assert _starte(repo, modus) == auftrag.Ende.NOTIZ

    assert befund in (repo / auftrag.AUFTRAEGE / "A1-notiz.md").read_text()


@pytest.mark.parametrize(
    ("modus", "exit", "erwartet"),
    [
        ("importfehler", 2, ERWARTET),
        ("falsch", 1, "erwartet 4, erhalten 3"),
        ("typfehler", 1, ERWARTET),
    ],
)
def test_abnahmetest_ohne_den_erwarteten_fehler_geht_an_den_testagenten_zurueck(
    repo, modus, exit, erwartet
):
    assert _starte(repo, modus, erwarteterFehler=erwartet) == auftrag.Ende.NOTIZ

    notiz = (repo / auftrag.AUFTRAEGE / "A1-notiz.md").read_text()
    assert f"nicht rot mit „{erwartet}“ (Exit {exit})" in notiz
    assert [z["rolle"] for z in _kosten(repo)] == ["test", "test", "ende"]


def test_rote_leiter_auf_main_setzt_main_zurueck(repo, monkeypatch):
    vorher = _git(repo, "rev-parse", "main")
    monkeypatch.setenv("ERSATZ_VOLL_ROT", "1")

    assert _starte(repo) == auftrag.Ende.MAIN_ROT

    assert _git(repo, "rev-parse", "main") == vorher
    assert _git(repo, "rev-parse", "auftrag/A1") != vorher, "die Arbeit bleibt im Zweig"


def test_hoechstens_zwei_auftraege_und_kein_gleicher_bereich(repo, capsys):
    for kennung in ("B1", "B2"):
        ziel = repo.parent / "telco-radar-wt" / kennung
        _git(repo, "worktree", "add", "-q", "-b", f"auftrag/{kennung}", str(ziel))
    lauf = auftrag.Lauf(repo, dict(AUFTRAG), ["agent"])
    lauf.datei("").parent.joinpath("B1").mkdir(parents=True)
    lauf.datei("").parent.joinpath("B1/auftrag.json").write_text(json.dumps(AUFTRAG))

    gruende = auftrag.sperren(lauf)

    assert "schon 2 Aufträge in Arbeit, höchstens 2" in gruende
    assert "Bereich überschneidet sich mit Auftrag B1" in gruende


@pytest.mark.parametrize(
    ("aenderung", "fehler"),
    [
        ({"art": "umbau"}, "erwarteterFehler bei art umbau"),
        ({"erwarteterFehler": ""}, "erwarteterFehler fehlt"),
        ({"bereich": "tests/"}, "bereich ist kein Unterordner"),
        ({"bereich": "src/telco_radar/gibtsnicht/"}, "bereich ist kein Unterordner"),
        ({"bereich": "src/telco_radar/"}, "bereich ist kein Unterordner"),
        ({"bereich": "src/telco_radar/rechnen"}, "bereich ist kein Unterordner"),
        (
            {"wasDarfNiePassieren": AUFTRAG["wasDarfNiePassieren"] | {"abbruch": 1}},
            "wasDarfNiePassieren.abbruch fehlt",
        ),
        ({"abnahme": "src/test_x.py"}, "abnahme ist keine Datei"),
        ({"id": "../x"}, "id nur aus"),
        ({"abhaengigVon": ["T0"]}, "abhaengigVon T0 ist nicht gemergt"),
        ({"ziel": None}, "Feld ziel fehlt"),
    ],
)
def test_formatfehler_nennt_jeden_verstoss(repo, aenderung, fehler):
    gruende = auftrag.format_.formatfehler(AUFTRAG | aenderung, repo)

    assert any(g.startswith(fehler) for g in gruende), gruende


def test_formatfehler_akzeptiert_einen_vollstaendigen_auftrag(repo):
    assert auftrag.format_.formatfehler(AUFTRAG, repo) == []
    umbau = AUFTRAG | {"art": "umbau", "erwarteterFehler": None}
    assert auftrag.format_.formatfehler(umbau, repo) == []


def test_stand_schritt_6_verlangt_einen_echten_agenten_bis_zum_merge(
    tmp_path, monkeypatch
):
    stand = importlib.import_module("stand")
    monkeypatch.setattr(stand, "W", tmp_path)
    assert stand.echter_auftrag() == [f"{auftrag.KOSTEN} fehlt"]
    leer = ["kein Auftrag, dessen Bau und Prüfer ein Claude-Modell bis zum Merge waren"]

    def zeile(kennung, rolle, agent="claude", modell="claude-opus-x", kosten="0.4"):
        werte = {"auftrag": kennung, "rolle": rolle, "agent": agent, "modell": modell}
        werte |= {"kosten_usd": kosten, "ergebnis": auftrag.GEMERGT * (rolle == "ende")}
        return dict.fromkeys(auftrag.format_.SPALTEN, "") | werte

    falsch = {
        "E1": {"agent": "python3"},
        "E2": {"modell": ""},
        "E3": {"modell": "ersatz"},
        "E4": {"kosten": ""},
        "E5": {"kosten": "0"},
    }
    for kennung, abweichung in falsch.items():
        zeilen = [zeile(kennung, "bau", **abweichung), zeile(kennung, "pruefer")]
        auftrag.format_.kosten_schreiben([*zeilen, zeile(kennung, "ende")], tmp_path)
    ohne_pruefer = [zeile("E6", "test"), zeile("E6", "bau"), zeile("E6", "ende")]
    auftrag.format_.kosten_schreiben(ohne_pruefer, tmp_path)
    nicht_gemergt = [zeile("E7", "bau"), zeile("E7", "pruefer")]
    auftrag.format_.kosten_schreiben(nicht_gemergt, tmp_path)
    assert stand.echter_auftrag() == leer
    assert auftrag.format_.echte_auftraege(tmp_path) == set()

    echt = [zeile("E8", "bau"), zeile("E8", "pruefer"), zeile("E8", "ende")]
    auftrag.format_.kosten_schreiben(echt, tmp_path)
    assert stand.echter_auftrag() == []
    assert auftrag.format_.echte_auftraege(tmp_path) == {"E8"}


def test_agent_startet_mit_rollendatei_und_rolleneinstellungen(repo):
    assert _starte(repo) == auftrag.Ende.GEMERGT

    aufrufe = [
        json.loads(z) for z in (repo.parent / "argv.jsonl").read_text().splitlines()
    ]
    assert [a[0] for a in aufrufe] == ["test", "bau", "pruefer"]
    for rolle, *argumente in aufrufe:
        assert argumente[:3] == ["--agent", rolle, "--settings"]
        einstellungen = json.loads(argumente[3])
        assert einstellungen["env"] == {"TELCO_ROLLE": rolle}
        haken = einstellungen["hooks"]["PreToolUse"][0]
        assert {"Bash", "Edit", "Write"} <= set(haken["matcher"].split("|"))
        assert "scripts/claude_rolle.py" in haken["hooks"][0]["command"]
        assert "Bash(git commit*)" in einstellungen["permissions"]["deny"]
    pruefer = [z for z in _kosten(repo) if z["rolle"] == "pruefer"]
    assert pruefer[0]["modell"] == "claude-opus-test"
    assert pruefer[0]["kosten_usd"] == "0.5"


@pytest.mark.parametrize(
    ("modus", "fremd"),
    [
        ("sammlung", "tests/orakel/conftest.py"),
        ("testaendern", "tests/test_basis.py"),
    ],
)
def test_bau_kann_bestehende_tests_und_die_sammlung_nicht_aendern(repo, modus, fremd):
    vorher = _git(repo, "rev-parse", "main")

    assert _starte(repo, modus) == auftrag.Ende.NOTIZ

    notiz = (repo / auftrag.AUFTRAEGE / "A1-notiz.md").read_text()
    assert f"Rolle bau darf nicht ändern: {fremd}" in notiz
    assert _git(repo, "rev-parse", "main") == vorher


@pytest.mark.parametrize(
    ("art", "ende", "rollen"),
    [
        ("rot", auftrag.Ende.NOTIZ, ["test", "bau", "pruefer", "bau", "pruefer"]),
        ("gruen", auftrag.Ende.GEMERGT, ["test", "bau", "pruefer"]),
        ("import", auftrag.Ende.GEMERGT, ["test", "bau", "pruefer"]),
        ("ohne", auftrag.Ende.GEMERGT, ["test", "bau", "pruefer"]),
        ("kaputt", auftrag.Ende.NOTIZ, ["test", "bau", "pruefer", "bau", "pruefer"]),
        ("worktree", auftrag.Ende.NOTIZ, ["test", "bau", "pruefer", "bau", "pruefer"]),
    ],
)
def test_prueferbefund_zaehlt_nur_mit_scheiternder_reproduktion(
    repo, monkeypatch, art, ende, rollen
):
    monkeypatch.setenv("PRUEFER", art)

    assert _starte(repo) == ende

    assert [z["rolle"] for z in _kosten(repo)][:-1] == rollen
    if ende is auftrag.Ende.GEMERGT:
        return
    notiz = (repo / auftrag.AUFTRAEGE / "A1-notiz.md").read_text()
    erwartet = {
        "rot": "Prüfer: 1 Blocker mit scheiternder Reproduktion",
        "kaputt": "Prüfer ohne lesbares Urteil: kein JSON",
        "worktree": "Prüfer hat den Worktree geändert",
    }[art]
    assert erwartet in notiz


@pytest.mark.parametrize(
    ("modus", "befund"),
    [
        ("selbstcommit", "scripts/pruefleiter.py"),
        ("selbstcommit", "HEAD"),
        ("umbenennen", "Rolle bau darf nicht ändern: tests/test_basis.py"),
    ],
)
def test_eigener_commit_oder_umbenennung_versteckt_nichts(repo, modus, befund):
    leiter = (repo / "scripts/pruefleiter.py").read_text()

    assert _starte(repo, modus) == auftrag.Ende.NOTIZ

    assert befund in (repo / auftrag.AUFTRAEGE / "A1-notiz.md").read_text()
    assert _git(repo, "show", "main:scripts/pruefleiter.py") + "\n" == leiter
    assert _git(repo, "ls-tree", "main", "tests/test_basis.py")


@pytest.mark.parametrize(
    ("modus", "befund"),
    [
        (
            "haupt",
            "Hauptbaum vor dem Merge verändert: scripts/pruefleiter.py",
        ),
        ("hauptcommit", "ungestempelte Commits auf main"),
    ],
)
def test_bauagent_im_hauptbaum_kommt_nicht_auf_main(repo, modus, befund):
    assert _starte(repo, modus) == auftrag.Ende.ABGEBROCHEN

    assert befund in (repo / auftrag.AUFTRAEGE / "A1-notiz.md").read_text()
    assert "x * 2" not in _git(repo, "show", "main:src/telco_radar/rechnen/kern.py")


def test_notiz_eines_parallelen_auftrags_haelt_den_merge_nicht_auf(repo):
    assert _starte(repo, "parallel") == auftrag.Ende.GEMERGT

    assert (repo / auftrag.AUFTRAEGE / "B1-notiz.md").is_file()
    assert _git(repo, "ls-tree", "main", "outputs/auftraege/B1-notiz.md") == ""


def test_leiter_aendert_ausserhalb_der_basen_setzt_main_zurueck(repo, monkeypatch):
    vorher = _git(repo, "rev-parse", "main")
    monkeypatch.setenv("ERSATZ_FREMD", "1")

    assert _starte(repo) == auftrag.Ende.MAIN_ROT

    assert _git(repo, "rev-parse", "main") == vorher
    notiz = (repo / auftrag.AUFTRAEGE / "A1-notiz.md").read_text()
    assert "Leiter änderte scripts/fremd.txt" in notiz


def test_basen_der_leiter_kommen_mit_jedem_namen_auf_main(repo, monkeypatch):
    (repo / "pruef").mkdir()
    (repo / "pruef/basis ä.txt").write_text("2\n")
    _git(repo, "add", "--", "pruef")
    _git(repo, "commit", "-q", "-m", "Basis")
    _leiter_voll(repo)
    monkeypatch.setenv("ERSATZ_BASIS", "1")

    assert _starte(repo) == auftrag.Ende.GEMERGT

    zeigen = ("-c", "core.quotePath=false", "show", "--name-only", "--format=%s")
    assert _git(repo, *zeigen, "main") == (
        "auftrag(A1): Basen der Leiter\n\npruef/basis ä.txt"
    )
    assert _git(repo, "status", "--porcelain") == ""


def test_rote_leiter_laesst_einen_commit_des_menschen_stehen(repo, monkeypatch):
    monkeypatch.setenv("ERSATZ_VOLL_ROT", "1")
    monkeypatch.setenv("ERSATZ_MENSCH", "1")

    assert _starte(repo) == auftrag.Ende.MAIN_ROT

    assert _git(repo, "log", "-1", "--format=%s", "main") == "Mensch"
    notiz = (repo / auftrag.AUFTRAEGE / "A1-notiz.md").read_text()
    assert "nicht zurückgesetzt" in notiz


def test_merge_und_leiter_laufen_unter_einer_sperre(repo, monkeypatch):
    sperre = repo / ".git" / "auftraege" / "main.sperre"
    monkeypatch.setenv("ERSATZ_SPERRE", str(sperre))

    assert _starte(repo) == auftrag.Ende.GEMERGT
