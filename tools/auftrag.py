"""Führt einen Auftrag vom roten Abnahmetest bis zum Merge auf ``main``.

Das Skript prüft das Auftrags-JSON, legt einen Worktree an, startet die Agenten als
eigene Prozesse und urteilt allein über Exit-Codes. Nach zwei roten Bau-Runden endet
der Auftrag mit einer Notiz unter ``outputs/auftraege/``; ein grüner Auftrag kommt per
``merge --ff-only`` auf ``main`` und wird dort mit der vollen Leiter neu gemessen.
"""

from __future__ import annotations

import argparse
import importlib
import json
import os
import re
import shlex
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import IntEnum
from pathlib import Path

WURZEL = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(WURZEL / "scripts"))
pruefstempel = importlib.import_module("pruefstempel")
format_ = importlib.import_module("auftrag_format")
pruefer_ = importlib.import_module("auftrag_pruefer")
rolle_ = importlib.import_module("claude_rolle")
git_ = importlib.import_module("auftrag_git")
mutation_ = importlib.import_module("mutation")
AUFTRAEGE, KOSTEN, GEMERGT = format_.AUFTRAEGE, format_.KOSTEN, format_.GEMERGT

RUNDEN = 2
TESTVERSUCHE = 2
PARALLEL = 2
DIFF_GRENZE = 400
AUSGABE_ZEILEN = 60
WT_ORDNER = "telco-radar-wt"
ZWEIG = "auftrag/"
STANDARD_AGENT = (
    f"{format_.ECHTER_AGENT} -p --output-format json --permission-mode acceptEdits"
)
LAUFDATEIEN = {
    "TELCO_VORAUSSETZUNG": "voraussetzung.md",
    "TELCO_COMMIT_NACHRICHT": "commit-nachricht.txt",
    "TELCO_AUFTRAG": "auftrag.json",
}
ROT_BELEG = "rot.txt"
BASEN = "pruef/"
SPERRE = "main.sperre"
FACHLICH = re.compile(r"\bAssertionError\b|\bFailed: |^.+?:\d+: assert ")
GRUEN = 0
TESTS_ROT = 1


class Ende(IntEnum):
    """Exit-Code des Skripts je Ausgang eines Auftrags."""

    GEMERGT = 0
    NICHT_GESTARTET = 1
    NOTIZ = 2
    VORAUSSETZUNG = 3
    MAIN_ROT = 4
    ABGEBROCHEN = 5


@dataclass
class Lauf:
    """Zustand eines laufenden Auftrags; Protokolle liegen im Git-Ordner."""

    wurzel: Path
    auftrag: dict
    agent: list[str]
    zeilen: list[dict[str, object]] = field(default_factory=list)
    start: str = ""

    @property
    def wt(self) -> Path:
        """Worktree des Auftrags neben dem Repo."""
        return self.wurzel.parent / WT_ORDNER / self.auftrag["id"]

    def datei(self, name: str) -> Path:
        """Datei im Laufordner, der im gemeinsamen Git-Ordner liegt."""
        gruen = pruefstempel.stempel_ordner(self.wurzel)
        return gruen.parent.parent / "auftraege" / self.auftrag["id"] / name


def _git(ort: Path, *argumente: str) -> str:
    return str(pruefstempel.git(ort, *argumente))


def _laufende(lauf: Lauf) -> list[Path]:
    liste = _git(lauf.wurzel, "worktree", "list", "--porcelain").splitlines()
    pfade = [Path(z[len("worktree ") :]) for z in liste if z.startswith("worktree ")]
    return [p for p in pfade if p.parent == lauf.wt.parent]


