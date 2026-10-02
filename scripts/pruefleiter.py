"""Prüfleiter: billig vor teuer, Abbruch bei der ersten roten Stufe, Exit-Code zählt.

Aufruf: ``python scripts/pruefleiter.py --voll``. Grün ist eine Zeile, Rot höchstens 60;
das volle Protokoll steht in ``.pruefleiter/letzter-lauf.log``. Bestandsbefunde stehen
unter ``pruef/``; die Leiter senkt diese Basen selbst und erhöht sie nie. Die Zahl der
gesammelten Tests ist eine Untergrenze, die nur steigt; die Zahl der übersprungenen
und ``xfail``-Tests eine Obergrenze, die nur sinkt. Variablen der Umgebung, die
Auswahl, Strenge oder Ausgabe der Werkzeuge ändern, erreichen die Werkzeuge nicht.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import signal
import subprocess
import sys
import tempfile
import time
from collections import Counter
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import TextIO

import leiter_pytest
import waechter
from leiter_befunde import Befund, gesenkte_basis, mypy_befunde, neue_befunde
from leiter_pytest import gesammelte_tests, nicht_ausgefuehrte_tests, pytest_ausgang
from waechter import lies_zaehlbasis, schreibe_zaehlbasis

WURZEL = Path(__file__).resolve().parents[1]
BIN = Path(sys.executable).parent
RUFF_BASIS = WURZEL / "pruef" / "ruff-basis.json"
MYPY_BASIS = WURZEL / "pruef" / "mypy-basis.txt"
ROT_BEKANNT = WURZEL / "pruef" / "rot-bekannt.txt"
TESTS_ANZAHL = WURZEL / "pruef" / "tests-anzahl.txt"
TESTS_UEBERSPRUNGEN = WURZEL / "pruef" / "tests-uebersprungen.txt"
KANARIE = "tests/kanarie_leiter.py"
LAUF_ORDNER = WURZEL / ".pruefleiter"
MAX_ROT_ZEILEN = 60
TEST_FRIST_SEKUNDEN = 300
STUFE_FRIST_SEKUNDEN = 1800
NACHLAUF_SEKUNDEN = 10
# Präfixe der Variablen, die pytest, ruff, mypy oder Python selbst lesen und mit denen
# sich Tests abwählen, Regeln lockern oder die Ausgabe für die Auswertung verbiegen
# ließe (PYTEST_ADDOPTS, PYTEST_PLUGINS, RUFF_*, MYPYPATH, PYTHON*, Farben).
_FREMDE_UMGEBUNG = (
    "PYTEST_",
    "PYTHON",
    "RUFF_",
    "MYPY",
    "PY_COLORS",
    "PY_IGNORE",
    "FORCE_COLOR",
    "NO_COLOR",
    "CLICOLOR",
)
Schluessel = waechter.Schluessel


@dataclass
class Ergebnis:
    """Ausgang einer Stufe: grün oder rot mit den Zeilen, die Rot begründen."""

    stufe: str
    gruen: bool
    zeilen: list[str] = field(default_factory=list)
    gesenkt: list[str] = field(default_factory=list)
    angehoben: list[str] = field(default_factory=list)
    hinweise: list[str] = field(default_factory=list)
    sekunden: float = 0.0


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


def umgebung(basis: Mapping[str, str]) -> dict[str, str]:
    """Gibt die Umgebung der Werkzeuge zurück: ohne fremde Steuerung, mit ``src``."""
    sauber = {k: v for k, v in basis.items() if not k.startswith(_FREMDE_UMGEBUNG)}
    sauber["PYTHONPATH"] = str(WURZEL / "src")
    return sauber


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


def stufe_waechter(log: TextIO) -> Ergebnis:
    """Stufe 0: Zählungen gegen ihre Basen, keine Liste lockerer als im Verlauf."""
    befehl = [str(BIN / "ruff"), "check", "--preview", "--select", "PLC2701"]
    lauf = _lauf(log, [*befehl, "--output-format", "json"])
    if lauf.returncode not in (0, 1):
        meldung = ["ruff bricht ab:", *lauf.stderr.splitlines()]
        return Ergebnis("0 Wächter", False, meldung)
    privat = Counter(b.schluessel for b in ruff_befunde(lauf.stdout))
    rot, geschrieben = waechter.pruefe(WURZEL, privat)
    ergebnis = Ergebnis("0 Wächter", not rot, rot, [_relativ(p) for p in geschrieben])
    ergebnis.hinweise = waechter.anker_verschiebungen(WURZEL)
    return ergebnis


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
    """Volle Suite; rot ist jeder unbekannt rote Test und jeder fehlende Test."""
    befehl = [
        sys.executable,
        "-m",
        "pytest",
        "-n",
        "auto",
        "--dist",
        "worksteal",
        "-rfEp",
        f"--timeout={TEST_FRIST_SEKUNDEN}",
        "-o",
        f"python_files=test_*.py *_test.py {Path(KANARIE).name}",
        "-p",
        leiter_pytest.PLUGIN,
    ]
    with tempfile.TemporaryDirectory() as ordner:
        pfade = os.pathsep.join(map(str, (WURZEL / "src", leiter_pytest.PLUGIN_ORDNER)))
        zusatz = {leiter_pytest.ROH_VARIABLE: ordner, "PYTHONPATH": pfade}
        lauf = _lauf(log, befehl, zusatz)
        roh = leiter_pytest.lies_roh(Path(ordner))
    rot, gruen = pytest_ausgang(lauf.stdout)
    if lauf.returncode not in (0, 1) or (lauf.returncode == 1 and not rot):
        ende = lauf.stdout.splitlines()[-20:] + lauf.stderr.splitlines()[-20:]
        return Ergebnis("Tests", False, [f"pytest endet mit {lauf.returncode}:", *ende])
    anzahl = gesammelte_tests(lauf.stdout)
    untergrenze = int(TESTS_ANZAHL.read_text(encoding="utf-8"))
    if anzahl is None:
        return Ergebnis("Tests", False, ["Zahl der gesammelten Tests nicht lesbar"])
    if anzahl < untergrenze:
        meldung = (
            f"{anzahl} Tests gesammelt, erwartet mindestens {untergrenze}"
            f" ({_relativ(TESTS_ANZAHL)}): Tests gelöscht oder abgewählt"
        )
        return Ergebnis("Tests", False, [meldung])
    uebersprungen = nicht_ausgefuehrte_tests(lauf.stdout)
    obergrenze = int(TESTS_UEBERSPRUNGEN.read_text(encoding="utf-8"))
    if uebersprungen is None:
        return Ergebnis("Tests", False, ["Schlusszeile von pytest nicht lesbar"])
    if uebersprungen > obergrenze:
        meldung = (
            f"{uebersprungen} Tests übersprungen oder xfail, erlaubt höchstens"
            f" {obergrenze} ({_relativ(TESTS_UEBERSPRUNGEN)})"
        )
        return Ergebnis("Tests", False, [meldung])
    falsch = leiter_pytest.pruefe_ergebnisse(rot, gruen, roh, KANARIE)
    if falsch:
        return Ergebnis("Tests", False, falsch)
    bekannt = []
    if ROT_BEKANNT.exists():
        bekannt = ROT_BEKANNT.read_text(encoding="utf-8").splitlines()
    unbekannt = [zeile for test, zeile in rot.items() if test not in bekannt]
    if unbekannt:
        return Ergebnis("Tests", False, unbekannt)
    ergebnis = Ergebnis("Tests", True)
    if anzahl > untergrenze:
        TESTS_ANZAHL.write_text(f"{anzahl}\n", encoding="utf-8")
        ergebnis.angehoben.append(_relativ(TESTS_ANZAHL))
    if uebersprungen < obergrenze:
        TESTS_UEBERSPRUNGEN.write_text(f"{uebersprungen}\n", encoding="utf-8")
        ergebnis.gesenkt.append(_relativ(TESTS_UEBERSPRUNGEN))
    rest = [test for test in bekannt if test in rot or test not in gruen]
    if rest != bekannt:
        ROT_BEKANNT.write_text("".join(f"{test}\n" for test in rest), encoding="utf-8")
        ergebnis.gesenkt.append(_relativ(ROT_BEKANNT))
    return ergebnis


STUFEN_STATISCH: list[Callable[[TextIO], Ergebnis]] = [
    stufe_waechter,
    stufe_lint,
    stufe_typen,
    stufe_schichten,
]
STUFEN_VOLL = [*STUFEN_STATISCH, stufe_tests]


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
    angehoben = [pfad for e in ergebnisse for pfad in e.angehoben]
    hinweise = [h for e in ergebnisse for h in e.hinweise]
    letzte = ergebnisse[-1]
    if letzte.gruen:
        senkung = f"; gesenkt: {', '.join(gesenkt)}" if gesenkt else ""
        hebung = f"; angehoben: {', '.join(angehoben)}" if angehoben else ""
        lockerung = f"; {'; '.join(hinweise)}" if hinweise else ""
        return [f"Prüfleiter grün ({zeiten}{senkung}{hebung}{lockerung})"]
    kopf = f"Prüfleiter rot in Stufe {letzte.stufe} ({zeiten})"
    fuss = f"Volles Protokoll: {_relativ(LAUF_ORDNER / 'letzter-lauf.log')}"
    platz = MAX_ROT_ZEILEN - 2
    zeilen = [*hinweise, *letzte.zeilen]
    if len(zeilen) > platz:
        zeilen = [
            *zeilen[: platz - 1],
            f"… und {len(zeilen) - platz + 1} weitere Zeilen",
        ]
    return [kopf, *zeilen, fuss]


def main(argv: list[str] | None = None) -> int:
    """Startet die Leiter; Exit 0 heißt grün, 1 rot."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    art = parser.add_mutually_exclusive_group(required=True)
    art.add_argument("--voll", action="store_true", help="Stufen 0 bis 3, alle Tests")
    art.add_argument("--statisch", action="store_true", help="Stufen 0 bis 3")
    args = parser.parse_args(argv)
    LAUF_ORDNER.mkdir(exist_ok=True)
    with (LAUF_ORDNER / "letzter-lauf.log").open("w", encoding="utf-8") as log:
        ergebnisse = fuehre_aus(STUFEN_VOLL if args.voll else STUFEN_STATISCH, log)
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


