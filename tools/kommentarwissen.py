"""Abdeckung der Kommentarübernahme: jede kommentierte Datei hat ihr Protokoll.

Vor dem Löschen der Kommentare muss ihr Wissen unter `outputs/kommentarwissen/`
stehen. Das Werkzeug meldet Dateien mit Wissenskommentaren ohne Abschnitt oder mit
leerem Abschnitt im Protokoll und Dateien, deren Kommentare sich seit der
Übernahme geändert haben, ohne dass ihr Abschnitt mitgezogen ist.
"""

from __future__ import annotations

import argparse
import ast
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
CODES = r"[A-Z]+[0-9]+(?:[\s,]+[A-Z]+[0-9]+)*"
SCHALTER = rf"noqa(?::\s*{CODES})?|type:\s*ignore(?:\[[^\]]*\])?|pragma:\s*no cover"
WERKZEUGKOMMENTAR = re.compile(rf"#\s*(?:{SCHALTER})\s*$")
SHEBANG = "#!"
UEBERSCHRIFT = re.compile(r"^### `([^`]+)`\s*$")
CODEZAUN = re.compile(r"^\s*(```|~~~)")
NICHTS = re.compile(r"nichts übernommen", re.IGNORECASE)
HTML_KOMMENTAR = re.compile(r"<!--.*?-->", re.DOTALL)
WORT = re.compile(r"\w*[^\W\d_]\w*")
MINDESTWOERTER = 3
BASEN = ("origin/main", "HEAD")
MODULEBENE = "<modul>"


class Unlesbar(Exception):
    """Eine Python-Datei lässt sich nicht in Tokens oder Syntaxbaum zerlegen."""


def _kommentar_tokens(text: str) -> list[tokenize.TokenInfo]:
    try:
        tokens = list(tokenize.generate_tokens(io.StringIO(text).readline))
    except (tokenize.TokenError, SyntaxError) as fehler:
        raise Unlesbar(str(fehler)) from fehler
    return [
        t
        for t in tokens
        if t.type == tokenize.COMMENT
        and not WERKZEUGKOMMENTAR.fullmatch(t.string)
        and not (t.start[0] == 1 and t.string.startswith(SHEBANG))
    ]


def wissenskommentare(text: str) -> list[str]:
    """Alle `#`-Kommentare außer reinen Werkzeugschaltern und der Shebang-Zeile."""
    return [t.string for t in _kommentar_tokens(text)]