def sperren(lauf: Lauf) -> list[str]:
    """Nennt, was den Start sperrt: ungestempelte Commits, Platz, Bereich, Zweig."""
    gruende: list[str] = []
    for ref in ("main", "origin/main"):
        try:
            commits = pruefstempel.ungestempelte(lauf.wurzel, ref).commits
        except pruefstempel.StempelFehler as fehler:
            gruende.append(f"Prüfstempel für {ref} nicht lesbar ({fehler})")
            continue
        if commits:
            kurz = ", ".join(c[:7] for c in commits[:5])
            gruende.append(f"{len(commits)} ungestempelte Commits auf {ref} ({kurz})")
    if _git(lauf.wurzel, "rev-parse", "--abbrev-ref", "HEAD").strip() != "main":
        gruende.append("Hauptarbeitsbaum steht nicht auf main")
    if offen := _git(lauf.wurzel, "status", "--porcelain").split("\n")[0].strip():
        gruende.append(f"Hauptarbeitsbaum nicht sauber ({offen} …), erst committen")
    if not (lauf.wurzel / ".venv/bin/python").is_file():
        gruende.append("Hauptarbeitsbaum ohne .venv, erst make venv")
    laufend, kennung = _laufende(lauf), lauf.auftrag["id"]
    if lauf.wt in laufend or _git(lauf.wurzel, "branch", "--list", ZWEIG + kennung):
        gruende.append(f"Auftrag {kennung} hat schon Worktree oder Zweig")
    if len(laufend) >= PARALLEL:
        gruende.append(f"schon {len(laufend)} Aufträge in Arbeit, höchstens {PARALLEL}")
    eigener = lauf.auftrag["bereich"]
    for anderer in laufend:
        datei = lauf.datei("").parent / anderer.name / "auftrag.json"
        fremd = (
            json.loads(datei.read_text("utf-8"))["bereich"] if datei.is_file() else ""
        )
        if fremd and (eigener.startswith(fremd) or fremd.startswith(eigener)):
            gruende.append(f"Bereich überschneidet sich mit Auftrag {anderer.name}")
    return gruende


def _tail(text: str) -> str:
    return "\n".join(text.strip().splitlines()[-AUSGABE_ZEILEN:])


def _prozess(
    befehl: list[str], ort: Path, eingabe: str | None = None, **extra: str
) -> subprocess.CompletedProcess[str]:
    umgebung = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    return subprocess.run(
        befehl,
        cwd=ort,
        env=umgebung | extra,
        input=eingabe,
        capture_output=True,
        text=True,
        check=False,
    )


def _ausfuehren(befehl: list[str], ort: Path) -> tuple[int, str]:
    lauf = _prozess(befehl, ort)
    return lauf.returncode, lauf.stdout + lauf.stderr


def _leiter(ort: Path, art: str) -> tuple[int, str]:
    python = str(ort / ".venv/bin/python")
    return _ausfuehren([python, "scripts/pruefleiter.py", f"--{art}"], ort)


def _abnahme(lauf: Lauf) -> tuple[int, str]:
    python = str(lauf.wt / ".venv/bin/python")
    befehl = [python, "-m", "pytest", "-q", "--tb=line", "-p", "no:cacheprovider"]
    return _ausfuehren([*befehl, lauf.auftrag["abnahme"]], lauf.wt)


def _zeile(lauf: Lauf, rolle: str, runde: int, code: object, **mehr: object) -> None:
    werte = {"datum": datetime.now(UTC).date().isoformat(), "rolle": rolle}
    werte |= {"auftrag": lauf.auftrag["id"], "runde": runde, "exit": code}
    werte |= {"agent": Path(lauf.agent[0]).name} | mehr
    lauf.zeilen.append(dict.fromkeys(format_.SPALTEN, "") | werte)


def _agent(
    lauf: Lauf, rolle: str, runde: int, befund: str, **extra: str
) -> tuple[int, object]:
    auftrag = lauf.auftrag
    soll = format_.SOLL[auftrag["art"]].format(auftrag.get("erwarteterFehler"))
    werte = {"abnahme": auftrag["abnahme"], "bereich": auftrag["bereich"]}
    prompt = format_.PROMPT[rolle].format(**werte, grenze=DIFF_GRENZE, soll=soll)
    prompt += f"\n\nBefund der letzten Runde:\n{befund}" if befund else ""
    pfade = {name: str(lauf.datei(datei)) for name, datei in LAUFDATEIEN.items()}
    einstellungen = json.dumps(rolle_.einstellungen(rolle))
    befehl = [*lauf.agent, "--agent", rolle, "--settings", einstellungen]
    start = time.monotonic()
    ergebnis = _prozess(befehl, lauf.wt, prompt, TELCO_ROLLE=rolle, **pfade | extra)
    sekunden, code = round(time.monotonic() - start, 1), ergebnis.returncode
    protokoll = ergebnis.stdout + ergebnis.stderr
    try:
        bericht = json.loads((ergebnis.stdout.strip().splitlines() or ["{}"])[-1])
    except json.JSONDecodeError as fehler:
        bericht, protokoll = {}, f"{protokoll}\nKostenbericht nicht lesbar: {fehler}"
    lauf.datei(f"{rolle}-{runde}.log").write_text(protokoll, "utf-8")
    _zeile(lauf, rolle, runde, code, sekunden=sekunden, **format_.verbrauch(bericht))
    return code, bericht


