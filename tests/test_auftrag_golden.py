"""Goldener Lauf und Basen in ``tools/auftrag.py``, am Ersatzrepo von test_auftrag."""

import json
import os
import subprocess
import sys

import pytest
from test_auftrag import AUFTRAG, ERSATZAGENT, LEITER, auftrag, repo

__all__ = ["repo"]
STREICHT = """if os.environ.get("ERSATZ_STREICHT") and sys.argv[1] != "--schnell":
    vertrag = Path(".importlinter")
    vertrag.write_text(vertrag.read_text().replace("    a.alt -> b.alt\\n", ""))
"""


def _git(ort, *argumente):
    umgebung = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    lauf = subprocess.run(
        ["git", *argumente], cwd=ort, env=umgebung, capture_output=True, text=True
    )
    assert lauf.returncode == 0, lauf.stderr
    return lauf.stdout.strip()


def _leiter_voll(ort):
    befehl = [str(ort / ".venv/bin/python"), "scripts/pruefleiter.py", "--voll"]
    subprocess.run(befehl, cwd=ort, capture_output=True, check=True)


def _ersetzt(text: str, alt: str, neu: str) -> str:
    assert text.count(alt) == 1, alt
    return text.replace(alt, neu)


LEITER_NEU = _ersetzt(
    _ersetzt(
        LEITER,
        'voll = sys.argv[1] == "--voll"\n',
        'voll = sys.argv[1] == "--voll"\nos.environ["LEITER_ART"] = sys.argv[1]\n',
    ),
    'if sys.argv[1] == "--statisch":\n',
    STREICHT + 'if sys.argv[1] == "--statisch":\n',
)
ERSATZ_NEU = _ersetzt(
    ERSATZAGENT,
    '    faktor = {"rot": 3,',
    '    if os.environ.get("ERSATZ_BAU_DATEI"):\n'
    '        name, text = json.loads(os.environ["ERSATZ_BAU_DATEI"])\n'
    "        Path(name).write_text(text)\n"
    '    faktor = {"rot": 3,',
)


def _starte(repo, modus="gut", **aenderung):
    (repo / "scripts/pruefleiter.py").write_text(LEITER_NEU)
    datei = repo.parent / "auftrag.json"
    datei.write_text(json.dumps(AUFTRAG | aenderung))
    (repo.parent / "ersatz.py").write_text(ERSATZ_NEU)
    agent = f"{sys.executable} {repo.parent / 'ersatz.py'} {modus}"
    return auftrag.main([str(datei), "--wurzel", str(repo), "--agent", agent])


def _committen(repo, dateien, titel):
    for name, text in dateien.items():
        (repo / name).parent.mkdir(parents=True, exist_ok=True)
        (repo / name).write_text(text)
    (repo / "scripts/pruefleiter.py").write_text(LEITER_NEU)
    _git(repo, "add", "--", "scripts/pruefleiter.py", *dateien)
    _git(repo, "commit", "-q", "-m", titel)
    _leiter_voll(repo)


GOLDEN = "tests/fixtures/golden/2026-10-03"
GOLDEN_SKRIPT = """import json, os, sys
from pathlib import Path
from telco_radar.rechnen.kern import verdopple
assert sys.argv[1] == "--seiten-neu"
ordner = Path(sys.argv[2])
if os.environ.get("ERSATZ_BAND"):
    (ordner / "http.jsonl.gz").write_bytes(b"anders")
alt = json.loads((ordner / "erwartet.json").read_text())
neu = {"fest.html": "1", "seite.html": str(verdopple(21))}
geaendert = sorted(k for k in alt.keys() | neu.keys() if alt.get(k) != neu.get(k))
if geaendert:
    (ordner / "erwartet.json").write_text(json.dumps(neu))
    (ordner / "_herkunft.json").write_text(json.dumps({"seiten": geaendert}))
print(json.dumps(geaendert))
"""
GOLDEN_TEST = f"""import json, os
from pathlib import Path
import pytest
from telco_radar.rechnen.kern import verdopple


def test_golden():
    if os.environ.get("LEITER_ART") != "--voll":
        pytest.skip("nur in der vollen Leiter")
    erwartet = json.loads(Path("{GOLDEN}/erwartet.json").read_text())
    assert erwartet["seite.html"] == str(verdopple(21))
"""
GOLDEN_DATEIEN = {
    "scripts/golden_aufnehmen.py": GOLDEN_SKRIPT,
    "tests/test_golden.py": GOLDEN_TEST,
    f"{GOLDEN}/erwartet.json": json.dumps({"fest.html": "1", "seite.html": "21"}),
    f"{GOLDEN}/_herkunft.json": "{}",
    f"{GOLDEN}/http.jsonl.gz": "band",
}


def _mit_golden(repo, **mehr):
    _committen(repo, GOLDEN_DATEIEN | mehr, "goldener Lauf")


