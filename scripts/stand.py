"""Meldet je Umbauschritt „erfüllt“ oder „offen, weil …“ und die Summe je Basis.

Schritt 2 und 3 messen ihr Fertig-Kriterium aus ``docs/umbau/plan.md`` in einem
Wegwerf-Worktree auf ``HEAD``: kaputter Zeitreihen-Render, Live-Datum, Rot-Proben.
"""

import ast
import contextlib
import csv
import importlib
import json
import os
import re
import shutil
import statistics
import subprocess
import sys
import tempfile
from collections.abc import Iterator
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import claude_rolle
import pruefstempel
import waechter
import waechter_claude
import waechter_kommentare
import waechter_regeln
import waechter_tests

W = waechter.WURZEL
sys.path.insert(0, str(W / "tools"))
auftrag_format = importlib.import_module("auftrag_format")
MUTATION_ENTFAELLT = "entfällt: "
MUTATION_ERKANNT = re.compile(r"\d+ von \d+ Mutanten erkannt")
ROLLENDATEIEN = tuple(f".claude/agents/{r}.md" for r in ("test", "bau", "pruefer"))
LIVE_SEITE = "https://telco-radar.onrender.com/geraete.html"
LIVE_FRIST_SEKUNDEN = 20
LIVE_TAGE_ALT = 1
TESTZEIT_ZIEL = 240
VORCOMMIT_ZIEL = 5
VORCOMMIT_LAEUFE = 20
HOOKS = ".githooks"
BLOCKIERT = 2
_DOC = '"""Rotprobe."""\n\n'
ROT_PROBEN = {
    "unbenutzter Import": (
        "src/telco_radar/rotprobe.py",
        _DOC + "import os\n",
        ("Stufe 1 Lint", "[F401]"),
    ),
    "neuer mypy-Fehler": (
        "src/telco_radar/rotprobe.py",
        _DOC + '\ndef f() -> int:\n    """Zahl."""\n    return "x"\n',
        ("Stufe 2 Typen", "[return-value]"),
    ),
    "collect in report": (
        "src/telco_radar/report/rotprobe.py",
        _DOC + "from telco_radar.collect import http\n\nNETZ = http\n",
        ("Stufe 3 Schichten",),
    ),
    "neue Datei mit 401 Zeilen": (
        "scripts/rotprobe.py",
        _DOC + "x = 1\n" * 399,
        ("Stufe 0 Wächter", "scripts/rotprobe.py [zeilen]"),
    ),
}
ZEITREIHEN_PROBE = """
from pathlib import Path
from telco_radar.report import bauen, geraete_zeitreihe
from telco_radar.report.geraete_view import ZEITREIHE_TEIL

def _wirft(*_a, **_k):
    raise ValueError("Rotprobe")

geraete_zeitreihe.aufbereiten = _wirft
code = bauen.main(["--root", "."])
seite = Path("site/geraete.html").read_text("utf-8")
print("EXIT", code, "AUSFALL", "Nicht neu gebaut" in seite and ZEITREIHE_TEIL in seite)
"""


def _zeilen(datei: str, funktion: str = "") -> int:
    text = (W / datei).read_text("utf-8") if (W / datei).is_file() else ""
    if not funktion:
        return text.count("\n")
    knoten = [k for k in ast.walk(ast.parse(text)) if getattr(k, "name", 0) == funktion]
    return sum(k.end_lineno - k.lineno + 1 for k in knoten)


def _ausnahmen(vertrag: str) -> int:
    teil = (W / ".importlinter").read_text("utf-8").split(f":{vertrag}]")[1]
    return teil.split("\n[")[0].partition("ignore_imports")[2].count("->")


def _mehr(was: str, wert: int, ziel: int = 0) -> list[str]:
    return [f"{was} {wert}, Ziel {ziel}"] if wert > ziel else []


def _tests_summe() -> dict[str, int]:
    basis = waechter.lies_zaehlbasis(W / waechter_tests.TESTS_BASIS)
    return {c: sum(n for (_, k), n in basis.items() if k == c) for _, c in basis}


def _testzeit() -> list[str]:
    """Hält die letzte Teststufe aus ``.pruefleiter/zeiten.csv`` gegen das Zeitziel."""
    datei = W / ".pruefleiter" / "zeiten.csv"
    zeilen = datei.read_text("utf-8").splitlines() if datei.is_file() else []
    stufen = (["Tests"], ["5 Voll"])
    tests = [z.split(",") for z in zeilen if z.split(",")[1:2] in stufen]
    if not tests:
        return ["keine Teststufe in .pruefleiter/zeiten.csv"]
    return _mehr(
        "Sekunden der letzten Teststufe", round(float(tests[-1][2])), TESTZEIT_ZIEL
    )