def _ausserhalb(lauf: Lauf, rolle: str) -> str:
    alt, neu = git_.geaendert(lauf.wt, lauf.start)
    ziel = rolle_.Ziel(rolle, lauf.auftrag["bereich"], lauf.auftrag["abnahme"])
    fremd = [p for p in alt + neu if rolle_.verstoss(ziel, lauf.wt, Path(p), p in neu)]
    if git_.kopf(lauf.wt) != (f"refs/heads/{ZWEIG}{lauf.auftrag['id']}", lauf.start):
        fremd.append("HEAD (eigener Commit oder Zweig)")
    return f"Rolle {rolle} darf nicht ändern: {', '.join(sorted(fremd))}" * bool(fremd)


def _pruefer(lauf: Lauf, runde: int) -> str:
    ordner = Path(tempfile.mkdtemp(prefix=f"pruefer-{lauf.auftrag['id']}-"))
    vorher = git_.stand(lauf.wt, lauf.start)
    code, bericht = _agent(lauf, "pruefer", runde, "", TELCO_PRUEFER_ORDNER=str(ordner))
    if git_.stand(lauf.wt, lauf.start) != vorher:
        return "Prüfer hat den Worktree geändert"
    urteil = pruefer_.urteilen(bericht, ordner, lauf.wt)
    lauf.datei(f"pruefer-{runde}-urteil.txt").write_text(urteil.protokoll, "utf-8")
    return f"Prüfer Exit {code}" if code else urteil.befund


def _abnahme_befund(lauf: Lauf) -> str:
    code, ausgabe = _abnahme(lauf)
    erwartet = lauf.auftrag.get("erwarteterFehler")
    if erwartet is None and code == GRUEN:
        return ""
    zeilen = ausgabe.splitlines() if erwartet is not None else []
    belege = [z.strip() for z in zeilen if erwartet in z and FACHLICH.search(z)]
    if code == TESTS_ROT and belege:
        lauf.datei(ROT_BELEG).write_text("\n".join(belege[:3]), "utf-8")
        return ""
    soll = "grün" if erwartet is None else f"rot mit „{erwartet}“"
    return f"Abnahmetest nicht {soll} (Exit {code})\n{_tail(ausgabe)}"


def _testphase(lauf: Lauf) -> str:
    befund = ""
    if (lauf.wt / lauf.auftrag["abnahme"]).is_file():
        befund = _abnahme_befund(lauf)
        if not befund:
            return ""
    for versuch in range(1, TESTVERSUCHE + 1):
        code, _ = _agent(lauf, "test", versuch, befund)
        befund = f"Agent Exit {code}" if code else _ausserhalb(lauf, "test")
        befund = befund or _abnahme_befund(lauf)
        if not befund:
            return ""
    return f"Abnahmetest nach {TESTVERSUCHE} Versuchen nicht wie verlangt:\n{befund}"


def _commit(lauf: Lauf, titel: str, dateien: list[str]) -> str:
    _git(lauf.wt, "add", "--", *dateien)
    code, ausgabe = _ausfuehren(["git", "commit", "-q", "-m", titel], lauf.wt)
    return f"Commit abgelehnt (Exit {code})\n{_tail(ausgabe)}" if code else ""