def _bereiche(text: str) -> list[tuple[int, int, str]]:
    try:
        baum = ast.parse(text)
    except SyntaxError as fehler:
        raise Unlesbar(str(fehler)) from fehler
    zeilen = text.splitlines()
    bereiche: list[tuple[int, int, str]] = []

    def anfang(kind: ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef) -> int:
        zeile = min([kind.lineno, *(d.lineno for d in kind.decorator_list)])
        while zeile > 1 and zeilen[zeile - 2].lstrip().startswith("#"):
            zeile -= 1
        return zeile

    def besuche(knoten: ast.AST, praefix: str) -> None:
        for kind in ast.iter_child_nodes(knoten):
            if isinstance(kind, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
                name = f"{praefix}{kind.name}"
                ende = kind.end_lineno or kind.lineno
                bereiche.append((anfang(kind), ende, name))
                besuche(kind, f"{name}.")
            else:
                besuche(kind, praefix)

    besuche(baum, "")
    return bereiche


def _ort(zeile: int, bereiche: list[tuple[int, int, str]]) -> str:
    passend = [b for b in bereiche if b[0] <= zeile <= b[1]]
    return min(passend, key=lambda b: b[1] - b[0])[2] if passend else MODULEBENE


def fingerabdruck(text: str) -> str:
    """sha256 über Kommentare samt umgebender Funktion oder Klasse, in Reihenfolge."""
    bereiche = _bereiche(text)
    teile = [
        f"{_ort(t.start[0], bereiche)}\t{t.string}" for t in _kommentar_tokens(text)
    ]
    return hashlib.sha256("\n".join(teile).encode()).hexdigest()


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
        text = datei.read_text(encoding="utf-8")
        try:
            if wissenskommentare(text):
                ergebnis[pfad] = fingerabdruck(text)
        except Unlesbar as fehler:
            raise Unlesbar(f"{pfad}: {fehler}") from fehler
    return ergebnis


def abschnitte(wurzel: Path) -> dict[str, str]:
    """Text je protokolliertem Pfad; Überschriften in Codeblöcken zählen nicht."""
    gesammelt: dict[str, list[str]] = {}
    for protokoll in sorted((wurzel / PROTOKOLLE).glob("*.md")):
        aktuell: list[str] | None = None
        im_code = False
        for zeile in protokoll.read_text(encoding="utf-8").splitlines():
            if CODEZAUN.match(zeile):
                im_code = not im_code
                continue
            if not im_code and zeile.startswith("#"):
                treffer = UEBERSCHRIFT.match(zeile)
                aktuell = gesammelt.setdefault(treffer[1], []) if treffer else None
                continue
            if aktuell is not None:
                aktuell.append(zeile)
    return {
        pfad: HTML_KOMMENTAR.sub("", "\n".join(z)).strip()
        for pfad, z in gesammelt.items()
    }


def protokollierte(wurzel: Path) -> set[str]:
    """Pfade, die in einem Protokoll eine eigene Überschrift haben."""
    return set(abschnitte(wurzel))


def _abschnitt_fehlt(text: str | None) -> str | None:
    if text is None:
        return "ohne Protokoll"
    if len(WORT.findall(NICHTS.sub("", text))) >= MINDESTWOERTER:
        return None
    if NICHTS.search(text):
        return "„nichts übernommen“ ohne Grund"
    return "leerer Abschnitt"


def _abdruck(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def gespeicherte_abdeckung(wurzel: Path) -> dict[str, dict[str, str]]:
    """Fingerabdrücke von Kommentaren und Abschnitt je Datei zur Übernahme."""
    datei = wurzel / ABDECKUNG
    if not datei.exists():
        return {}
    daten = json.loads(datei.read_text(encoding="utf-8"))["dateien"]
    return {p: e for p, e in daten.items() if isinstance(e, dict)}


def befunde(wurzel: Path) -> list[str]:
    """Eine Zeile je Datei, deren Kommentarwissen nicht übernommen ist."""
    texte = abschnitte(wurzel)
    gespeichert = gespeicherte_abdeckung(wurzel)
    meldungen: list[str] = []
    for pfad, abdruck in kommentierte_dateien(wurzel).items():
        text = texte.get(pfad)
        eintrag = gespeichert.get(pfad, {})
        if grund := _abschnitt_fehlt(text):
            meldungen.append(f"{grund}: {pfad}")
        elif eintrag.get("kommentare") != abdruck:
            meldungen.append(f"Kommentare seit der Übernahme geändert: {pfad}")
        elif eintrag.get("protokoll") != _abdruck(text or ""):
            meldungen.append(f"Abschnitt seit dem Festhalten geändert: {pfad}")
    return meldungen


def _basis(wurzel: Path) -> str | None:
    for name in BASEN:
        lauf = subprocess.run(
            ["git", "rev-parse", "--verify", "-q", f"{name}^{{commit}}"],
            cwd=wurzel,
            capture_output=True,
            text=True,
        )
        if lauf.returncode == 0:
            return name
    return None


def neu_gegen_basis(wurzel: Path, pfad: str) -> bool:
    """Wahr, wenn die Basis die Datei nicht kennt oder sie dort ohne Wissen ist."""
    basis = _basis(wurzel)
    if basis is None:
        return True
    lauf = subprocess.run(
        ["git", "show", f"{basis}:{pfad}"],
        cwd=wurzel,
        capture_output=True,
        text=True,
    )
    if lauf.returncode != 0:
        return True
    try:
        return not wissenskommentare(lauf.stdout)
    except Unlesbar:
        return False


def schreibe_abdeckung(wurzel: Path) -> tuple[int, list[tuple[str, str]]]:
    """Hält Dateien fest, deren Abschnitt mit den Kommentaren mitgezogen ist.

    Haben sich die Kommentare einer festgehaltenen Datei geändert, ihr Abschnitt
    aber nicht, bleibt der alte Stand stehen. Ohne früheren Eintrag hält es nur
    Dateien fest, die in der Basis fehlen oder dort ohne Kommentarwissen sind.
    """
    texte = abschnitte(wurzel)
    alt = gespeicherte_abdeckung(wurzel)
    neu: dict[str, dict[str, str]] = {}
    liegen: list[tuple[str, str]] = []
    for pfad, abdruck in kommentierte_dateien(wurzel).items():
        text = texte.get(pfad)
        vorher = alt.get(pfad, {})
        if _abschnitt_fehlt(text):
            if vorher:
                neu[pfad] = vorher
            liegen.append((pfad, "Abschnitt fehlt oder ist leer"))
            continue
        eintrag = {"kommentare": abdruck, "protokoll": _abdruck(text or "")}
        if not vorher:
            if neu_gegen_basis(wurzel, pfad):
                neu[pfad] = eintrag
            else:
                liegen.append(
                    (pfad, "kein früherer Eintrag, Kommentare schon in der Basis")
                )
            continue
        geaendert = vorher.get("kommentare") != abdruck
        if geaendert and vorher.get("protokoll") == eintrag["protokoll"]:
            neu[pfad] = vorher
            liegen.append((pfad, "Abschnitt unverändert"))
            continue
        neu[pfad] = eintrag
    inhalt = json.dumps({"dateien": neu}, indent=1, sort_keys=True) + "\n"
    (wurzel / ABDECKUNG).write_text(inhalt, encoding="utf-8")
    return len(neu) - sum(1 for p, _ in liegen if p in neu), liegen


def main(argv: list[str] | None = None) -> int:
    """Exit 0, wenn jede kommentierte Datei übernommen und unverändert ist."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--wurzel", type=Path, default=WURZEL)
    parser.add_argument(
        "--schreiben", action="store_true", help="Fingerabdrücke festhalten"
    )
    args = parser.parse_args(argv)
    if args.schreiben:
        anzahl, liegen = schreibe_abdeckung(args.wurzel)
        print(f"{anzahl} Dateien festgehalten")
        for pfad, grund in liegen:
            print(f"nicht festgehalten, {grund}: {pfad}")
    meldungen = befunde(args.wurzel)
    for zeile in meldungen:
        print(zeile)
    if meldungen:
        return 1
    print("Kommentarwissen übernommen")
    return 0


if __name__ == "__main__":
    sys.exit(main())
