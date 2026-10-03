"""Git-Abfragen des Auftragsskripts: geänderte Pfade, Produktzeilen, Kopf, Sperre."""

from __future__ import annotations

import fcntl
import hashlib
import importlib
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

pruefstempel = importlib.import_module("pruefstempel")


def _git(ort: Path, *argumente: str) -> str:
    return str(pruefstempel.git(ort, *argumente))


def geaendert(ort: Path, basis: str) -> tuple[list[str], list[str]]:
    """Pfade gegen ``basis`` samt Arbeitsbaum; Umbenennungen zählen beide Seiten."""
    alt = _git(ort, "diff", "-z", "--name-only", "--no-renames", basis)
    neu = _git(ort, "ls-files", "-z", "--others", "--exclude-standard")
    return [p for p in alt.split("\0") if p], [p for p in neu.split("\0") if p]


def produktzeilen(ort: Path, basis: str) -> int:
    """Hinzugefügte Zeilen unter ``src`` gegen ``basis``, neue Dateien ganz."""
    zahlen = _git(ort, "diff", "--numstat", "--no-renames", basis, "--", "src")
    neu = _git(ort, "ls-files", "-z", "--others", "--exclude-standard", "--", "src")
    spalten = [z.split("\t")[0] for z in zahlen.splitlines()]
    anzahl = sum(int(s) for s in spalten if s.isdigit())
    pfade = [p for p in neu.split("\0") if p]
    return anzahl + sum(len((ort / p).read_bytes().splitlines()) for p in pfade)


def kopf(ort: Path) -> tuple[str, str]:
    """Voller Name des Zweigs (``HEAD``, wenn losgelöst) und Commit des Kopfs."""
    name = _git(ort, "rev-parse", "--symbolic-full-name", "HEAD").strip()
    return name, _git(ort, "rev-parse", "HEAD").strip()


def pruefsumme(datei: Path) -> str:
    """SHA-256 einer Datei, leer, wenn sie fehlt."""
    return hashlib.sha256(datei.read_bytes()).hexdigest() if datei.is_file() else ""


@contextmanager
def sperre(datei: Path) -> Iterator[None]:
    """Hält eine exklusive Sperre auf ``datei``, wartet, bis sie frei ist."""
    with datei.open("a") as offen:
        fcntl.flock(offen, fcntl.LOCK_EX)
        yield


def schmutz(ort: Path, frei: str) -> list[str]:
    """Geänderte Pfade des Arbeitsbaums gegen HEAD außer denen unter ``frei``."""
    return [p for p in sum(geaendert(ort, "HEAD"), []) if not p.startswith(frei)]


def hauptbaum_befund(wurzel: Path, frei: str) -> str:
    """Was den Merge sperrt: ungestempelte Commits auf main, schmutziger Baum."""
    if fremde := pruefstempel.ungestempelte(wurzel, "main").commits:
        return f"ungestempelte Commits auf main: {', '.join(fremde)}"
    geaendert = schmutz(wurzel, frei)
    return f"Hauptbaum vor dem Merge verändert: {', '.join(geaendert)}" * bool(
        geaendert
    )


def stand(ort: Path, basis: str) -> tuple[object, ...]:
    """Pfade, Kopf und Inhalt des Arbeitsbaums gegen ``basis`` zum Vergleich."""
    return geaendert(ort, basis), kopf(ort), _git(ort, "diff", "--binary", basis)


def committen(ort: Path, titel: str, pfade: list[str]) -> None:
    """Committet genau ``pfade``; anderes Gestagtes bleibt draußen."""
    _git(ort, "add", "--", *pfade)
    _git(ort, "commit", "-q", "-m", titel, "--", *pfade)