def _urteil(lauf: Lauf, runde: int, code: int, summe: dict[str, str]) -> str:
    alt, neu = git_.geaendert(lauf.wt, lauf.start)
    zeilen = git_.produktzeilen(lauf.wt, lauf.start)
    if code:
        return f"Agent Exit {code}"
    if anders := git_.veraendert(lauf.wt, summe):
        return f"Abnahmetest geändert oder gelöscht: {', '.join(anders)}"
    if fremd := _ausserhalb(lauf, "bau"):
        return fremd
    if zeilen > DIFF_GRENZE:
        return f"{zeilen} Zeilen Produktcode, höchstens {DIFF_GRENZE}"
    code, ausgabe = _abnahme(lauf)
    if code != GRUEN:
        return f"Abnahmetest rot (Exit {code})\n{_tail(ausgabe)}"
    code, ausgabe = _leiter(lauf.wt, "schnell")
    if code != GRUEN:
        return f"schnelle Leiter rot (Exit {code})\n{_tail(ausgabe)}"
    if befund := _pruefer(lauf, runde):
        return befund
    nachricht = lauf.datei(LAUFDATEIEN["TELCO_COMMIT_NACHRICHT"])
    rot = lauf.datei(ROT_BELEG)
    titel = nachricht.read_text("utf-8").strip() if nachricht.is_file() else ""
    titel = titel or f"auftrag({lauf.auftrag['id']}): {lauf.auftrag['ziel']}"
    if rot.is_file():
        titel += f"\n\nAbnahmetest vor dem Bau rot:\n{rot.read_text('utf-8')}"
    return _commit(lauf, titel, [*alt, *neu])


def _bauphase(lauf: Lauf) -> tuple[Ende, list[str]]:
    testphase = [lauf.auftrag["abnahme"], *sum(git_.geaendert(lauf.wt, lauf.start), [])]
    summe, befunde = git_.pruefsummen(lauf.wt, testphase), [""]
    voraussetzung = lauf.datei(LAUFDATEIEN["TELCO_VORAUSSETZUNG"])
    for runde in range(1, RUNDEN + 1):
        code, _ = _agent(lauf, "bau", runde, befunde[-1])
        if voraussetzung.is_file():
            return Ende.VORAUSSETZUNG, [voraussetzung.read_text("utf-8").strip()]
        befunde.append(_urteil(lauf, runde, code, summe))
        if not befunde[-1]:
            p = mutation_.probe(lauf.wt, lauf.start, lauf.datei("mutation.log"))
            _zeile(lauf, "mutation", 0, p.exit, agent="mutmut", **p.spalten())
            return Ende.GEMERGT, []
    return Ende.NOTIZ, befunde[1:]


def _zusammenfuehren(lauf: Lauf) -> tuple[Ende, list[str]]:
    """Merge, Leiter und Basen-Commit laufen für alle Aufträge nacheinander."""
    with git_.sperre(lauf.datei("").parent / SPERRE):
        return _unter_sperre(lauf)


def _unter_sperre(lauf: Lauf) -> tuple[Ende, list[str]]:
    zweig, frei = ZWEIG + lauf.auftrag["id"], AUFTRAEGE + "/"
    if befund := git_.hauptbaum_befund(lauf.wurzel, frei):
        return Ende.ABGEBROCHEN, [befund]
    code, ausgabe = _ausfuehren(["git", "rebase", "main"], lauf.wt)
    if code:
        _ausfuehren(["git", "rebase", "--abort"], lauf.wt)
        return Ende.NOTIZ, [f"Rebase auf main gescheitert\n{_tail(ausgabe)}"]
    _zeile(lauf, "ende", 0, "", ergebnis=GEMERGT)
    kosten = format_.kosten_schreiben(lauf.zeilen, lauf.wt).relative_to(lauf.wt)
    lauf.zeilen.pop()
    befund = _commit(lauf, f"auftrag({lauf.auftrag['id']}): Kosten", [str(kosten)])
    if befund:
        return Ende.NOTIZ, [befund]
    vorher = _git(lauf.wurzel, "rev-parse", "HEAD").strip()
    code, ausgabe = _ausfuehren(["git", "merge", "--ff-only", "-q", zweig], lauf.wurzel)
    if code:
        return Ende.NOTIZ, [f"merge --ff-only gescheitert\n{_tail(ausgabe)}"]
    gemergt = git_.kopf(lauf.wurzel)[1]
    code, ausgabe = _leiter(lauf.wurzel, "voll")
    basen = git_.schmutz(lauf.wurzel, frei)
    if code != GRUEN or (fremd := [p for p in basen if not p.startswith(BASEN)]):
        grund = f"Leiter änderte {', '.join(fremd)}" if not code else "Leiter rot"
        zurueck = (1, "main hat sich während der Leiter bewegt, nicht zurückgesetzt")
        if git_.kopf(lauf.wurzel)[1] == gemergt:
            zurueck = _ausfuehren(["git", "reset", "--keep", vorher], lauf.wurzel)
        rueck = f"main zurück auf {vorher[:7]}" if not zurueck[0] else zurueck[1]
        return Ende.MAIN_ROT, [f"{grund} auf main; {rueck}\n{_tail(ausgabe)}"]
    if basen:
        titel = f"auftrag({lauf.auftrag['id']}): Basen der Leiter"
        git_.committen(lauf.wurzel, titel, basen)
    _git(lauf.wurzel, "worktree", "remove", "--force", str(lauf.wt))
    _git(lauf.wurzel, "branch", "-d", zweig)
    return Ende.GEMERGT, []