def test_verhalten_schreibt_die_neuen_seiten_in_den_auftragscommit(repo):
    _mit_golden(repo)

    assert _starte(repo) == auftrag.Ende.GEMERGT

    seiten = json.loads(_git(repo, "show", f"main:{GOLDEN}/erwartet.json"))
    assert seiten == {"fest.html": "1", "seite.html": "42"}
    assert _git(repo, "show", f"main:{GOLDEN}/http.jsonl.gz") == "band"
    nachricht = _git(repo, "log", "-1", "--format=%B", "HEAD~1")
    assert nachricht.endswith("Seiten neu im goldenen Lauf:\nseite.html")
    lauf = auftrag.Lauf(repo, dict(AUFTRAG), ["agent"])
    assert lauf.datei(auftrag.golden_.PROTOKOLL).read_text() == "seite.html\n"
    assert _git(repo, "status", "--porcelain") == ""


def test_derselbe_diff_als_umbau_endet_mit_roter_leiter(repo):
    abnahme = "from telco_radar.rechnen.kern import verdopple\n\n\n"
    abnahme += "def test_verdopple():\n    assert verdopple(0) == 0\n"
    _mit_golden(repo, **{"tests/test_abnahme.py": abnahme})
    vorher = _git(repo, "rev-parse", "main")

    ende = _starte(repo, "gut", art="umbau", erwarteterFehler=None)

    assert ende == auftrag.Ende.MAIN_ROT
    notiz = (repo / auftrag.AUFTRAEGE / "A1-notiz.md").read_text()
    assert "Leiter rot auf main" in notiz
    assert _git(repo, "rev-parse", "main") == vorher
    erwartet = _git(repo, "show", f"auftrag/A1:{GOLDEN}/erwartet.json")
    assert json.loads(erwartet)["seite.html"] == "21"


def test_goldener_lauf_aendert_kein_aufnahmeband(repo, monkeypatch):
    _mit_golden(repo)
    vorher = _git(repo, "rev-parse", "main")
    monkeypatch.setenv("ERSATZ_BAND", "1")

    assert _starte(repo) == auftrag.Ende.NOTIZ

    notiz = (repo / auftrag.AUFTRAEGE / "A1-notiz.md").read_text()
    assert f"goldener Lauf änderte {GOLDEN}/http.jsonl.gz" in notiz
    assert _git(repo, "rev-parse", "main") == vorher


VERTRAG = """[importlinter]
root_packages =
    telco_radar

[importlinter:contract:a]
name = a
type = forbidden
source_modules =
    telco_radar.rechnen
forbidden_modules =
    telco_radar.sonst
ignore_imports =
    a.alt -> b.alt
    a.bleibt -> b.bleibt
"""


def _mit_basen(repo):
    basen = {
        "pruef/riesendateien.txt": "src/x.py zeilen 500\n",
        ".importlinter": VERTRAG,
    }
    _committen(repo, basen, "Basen")


def test_vom_bau_gesenkte_basis_laesst_den_auftrag_nicht_scheitern(repo, monkeypatch):
    _mit_basen(repo)
    riesen = ["pruef/riesendateien.txt", "src/x.py zeilen 450\n"]
    monkeypatch.setenv("ERSATZ_BAU_DATEI", json.dumps(riesen))

    assert _starte(repo) == auftrag.Ende.GEMERGT

    assert _git(repo, "show", "main:pruef/riesendateien.txt") == "src/x.py zeilen 500"


@pytest.mark.parametrize(
    ("datei", "befund"),
    [
        (
            ["pruef/riesendateien.txt", "src/x.py zeilen 600\n"],
            "pruef/riesendateien.txt lockerer: src/x.py zeilen von 500 auf 600",
        ),
        (
            [".importlinter", VERTRAG + "    a.neu -> b.neu\n"],
            ".importlinter lockerer: importlinter:contract:a: neue Ausnahme",
        ),
    ],
)
def test_vom_bau_gelockerte_basis_bleibt_rot(repo, monkeypatch, datei, befund):
    _mit_basen(repo)
    vorher = _git(repo, "rev-parse", "main")
    monkeypatch.setenv("ERSATZ_BAU_DATEI", json.dumps(datei))

    assert _starte(repo) == auftrag.Ende.NOTIZ

    assert befund in (repo / auftrag.AUFTRAEGE / "A1-notiz.md").read_text()
    assert _git(repo, "rev-parse", "main") == vorher


def test_von_der_leiter_gestrichene_ausnahme_kommt_auf_main(repo, monkeypatch):
    _mit_basen(repo)
    monkeypatch.setenv("ERSATZ_STREICHT", "1")

    assert _starte(repo) == auftrag.Ende.GEMERGT

    vertrag = _git(repo, "show", "main:.importlinter")
    assert "a.alt -> b.alt" not in vertrag
    assert "a.bleibt -> b.bleibt" in vertrag
    assert _git(repo, "log", "-1", "--format=%s") == "auftrag(A1): Basen der Leiter"
