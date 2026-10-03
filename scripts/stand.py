"""Meldet je Umbauschritt „erfüllt“ oder „offen, weil …“ und die Summe je Basis.

Schritt 2 und 3 messen ihr Fertig-Kriterium aus ``docs/umbau/plan.md`` in einem
Wegwerf-Worktree auf ``HEAD``: kaputter Zeitreihen-Render, Live-Datum, Rot-Proben.
"""

import ast
import contextlib
import os
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Iterator
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import waechter
import waechter_regeln
import waechter_tests

W = waechter.WURZEL
LIVE_SEITE = "https://telco-radar.onrender.com/geraete.html"
LIVE_FRIST_SEKUNDEN = 20
LIVE_TAGE_ALT = 1
TESTZEIT_ZIEL = 240
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
    tests = [z.split(",") for z in zeilen if z.split(",")[1:2] == ["Tests"]]
    if not tests:
        return ["keine Teststufe in .pruefleiter/zeiten.csv"]
    return _mehr(
        "Sekunden der letzten Teststufe", round(float(tests[-1][2])), TESTZEIT_ZIEL
    )


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
        "4 Hermetische Tests": _mehr("rot-bekannt", _zeilen("pruef/rot-bekannt.txt"))
        + _mehr("Testdateien mit Bestand", _zeilen("pruef/tests-mit-bestand.txt"))
        + [f"{c} in Tests {n}, Ziel 0" for c, n in sorted(_tests_summe().items())]
        + _testzeit()
        + _fehlt("tests/fixtures/bestand"),
        "5 Hooks, CLAUDE.md": _fehlt(".githooks/pre-push", ".claude/hooks")
        + _mehr("Zeilen CLAUDE.md", _zeilen("CLAUDE.md"), 100),
        "6 Auftragsablauf": _fehlt("tools/auftrag.py", "outputs/auftraege/kosten.csv"),
        "7 Kommentarabbau": _fehlt("pruef/kommentar-basis.txt"),
        "8 Promo-IDs": _fehlt("outputs/auftraege/T1.json", "tests/orakel"),
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