def _lauf(
    log: TextIO, befehl: list[str], zusatz: Mapping[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    # Eigene Prozessgruppe: Bei überschrittener Frist sterben auch die Worker von
    # pytest-xdist, sonst hielten sie die Pipes offen und die Leiter hinge mit.
    with subprocess.Popen(
        befehl,
        cwd=WURZEL,
        env={**umgebung(os.environ), **(zusatz or {})},
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,
    ) as prozess:
        try:
            stdout, stderr = prozess.communicate(timeout=STUFE_FRIST_SEKUNDEN)
        except subprocess.TimeoutExpired:
            with contextlib.suppress(ProcessLookupError):
                os.killpg(prozess.pid, signal.SIGKILL)
            try:
                stdout, stderr = prozess.communicate(timeout=NACHLAUF_SEKUNDEN)
            except subprocess.TimeoutExpired:
                # Ein Enkel in eigener Sitzung hält die Pipe; die Ausgabe ist verloren.
                stdout, stderr = "", ""
            stderr += f"\nabgebrochen nach {STUFE_FRIST_SEKUNDEN} s\n"
        lauf = subprocess.CompletedProcess(befehl, prozess.wait(), stdout, stderr)
    log.write(
        f"$ {' '.join(befehl)}\n-> Exit {lauf.returncode}\n{lauf.stdout}{lauf.stderr}\n"
    )
    return lauf


def _relativ(pfad: str | Path) -> str:
    pfad = Path(pfad)
    return str(pfad.relative_to(WURZEL)) if pfad.is_relative_to(WURZEL) else str(pfad)


if __name__ == "__main__":
    sys.exit(main())