def _vorcommit_median() -> list[str]:
    """Hält den Median der letzten grünen pre-commit-Läufe gegen ``VORCOMMIT_ZIEL``.

    Rote Läufe brechen früh ab und würden den Median schönen.
    """
    datei = W / ".pruefleiter" / "zeiten.csv"
    zeilen = datei.read_text("utf-8").splitlines() if datei.is_file() else []
    laeufe = [z.split(",") for z in zeilen]
    sekunden = [
        float(z[2]) for z in laeufe if z[1:2] == ["--pre-commit"] and z[3:] == ["gruen"]
    ]
    if not sekunden:
        return ["kein grüner pre-commit-Lauf in .pruefleiter/zeiten.csv"]
    median = statistics.median(sekunden[-VORCOMMIT_LAEUFE:])
    if median < VORCOMMIT_ZIEL:
        return []
    return [f"pre-commit im Median {median:.1f} s, Ziel unter {VORCOMMIT_ZIEL} s"]


def _hooks() -> list[str]:
    """Die Git-Hooks liegen in ``.githooks`` und sind eingerichtet."""
    lauf = subprocess.run(
        ["git", "config", "core.hooksPath"], cwd=W, capture_output=True, text=True
    )
    gruende = _fehlt(f"{HOOKS}/pre-commit", f"{HOOKS}/pre-push")
    if lauf.stdout.strip() != HOOKS:
        gruende.append(f"core.hooksPath ist nicht {HOOKS} (make einrichten)")
    return gruende


def freie_kommentare() -> int:
    """Zählt die ``#``-Kommentare, die Stufe 0 als ``kommentar`` meldet."""
    return sum(
        len(waechter_kommentare.freie_kommentare((W / p).read_text(encoding="utf-8")))
        for p in waechter_regeln.kommentar_dateien(W)
    )


def ungepruefte() -> list[str]:
    """Nennt Commits auf ``origin/main`` seit dem jüngsten Prüfstempel."""
    try:
        befund = pruefstempel.ungestempelte(W)
    except pruefstempel.StempelFehler as fehler:
        return [f"Prüfstempel nicht lesbar ({fehler})"]
    if not befund.commits:
        return []
    anzahl = len(befund.commits)
    kurz = ", ".join(c[:7] for c in befund.commits[:10])
    mehr = f" und {anzahl - 10} weitere" if anzahl > 10 else ""
    ohne = "" if befund.stempel_gefunden else ", kein Stempel in diesem Klon"
    return [f"{anzahl} ungeprüfte Commits ({kurz}{mehr}{ohne})"]


def echter_auftrag() -> list[str]:
    """Verlangt einen Auftrag, den ein echter Agent bis zum Merge brachte."""
    datei = W / auftrag_format.KOSTEN
    if not datei.is_file():
        return [f"{auftrag_format.KOSTEN} fehlt"]
    if auftrag_format.echte_auftraege(W):
        return []
    return ["kein Auftrag, dessen Bau und Prüfer ein Claude-Modell bis zum Merge waren"]


def promo_ids() -> list[str]:
    """Verlangt den gemergten Auftrag T1 samt seiner Abnahme auf ``main``."""
    datei = W / auftrag_format.AUFTRAEGE / "T1.json"
    if not datei.is_file():
        return [f"{auftrag_format.AUFTRAEGE}/T1.json fehlt"]
    abnahme = json.loads(datei.read_text("utf-8"))["abnahme"]
    gemergt = "T1" in auftrag_format.gemergt(W)
    return _fehlt(abnahme) + ["Auftrag T1 nicht gemergt"] * (not gemergt)


def mutationsprobe() -> list[str]:
    """Verlangt zu einem echten Auftrag eine Mutationsprobe mit Zeit oder Grund."""
    datei = W / auftrag_format.KOSTEN
    if datei.is_file():
        echte = auftrag_format.echte_auftraege(W)
        with datei.open(encoding="utf-8") as f:
            zeilen = [z for z in csv.DictReader(f) if z["auftrag"] in echte]
        if any(z["rolle"] == "mutation" and _probe_belegt(z) for z in zeilen):
            return []
    return ["keine Mutationsprobe mit Zeit oder Grund zu einem echten Auftrag"]


def _probe_belegt(zeile: dict[str, str]) -> bool:
    ergebnis = zeile.get("ergebnis") or ""
    if ergebnis.startswith(MUTATION_ENTFAELLT):
        return len(ergebnis) > len(MUTATION_ENTFAELLT)
    try:
        sekunden = float(zeile.get("sekunden") or "")
    except ValueError:
        return False
    return sekunden > 0 and MUTATION_ERKANNT.match(ergebnis) is not None


