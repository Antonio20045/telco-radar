"""Abdeckung der Kommentarübernahme: jede kommentierte Datei hat ihr Protokoll.

Vor dem Löschen der Kommentare muss ihr Wissen unter `outputs/kommentarwissen/`
stehen. Das Werkzeug meldet Dateien mit Wissenskommentaren ohne Abschnitt im
Protokoll und Dateien, deren Kommentare sich seit der Übernahme geändert haben.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import subprocess
import sys
import tokenize
from pathlib import Path

WURZEL = Path(__file__).resolve().parents[1]
PROTOKOLLE = Path("outputs/kommentarwissen")
ABDECKUNG = PROTOKOLLE / "abdeckung.json"
NICHT_GEPRUEFT = ("site/", "data/")
WERKZEUGKOMMENTAR = re.compile(r"#\s*(?:noqa\b|type:\s*ignore\b|pragma:\s*no cover\b)")
SHEBANG = "#!"
UEBERSCHRIFT = re.compile(r"^### `([^`]+)`\s*$", re.MULTILINE)


class Unlesbar(Exception):
    """Eine Python-Datei lässt sich nicht in Tokens zerlegen."""


def wissenskommentare(text: str) -> list[str]:
    """Alle `#`-Kommentare außer Werkzeugschaltern und der Shebang-Zeile."""
    try:
        tokens = list(tokenize.generate_tokens(io.StringIO(text).readline))
    except (tokenize.TokenError, SyntaxError) as fehler:
        raise Unlesbar(str(fehler)) from fehler
    return [
        t.string
        for t in tokens
        if t.type == tokenize.COMMENT
        and not WERKZEUGKOMMENTAR.match(t.string)
        and not (t.start[0] == 1 and t.string.startswith(SHEBANG))
    ]


def fingerabdruck(kommentare: list[str]) -> str:
    """sha256 über die Kommentare einer Datei in ihrer Reihenfolge."""
    return hashlib.sha256("\n".join(kommentare).encode()).hexdigest()


def kommentierte_dateien(wurzel: Path) -> dict[str, str]:
    """Versionierte Python-Dateien mit Wissenskommentaren und ihr Fingerabdruck."""
    lauf = subprocess.run(
        ["git", "ls-files", "-z", "--", "*.py"],
        cwd=wurzel,
        capture_output=True,
        text=True,
        check=True,
    )
    ergebnis: dict[str, str] = {}
    for pfad in sorted(filter(None, lauf.stdout.split("\0"))):
        datei = wurzel / pfad
        if pfad.startswith(NICHT_GEPRUEFT) or not datei.is_file():
            continue
        try:
            kommentare = wissenskommentare(datei.read_text(encoding="utf-8"))
        except Unlesbar as fehler:
            raise Unlesbar(f"{pfad}: {fehler}") from fehler
        if kommentare:
            ergebnis[pfad] = fingerabdruck(kommentare)
    return ergebnis


def protokollierte(wurzel: Path) -> set[str]:
    """Pfade, die in einem Protokoll eine eigene Überschrift haben."""
    pfade: set[str] = set()
    for protokoll in sorted((wurzel / PROTOKOLLE).glob("*.md")):
        pfade.update(UEBERSCHRIFT.findall(protokoll.read_text(encoding="utf-8")))
    return pfade


def gespeicherte_abdeckung(wurzel: Path) -> dict[str, str]:
    """Fingerabdrücke zum Zeitpunkt der Übernahme; leer, solange keine Datei da ist."""
    datei = wurzel / ABDECKUNG
    if not datei.exists():
        return {}
    daten = json.loads(datei.read_text(encoding="utf-8"))
    return {str(k): str(v) for k, v in daten["dateien"].items()}


def befunde(wurzel: Path) -> list[str]:
    """Eine Zeile je Datei, deren Kommentarwissen nicht übernommen ist."""
    aktuell = kommentierte_dateien(wurzel)
    genannt = protokollierte(wurzel)
    gespeichert = gespeicherte_abdeckung(wurzel)
    meldungen: list[str] = []
    for pfad, abdruck in aktuell.items():
        if pfad not in genannt:
            meldungen.append(f"ohne Protokoll: {pfad}")
        elif gespeichert.get(pfad) != abdruck:
            meldungen.append(f"Kommentare seit der Übernahme geändert: {pfad}")
    return meldungen


def schreibe_abdeckung(wurzel: Path) -> int:
    """Hält den Fingerabdruck jeder protokollierten Datei fest; liefert ihre Zahl."""
    genannt = protokollierte(wurzel)
    dateien = {p: a for p, a in kommentierte_dateien(wurzel).items() if p in genannt}
    inhalt = json.dumps({"dateien": dateien}, indent=1, sort_keys=True) + "\n"
    (wurzel / ABDECKUNG).write_text(inhalt, encoding="utf-8")
    return len(dateien)


def main(argv: list[str] | None = None) -> int:
    """Exit 0, wenn jede kommentierte Datei übernommen und unverändert ist."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--wurzel", type=Path, default=WURZEL)
    parser.add_argument(
        "--schreiben", action="store_true", help="Fingerabdrücke festhalten"
    )
    args = parser.parse_args(argv)
    if args.schreiben:
        print(f"{schreibe_abdeckung(args.wurzel)} Dateien festgehalten")
    meldungen = befunde(args.wurzel)
    for zeile in meldungen:
        print(zeile)
    if meldungen:
        return 1
    print("Kommentarwissen übernommen")
    return 0


if __name__ == "__main__":
    sys.exit(main())