def _ablauf(lauf: Lauf) -> tuple[Ende, list[str]]:
    zweig = ZWEIG + lauf.auftrag["id"]
    _git(lauf.wurzel, "worktree", "add", "-q", "-b", zweig, str(lauf.wt), "main")
    lauf.start = _git(lauf.wt, "rev-parse", "HEAD").strip()
    code, ausgabe = _ausfuehren(["make", "venv"], lauf.wt)
    if code:
        return Ende.VORAUSSETZUNG, [f"make venv: Exit {code}\n{_tail(ausgabe)}"]
    if befund := _testphase(lauf):
        return Ende.NOTIZ, [befund]
    ende, befunde = _bauphase(lauf)
    return _zusammenfuehren(lauf) if ende is Ende.GEMERGT else (ende, befunde)


def ausfuehren(lauf: Lauf) -> Ende:
    """Führt einen startbereiten Auftrag aus und gibt seinen Ausgang zurück."""
    lauf.datei("").mkdir(parents=True, exist_ok=True)
    for alt in [*LAUFDATEIEN.values(), ROT_BELEG]:
        lauf.datei(alt).unlink(missing_ok=True)
    text = json.dumps(lauf.auftrag, ensure_ascii=False, indent=1)
    lauf.datei(LAUFDATEIEN["TELCO_AUFTRAG"]).write_text(text, "utf-8")
    try:
        ende, befunde = _ablauf(lauf)
    except (pruefstempel.StempelFehler, OSError) as fehler:
        ende, befunde = Ende.ABGEBROCHEN, [f"{type(fehler).__name__}: {fehler}"]
    if ende is not Ende.GEMERGT:
        _zeile(lauf, "ende", 0, "", ergebnis=ende.name.lower())
        format_.kosten_schreiben(lauf.zeilen, lauf.wurzel)
        notiz = format_.notiz(
            lauf.wurzel, lauf.auftrag, lauf.wt, ende.name.lower(), befunde
        )
        print(f"Notiz: {notiz}")
    return ende


def main(argv: list[str] | None = None) -> int:
    """Liest den Auftrag, prüft Format und Sperren und führt ihn aus."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("auftrag", type=Path, help="Auftrags-JSON")
    parser.add_argument("--wurzel", type=Path, default=WURZEL)
    parser.add_argument("--agent", default=STANDARD_AGENT, help="Prompt auf stdin")
    argumente = parser.parse_args(argv)
    wurzel = argumente.wurzel.resolve()
    try:
        auftrag = json.loads(argumente.auftrag.read_text("utf-8"))
        gruende = format_.formatfehler(auftrag, wurzel)
        lauf = Lauf(wurzel, auftrag, shlex.split(argumente.agent))
        gruende = gruende or sperren(lauf)
    except (OSError, json.JSONDecodeError, pruefstempel.StempelFehler) as fehler:
        gruende = [f"{type(fehler).__name__}: {fehler}"]
    if gruende:
        print("Auftrag startet nicht:\n- " + "\n- ".join(gruende))
        return Ende.NICHT_GESTARTET
    ende = ausfuehren(lauf)
    print(f"Auftrag {auftrag['id']}: {ende.name.lower()}")
    return ende


if __name__ == "__main__":
    sys.exit(main())
