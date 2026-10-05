"""Git-Abfragen des Auftragsskripts: geänderte Pfade, Produktzeilen, Kopf, Sperre."""

from __future__ import annotations

import fcntl
import hashlib
import importlib
import os
import posixpath
import subprocess
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from pathlib import Path
from unicodedata import normalize

pruefstempel = importlib.import_module("pruefstempel")


def _git(ort: Path, *argumente: str) -> str:
    return str(pruefstempel.git(ort, *argumente))


def _git_ein(ort: Path, eingabe: bytes, *argumente: str) -> str:
    umgebung = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    befehl = ["git", *argumente]
    lauf = subprocess.run(
        befehl, cwd=ort, env=umgebung, input=eingabe, capture_output=True, check=True
    )
    return lauf.stdout.decode().strip()


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


def pruefsummen(ort: Path, pfade: Iterable[str]) -> dict[str, str]:
    """SHA-256 je Pfad unter ``ort``, leer, wenn die Datei fehlt."""
    dateien = {p: ort / p for p in pfade}
    return {
        p: hashlib.sha256(d.read_bytes()).hexdigest() if d.is_file() else ""
        for p, d in dateien.items()
    }


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
    _git(
        ort, "-c", "core.hooksPath=/dev/null", "commit", "-q", "-m", titel, "--", *pfade
    )


def veraendert(ort: Path, summen: dict[str, str]) -> list[str]:
    """Pfade, deren Prüfsumme nicht mehr der in ``summen`` gleicht."""
    return [p for p, s in pruefsummen(ort, summen).items() if s != summen[p]]


def blobs(ort: Path, pfade: list[str]) -> dict[str, str]:
    """Schreibt jeden Pfad als Blob; gibt ``modus,blob`` je Pfad, leer bei fehlend."""
    stand: dict[str, str] = {}
    for pfad in pfade:
        datei = ort / pfad
        if datei.is_symlink():
            ziel = os.readlink(datei).encode()
            blob = _git_ein(ort, ziel, "hash-object", "-w", "--stdin")
            stand[pfad] = f"120000,{blob}"
        elif datei.is_file():
            modus = "100755" if os.access(datei, os.X_OK) else "100644"
            blob = _git(ort, "hash-object", "-w", "--no-filters", "--", pfad).strip()
            stand[pfad] = f"{modus},{blob}"
        else:
            stand[pfad] = ""
    return stand


def genau_committen(ort: Path, titel: str, stand: dict[str, str]) -> str:
    """Committet genau die Blobs aus ``stand`` auf HEAD, ohne Haken, und prüft nach."""
    if not stand:
        return "Commit abgelehnt: keine geprüfte Änderung"
    alt = kopf(ort)[1]
    _git(ort, "read-tree", alt)
    for pfad, eintrag in stand.items():
        if eintrag:
            _git(ort, "update-index", "--add", "--cacheinfo", f"{eintrag},{pfad}")
        else:
            _git(ort, "update-index", "--force-remove", "--", pfad)
    baum = _git(ort, "write-tree").strip()
    neu = _git(ort, "commit-tree", baum, "-p", alt, "-m", titel).strip()
    _git(ort, "update-ref", "-m", titel, "HEAD", neu, alt)
    drin = _git(ort, "diff", "-z", "--name-only", "--no-renames", alt, neu)
    if abweichung := sorted({p for p in drin.split("\0") if p} ^ set(stand)):
        return f"Commit weicht von den geprüften Pfaden ab: {', '.join(abweichung)}"
    ist = _git(ort, "rev-parse", "HEAD^", "HEAD^{tree}").split()
    return "" if ist == [alt, baum] else f"HEAD nach dem Commit ist nicht {neu[:7]}"


def ueberschneiden(eins: str, zwei: str) -> bool:
    """Ob zwei Bereiche denselben Pfad treffen, auch auf Dateisystemen wie macOS."""
    a, b = (posixpath.normpath(normalize("NFC", x).casefold()) for x in (eins, zwei))
    return a == b or a.startswith(b + "/") or b.startswith(a + "/")