def rollen_sperren() -> list[str]:
    """Probt den Rollen-Hook: ``bau`` darf einen bestehenden Test nicht ändern."""
    ziel = claude_rolle.Ziel("bau", "src/telco_radar/analyze/", "tests/test_neu.py")
    test = W / "tests/test_auftrag.py"
    befehle = (f"echo x >> {test}", f"nice sed -i s/a/b/ {test}", "env git stash")
    gruende = [("Edit", claude_rolle.verstoss(ziel, W, test, neu=False))]
    gruende += [
        ("Bash", claude_rolle.befehl_verstoss(ziel, W, W, b, _alt)) for b in befehle
    ]
    return [f"Rolle bau ändert per {w} einen Test" for w, g in gruende if not g]


def _alt(_wurzel: Path, _pfad: Path) -> bool:
    return False


def _fehlt(*pfade: str) -> list[str]:
    return [f"{p} fehlt" for p in pfade if not (W / p).exists()]


@contextlib.contextmanager
def _wegwerf_baum() -> Iterator[Path]:
    with tempfile.TemporaryDirectory() as ordner:
        baum = Path(ordner) / "baum"
        git = ["git", "worktree"]
        subprocess.run([*git, "add", "-q", "--detach", baum, "HEAD"], cwd=W, check=True)
        try:
            if (W / ".mypy_cache").is_dir():
                shutil.copytree(W / ".mypy_cache", baum / ".mypy_cache")
            yield baum
        finally:
            subprocess.run([*git, "remove", "--force", baum], cwd=W, check=False)


def _python(baum: Path, *argumente: str) -> subprocess.CompletedProcess[str]:
    umgebung = {**os.environ, "PYTHONPATH": "src"}
    befehl = [sys.executable, *argumente]
    return subprocess.run(
        befehl, cwd=baum, env=umgebung, capture_output=True, text=True
    )


def rot_proben() -> list[str]:
    """Schritt 3: Leiter 0–3 grün auf HEAD und jede Rot-Probe rot in ihrer Stufe."""
    with _wegwerf_baum() as baum:
        leiter = ("scripts/pruefleiter.py", "--statisch")
        if _python(baum, *leiter).returncode != 0:
            return ["Leiter Stufen 0–3 auf HEAD nicht grün"]
        gruende = []
        for name, (pfad, text, erwartet) in ROT_PROBEN.items():
            (baum / pfad).write_text(text, encoding="utf-8")
            lauf = _python(baum, *leiter)
            if lauf.returncode != 1 or not all(e in lauf.stdout for e in erwartet):
                gruende.append(f"Rot-Probe „{name}“ nicht rot in {erwartet[0]}")
            (baum / pfad).unlink()
        return gruende


def _hook(
    baum: Path, ereignis: dict, *argumente: str
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, *argumente],
        cwd=baum,
        input=json.dumps(ereignis),
        capture_output=True,
        text=True,
        check=False,
    )


def hook_proben() -> list[str]:
    """Schritt 5: Claude-Hooks sperren ``--no-verify`` und ganze große Dateien,
    und ein Stop mit rotem Lint lässt die Sitzung weiterlaufen."""
    hook = "scripts/claude_hooks.py"
    gruende = []
    befehl = {"tool_input": {"command": "git commit --no-verify -m probe"}}
    if _hook(W, befehl, hook, "befehl").returncode != BLOCKIERT:
        gruende.append("--no-verify nicht gesperrt")
    lesen = {"tool_input": {"file_path": str(W / "src/telco_radar/report/html.py")}}
    if _hook(W, lesen, hook, "datei_lesen").returncode != BLOCKIERT:
        gruende.append("Read von html.py ohne limit nicht gesperrt")
    pfad, text, (_, befund) = ROT_PROBEN["unbenutzter Import"]
    with _wegwerf_baum() as baum:
        (baum / pfad).write_text(text, encoding="utf-8")
        (baum / ".venv").symlink_to(W / ".venv")
        stop = {"session_id": "stand-probe", "hook_event_name": "Stop"}
        lauf = _hook(baum, stop, hook, "stop")
    if lauf.returncode != BLOCKIERT or befund not in lauf.stderr:
        gruende.append("Stop mit rotem Lint lässt die Sitzung enden")
    return gruende


def zeitreihen_probe() -> list[str]:
    """Schritt 2: kaputte Zeitreihe gibt Exit ≠ 0, und die Seite nennt den Ausfall."""
    with _wegwerf_baum() as baum:
        lauf = _python(baum, "-c", ZEITREIHEN_PROBE)
    zeile = (lauf.stdout.splitlines() or [""])[-1]
    if not zeile.startswith("EXIT ") or zeile.startswith("EXIT 0 "):
        return ["kaputte Zeitreihe endet nicht rot"]
    return [] if zeile.endswith("AUSFALL True") else ["Seite nennt den Ausfall nicht"]


