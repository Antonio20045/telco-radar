"""Meldet je Umbauschritt „erfüllt“ oder „offen, weil …“ und die Summe je Basis."""

import ast
import subprocess

import waechter

W = waechter.WURZEL


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


def _fehlt(*pfade: str) -> list[str]:
    return [f"{p} fehlt" for p in pfade if not (W / p).exists()]


def offen() -> dict[str, list[str]]:
    """Gibt je Schritt die Gründe zurück, aus denen er offen ist; leer heißt erfüllt."""
    basis = waechter.lies_zaehlbasis(W / waechter.WAECHTER_BASIS)
    summe = {c: sum(n for (_, k), n in basis.items() if k == c) for _, c in basis}
    git = ["git", "ls-remote", "--heads", "origin"]
    zweige = subprocess.run(git, cwd=W, capture_output=True, text=True).stdout
    log = W / ".pruefleiter/letzter-lauf.log"
    gruen = log.is_file() and "grün (0 Wächter" in log.read_text("utf-8")
    html, pipeline = "src/telco_radar/report/html.py", "src/telco_radar/pipeline.py"
    return {
        "1 Aufräumen": _mehr("Zweige neben main", zweige.count("refs/heads/") - 1)
        + ["origin nicht lesbar"] * ("refs/heads/main" not in zweige)
        + ["_to_delete vorhanden"] * (W / "_to_delete").exists(),
        "2 Workflows, Python": _mehr("python-version", summe.get("python-version", 0)),
        "3 Format, Werkzeuge, Basen": ["letzter Volllauf nicht grün"] * (not gruen),
        "4 Hermetische Tests": _mehr("rot-bekannt", _zeilen("pruef/rot-bekannt.txt"))
        + _fehlt("tests/fixtures/bestand"),
        "5 Hooks, CLAUDE.md": _fehlt(".githooks/pre-push", ".claude/hooks")
        + _mehr("Zeilen CLAUDE.md", _zeilen("CLAUDE.md"), 100),
        "6 Auftragsablauf": _fehlt("tools/auftrag.py", "outputs/auftraege/kosten.csv"),
        "7 Kommentarabbau": _fehlt("pruef/kommentar-basis.txt"),
        "8 Promo-IDs": _fehlt("outputs/auftraege/T1.json", "tests/orakel"),
        "9 Lader, render_site": _mehr("Hex-Farben", summe.get("hexfarbe", 0))
        + _mehr("report-rechnet-nur", _ausnahmen("report-rechnet-nur"), 3)
        + _mehr("Zeilen render_site", _zeilen(html, "render_site"), 99),
        "10 run, Uhr, Fehler, Netzweg": _mehr("Uhraufrufe", summe.get("uhr", 0))
        + _mehr("Zeilen run", _zeilen(pipeline, "run"), 99)
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
