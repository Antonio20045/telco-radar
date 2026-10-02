"""Prüfleiter: billig vor teuer, Abbruch bei der ersten roten Stufe, Exit-Code zählt.

Aufruf: ``python scripts/pruefleiter.py --voll``. Grün ist eine Zeile, Rot höchstens 60;
das volle Protokoll steht in ``.pruefleiter/letzter-lauf.log``. Bestandsbefunde stehen
unter ``pruef/``; die Leiter senkt diese Basen selbst und erhöht sie nie.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import TextIO

WURZEL = Path(__file__).resolve().parents[1]
BIN = Path(sys.executable).parent
RUFF_BASIS = WURZEL / "pruef" / "ruff-basis.json"
MYPY_BASIS = WURZEL / "pruef" / "mypy-basis.txt"
ROT_BEKANNT = WURZEL / "pruef" / "rot-bekannt.txt"
LAUF_ORDNER = WURZEL / ".pruefleiter"
MAX_ROT_ZEILEN = 60
_MYPY_FEHLER = ": error: "

Schluessel = tuple[str, str]


@dataclass(frozen=True)
class Befund:
    """Ein Befund eines Prüfwerkzeugs; verglichen wird je Datei und Code, ohne Zeile."""

    pfad: str
    zeile: int
    code: str
    text: str

    @property
    def schluessel(self) -> Schluessel:
        """Datei und Code, unter denen die Basis den Befund zählt."""
        return (self.pfad, self.code)


@dataclass
class Ergebnis:
    """Ausgang einer Stufe: grün oder rot mit den Zeilen, die Rot begründen."""

    stufe: str
    gruen: bool
    zeilen: list[str] = field(default_factory=list)
    gesenkt: list[str] = field(default_factory=list)
    sekunden: float = 0.0


def neue_befunde(befunde: list[Befund], basis: Counter[Schluessel]) -> list[Befund]:
    """Gibt die Befunde der Schlüssel zurück, die öfter vorkommen als in der Basis."""
    zaehlung = Counter(b.schluessel for b in befunde)
    ueber = {k for k, n in zaehlung.items() if n > basis[k]}
    return [b for b in befunde if b.schluessel in ueber]


def gesenkte_basis(
    befunde: list[Befund], basis: Counter[Schluessel]
) -> Counter[Schluessel]:
    """Gibt die Basis zurück, in der kein Schlüssel öfter steht als heute gefunden."""
    zaehlung = Counter(b.schluessel for b in befunde)
    return Counter({k: min(n, zaehlung[k]) for k, n in basis.items() if zaehlung[k]})


def ruff_befunde(ausgabe: str) -> list[Befund]:
    """Liest ``ruff check --output-format json`` in Befunde mit relativen Pfaden."""
    return [
        Befund(
            _relativ(eintrag["filename"]),
            eintrag["location"]["row"],
            eintrag["code"] or "syntax",
            eintrag["message"],
        )
        for eintrag in json.loads(ausgabe)
    ]


def mypy_befunde(ausgabe: str) -> list[Befund]:
    """Liest die Fehlerzeilen von mypy; Hinweiszeilen zählen nicht."""
    befunde = []
    for zeile in ausgabe.splitlines():
        ort, trenner, rest = zeile.partition(_MYPY_FEHLER)
        if not trenner:
            continue
        pfad, _, nummer = ort.partition(":")
        text, _, code = rest.rpartition("  [")
        if not code.endswith("]"):
            text, code = rest, "ohne-code]"
        nummer = nummer.partition(":")[0]
        zeile_nr = int(nummer) if nummer.isdigit() else 0
        befunde.append(Befund(pfad, zeile_nr, code[:-1], text))
    return befunde


def pytest_ausgang(ausgabe: str) -> tuple[dict[str, str], set[str]]:
    """Gibt gescheiterte Tests mit ihrer Zeile und bestandene aus ``-rfEp`` zurück."""
    rot: dict[str, str] = {}
    gruen: set[str] = set()
    _, _, zusammenfassung = ausgabe.partition("short test summary info")
    for zeile in zusammenfassung.splitlines():
        art, _, rest = zeile.partition(" ")
        if art in ("FAILED", "ERROR"):
            rot[rest.split(" - ", 1)[0]] = zeile
        elif art == "PASSED":
            gruen.add(rest)
    return rot, gruen


def lies_zaehlbasis(pfad: Path) -> Counter[Schluessel]:
    """Liest eine Basis: JSON je Datei und Code oder Zeilen ``pfad code anzahl``."""
    if pfad.suffix == ".json":
        roh = json.loads(pfad.read_text(encoding="utf-8"))
        return Counter(
            {(p, c): n for p, codes in roh.items() for c, n in codes.items()}
        )
    basis: Counter[Schluessel] = Counter()
    for zeile in pfad.read_text(encoding="utf-8").splitlines():
        p, c, n = zeile.split()
        basis[(p, c)] = int(n)
    return basis


def schreibe_zaehlbasis(pfad: Path, basis: Counter[Schluessel]) -> None:
    """Schreibt eine Basis sortiert im Format, das ``lies_zaehlbasis`` liest."""
    if pfad.suffix == ".json":
        roh: dict[str, dict[str, int]] = {}
        for (p, c), n in sorted(basis.items()):
            roh.setdefault(p, {})[c] = n
        text = json.dumps(roh, indent=1, sort_keys=True, ensure_ascii=False) + "\n"
    else:
        text = "".join(f"{p} {c} {n}\n" for (p, c), n in sorted(basis.items()))
    pfad.write_text(text, encoding="utf-8")


def vergleiche(stufe: str, befunde: list[Befund], basis_pfad: Path) -> Ergebnis:
    """Hält Befunde gegen ihre Basis: Neues ist rot, Weniger senkt die Basis."""
    basis = lies_zaehlbasis(basis_pfad)
    neu = neue_befunde(befunde, basis)
    if neu:
        zaehlung = Counter(b.schluessel for b in befunde)
        zeilen = [
            f"{b.pfad}:{b.zeile} [{b.code}] erwartet höchstens {basis[b.schluessel]}"
            f" je Datei, gefunden {zaehlung[b.schluessel]}: {b.text}"
            for b in neu
        ]
        return Ergebnis(stufe, False, zeilen)
    gesenkt = gesenkte_basis(befunde, basis)
    if gesenkt == basis:
        return Ergebnis(stufe, True)
    schreibe_zaehlbasis(basis_pfad, gesenkt)
    return Ergebnis(stufe, True, gesenkt=[_relativ(basis_pfad)])


def stufe_lint(log: TextIO) -> Ergebnis:
    """Stufe 1: ``ruff format --check`` muss grün sein, ``ruff check`` gegen Basis."""
    form = _lauf(log, [str(BIN / "ruff"), "format", "--check"])
    if form.returncode not in (0, 1):
        meldung = ["ruff format bricht ab:", *form.stderr.splitlines()]
        return Ergebnis("1 Lint", False, meldung)
    if form.returncode == 1:
        dateien = [
            z for z in form.stdout.splitlines() if z.startswith("Would reformat")
        ]
        return Ergebnis("1 Lint", False, ["ruff format: nicht formatiert", *dateien])
    lauf = _lauf(log, [str(BIN / "ruff"), "check", "--output-format", "json"])
    if lauf.returncode not in (0, 1):
        return Ergebnis(
            "1 Lint", False, ["ruff check bricht ab:", *lauf.stderr.splitlines()]
        )
    return vergleiche("1 Lint", ruff_befunde(lauf.stdout), RUFF_BASIS)


def stufe_typen(log: TextIO) -> Ergebnis:
    """Stufe 2: mypy-Fehler je Datei und Code gegen ``pruef/mypy-basis.txt``."""
    lauf = _lauf(log, [str(BIN / "mypy")])
    befunde = mypy_befunde(lauf.stdout)
    if lauf.returncode not in (0, 1) or (lauf.returncode == 1 and not befunde):
        zeilen = (lauf.stdout + lauf.stderr).splitlines()
        return Ergebnis("2 Typen", False, ["mypy bricht ab:", *zeilen])
    return vergleiche("2 Typen", befunde, MYPY_BASIS)


def stufe_schichten(log: TextIO) -> Ergebnis:
    """Stufe 3: Jeder Vertrag aus ``.importlinter`` muss gehalten sein."""
    lauf = _lauf(log, [str(BIN / "lint-imports"), "--no-cache"])
    if lauf.returncode == 0:
        return Ergebnis("3 Schichten", True)
    _, _, bericht = lauf.stdout.partition("Broken contracts")
    zeilen = [
        z for z in (bericht or lauf.stdout + lauf.stderr).splitlines() if z.strip("- ")
    ]
    return Ergebnis("3 Schichten", False, zeilen)


def stufe_tests(log: TextIO) -> Ergebnis:
    """Volle Suite; rot ist jeder gescheiterte Test, der nicht bekannt rot ist."""
    befehl = [
        sys.executable,
        "-m",
        "pytest",
        "-q",
        "-n",
        "auto",
        "--dist",
        "worksteal",
        "-rfEp",
    ]
    lauf = _lauf(log, befehl)
    rot, gruen = pytest_ausgang(lauf.stdout)
    if lauf.returncode not in (0, 1) or (lauf.returncode == 1 and not rot):
        ende = lauf.stdout.splitlines()[-20:] + lauf.stderr.splitlines()[-20:]
        return Ergebnis("Tests", False, [f"pytest endet mit {lauf.returncode}:", *ende])
    bekannt = []
    if ROT_BEKANNT.exists():
        bekannt = ROT_BEKANNT.read_text(encoding="utf-8").splitlines()
    unbekannt = [zeile for test, zeile in rot.items() if test not in bekannt]
    if unbekannt:
        return Ergebnis("Tests", False, unbekannt)
    rest = [test for test in bekannt if test in rot or test not in gruen]
    if rest == bekannt:
        return Ergebnis("Tests", True)
    ROT_BEKANNT.write_text("".join(f"{test}\n" for test in rest), encoding="utf-8")
    return Ergebnis("Tests", True, gesenkt=[_relativ(ROT_BEKANNT)])


STUFEN_VOLL: list[Callable[[TextIO], Ergebnis]] = [
    stufe_lint,
    stufe_typen,
    stufe_schichten,
    stufe_tests,
]


def fuehre_aus(
    stufen: list[Callable[[TextIO], Ergebnis]], log: TextIO
) -> list[Ergebnis]:
    """Führt die Stufen der Reihe nach aus und hört nach der ersten roten auf."""
    ergebnisse = []
    for stufe in stufen:
        start = time.monotonic()
        ergebnis = stufe(log)
        ergebnis.sekunden = time.monotonic() - start
        ergebnisse.append(ergebnis)
        log.write(f"== {ergebnis.stufe}: {'grün' if ergebnis.gruen else 'rot'}\n")
        log.writelines(f"{zeile}\n" for zeile in ergebnis.zeilen)
        if not ergebnis.gruen:
            break
    return ergebnisse


def zusammenfassung(ergebnisse: list[Ergebnis]) -> list[str]:
    """Grün ist eine Zeile, Rot höchstens ``MAX_ROT_ZEILEN`` samt Verweis aufs Log."""
    zeiten = ", ".join(f"{e.stufe} {e.sekunden:.0f} s" for e in ergebnisse)
    gesenkt = [pfad for e in ergebnisse for pfad in e.gesenkt]
    letzte = ergebnisse[-1]
    if letzte.gruen:
        senkung = f"; gesenkt: {', '.join(gesenkt)}" if gesenkt else ""
        return [f"Prüfleiter grün ({zeiten}{senkung})"]
    kopf = f"Prüfleiter rot in Stufe {letzte.stufe} ({zeiten})"
    fuss = f"Volles Protokoll: {_relativ(LAUF_ORDNER / 'letzter-lauf.log')}"
    platz = MAX_ROT_ZEILEN - 2
    zeilen = letzte.zeilen
    if len(zeilen) > platz:
        zeilen = [
            *zeilen[: platz - 1],
            f"… und {len(zeilen) - platz + 1} weitere Zeilen",
        ]
    return [kopf, *zeilen, fuss]


def main(argv: list[str] | None = None) -> int:
    """Startet die Leiter; Exit 0 heißt grün, 1 rot."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--voll", action="store_true", help="Stufen 1 bis 3 und alle Tests"
    )
    args = parser.parse_args(argv)
    if not args.voll:
        parser.error("bisher gibt es nur --voll")
    LAUF_ORDNER.mkdir(exist_ok=True)
    with (LAUF_ORDNER / "letzter-lauf.log").open("w", encoding="utf-8") as log:
        ergebnisse = fuehre_aus(STUFEN_VOLL, log)
        ausgabe = zusammenfassung(ergebnisse)
        log.writelines(f"{zeile}\n" for zeile in ausgabe)
    with (LAUF_ORDNER / "zeiten.csv").open("a", encoding="utf-8") as zeiten:
        stempel = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        zeiten.writelines(
            f"{stempel},{e.stufe},{e.sekunden:.1f},{'gruen' if e.gruen else 'rot'}\n"
            for e in ergebnisse
        )
    print("\n".join(ausgabe))
    return 0 if ergebnisse[-1].gruen else 1


def _lauf(log: TextIO, befehl: list[str]) -> subprocess.CompletedProcess[str]:
    lauf = subprocess.run(
        befehl,
        cwd=WURZEL,
        env={**os.environ, "PYTHONPATH": str(WURZEL / "src")},
        capture_output=True,
        text=True,
    )
    log.write(
        f"$ {' '.join(befehl)}\n-> Exit {lauf.returncode}\n{lauf.stdout}{lauf.stderr}\n"
    )
    return lauf


def _relativ(pfad: str | Path) -> str:
    pfad = Path(pfad)
    return str(pfad.relative_to(WURZEL)) if pfad.is_relative_to(WURZEL) else str(pfad)


if __name__ == "__main__":
    sys.exit(main())