def live_datum(heute: date | None = None) -> list[str]:
    """Schritt 2: die Live-Geräteseite trägt das Datum des letzten Tageslaufs.

    ``heute`` ist der Bezugstag; ohne Angabe der heutige Tag in UTC.
    """
    befehl = ["curl", "-L", "-sS", "--max-time", str(LIVE_FRIST_SEKUNDEN), LIVE_SEITE]
    abruf = subprocess.run(befehl, capture_output=True, text=True, check=False)
    if abruf.returncode != 0:
        return [f"Live-Seite nicht lesbar ({abruf.stderr.strip()})"]
    seite = abruf.stdout
    heute = heute or datetime.now(UTC).date()
    tage = [heute - timedelta(days=n) for n in range(LIVE_TAGE_ALT + 1)]
    if any(tag.isoformat() in seite for tag in tage):
        return []
    return [f"Live-Seite trägt weder {tage[0]} noch {tage[-1]}"]


def offen() -> dict[str, list[str]]:
    """Gibt je Schritt die Gründe zurück, aus denen er offen ist; leer heißt erfüllt."""
    basis = waechter.lies_zaehlbasis(W / waechter.WAECHTER_BASIS)
    summe = {c: sum(n for (_, k), n in basis.items() if k == c) for _, c in basis}
    git = ["git", "ls-remote", "--heads", "origin"]
    zweige = subprocess.run(git, cwd=W, capture_output=True, text=True).stdout
    html, pipeline = "src/telco_radar/report/html.py", "src/telco_radar/pipeline.py"
    uhr = summe.get("uhr", 0) + waechter_regeln.uhr_ausserhalb_einstieg(W)
    return {
        "1 Aufräumen": _mehr("Zweige neben main", zweige.count("refs/heads/") - 1)
        + ["origin nicht lesbar"] * ("refs/heads/main" not in zweige)
        + ["_to_delete vorhanden"] * (W / "_to_delete").exists(),
        "2 Workflows, Python": _mehr("python-version", summe.get("python-version", 0))
        + zeitreihen_probe()
        + live_datum(),
        "3 Format, Werkzeuge, Basen": rot_proben(),
        "4 Hermetische Tests": [
            f"{c} in Tests {n}, Ziel 0" for c, n in sorted(_tests_summe().items())
        ]
        + _testzeit()
        + _fehlt("tests/fixtures/bestand"),
        "5 Hooks, CLAUDE.md": _hooks()
        + waechter_claude.einstellungen(W)
        + hook_proben()
        + ungepruefte()
        + _vorcommit_median()
        + _mehr("Zeilen CLAUDE.md", _zeilen("CLAUDE.md"), 100),
        "6 Auftragsablauf": _fehlt("tools/auftrag.py", *ROLLENDATEIEN)
        + rollen_sperren()
        + echter_auftrag()
        + mutationsprobe(),
        "7 Kommentarabbau": _mehr("freie Kommentare", freie_kommentare()),
        "8 Promo-IDs": promo_ids() + _fehlt("tests/orakel"),
        "9 Lader, render_site": _mehr("Hex-Farben", summe.get("hexfarbe", 0))
        + _mehr("report-rechnet-nur", _ausnahmen("report-rechnet-nur"), 3)
        + _mehr("Zeilen render_site", _zeilen(html, "render_site"), 99)
        + _fehlt(html),
        "10 run, Uhr, Fehler, Netzweg": _mehr("Uhraufrufe", uhr)
        + _mehr("Zeilen run", _zeilen(pipeline, "run"), 99)
        + _fehlt(pipeline)
        + _mehr("wurzel-unten", _ausnahmen("wurzel-unten"))
        + _mehr("breite except", summe.get("breite-ausnahme", 0), 39),
    }


if __name__ == "__main__":
    for schritt, gruende in offen().items():
        zustand = "offen, weil " + "; ".join(gruende) if gruende else "erfüllt"
        print(f"{schritt}: {zustand}")
    for name in waechter.LISTEN:
        if name.endswith(("basis.json", "basis.txt", "riesendateien.txt")):
            print(f"{name}: {sum(waechter.lies_zaehlbasis(W / name).values())}")
    lockerungen = waechter.anker_verschiebungen(W)
    print(
        "Ankerverschiebungen seit Beginn (Lockerungen):",
        "; ".join(lockerungen) or "keine",
    )
