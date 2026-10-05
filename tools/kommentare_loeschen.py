"""Löscht jeden ``#``-Kommentar, den Stufe 0 als ``kommentar`` zählt.

Ein Schalter mit angehängter Begründung schrumpft auf den Schalter. Je Datei vergleicht
das Werkzeug den Syntaxbaum vor und nach dem Löschen samt ``ruff format`` und schreibt
nur bei unverändertem Baum. Vorher muss ``tools/kommentarwissen.py`` ohne Befund sein.
"""

from __future__ import annotations

import argparse
import ast
import importlib
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import libcst as cst

WURZEL = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(WURZEL / "scripts"))
sys.path.insert(0, str(WURZEL / "tools"))
regeln = importlib.import_module("waechter_regeln")
kommentare = importlib.import_module("waechter_kommentare")
kommentarwissen = importlib.import_module("kommentarwissen")


class SyntaxbaumGeaendert(Exception):
    """Das Löschen hätte den Syntaxbaum einer Datei verändert."""


def neuer_kommentar(kommentar: str) -> str | None:
    """Der Kommentar, der stehen bleibt, oder ``None``, wenn er ganz wegfällt."""
    if kommentare.ist_erlaubter_kommentar(kommentar, 0, ""):
        return kommentar
    vorn = kommentare.SCHALTER_VORN.match(kommentar)
    return vorn.group(0).rstrip() if vorn else None


class _Loescher(cst.CSTTransformer):
    def __init__(self, pfad: str) -> None:
        super().__init__()
        self.pfad = pfad
        self.shebang: cst.EmptyLine | None = None
        self.geloescht = 0

    def visit_Module(self, node: cst.Module) -> None:
        kopf = node.header[0] if node.header else None
        wert = kopf.comment.value if kopf and kopf.comment else ""
        if kommentare.ist_erlaubter_kommentar(wert, 1, self.pfad):
            self.shebang = kopf

    def leave_EmptyLine(
        self, original_node: cst.EmptyLine, updated_node: cst.EmptyLine
    ) -> cst.EmptyLine | cst.RemovalSentinel:
        if updated_node.comment is None or original_node is self.shebang:
            return updated_node
        neu = neuer_kommentar(updated_node.comment.value)
        if neu == updated_node.comment.value:
            return updated_node
        self.geloescht += 1
        if neu is None:
            return cst.RemovalSentinel.REMOVE
        return updated_node.with_changes(comment=cst.Comment(neu))

    def leave_TrailingWhitespace(
        self,
        original_node: cst.TrailingWhitespace,
        updated_node: cst.TrailingWhitespace,
    ) -> cst.TrailingWhitespace:
        if updated_node.comment is None:
            return updated_node
        neu = neuer_kommentar(updated_node.comment.value)
        if neu == updated_node.comment.value:
            return updated_node
        self.geloescht += 1
        if neu is None:
            leer = cst.SimpleWhitespace("")
            return updated_node.with_changes(whitespace=leer, comment=None)
        return updated_node.with_changes(comment=cst.Comment(neu))


@dataclass(frozen=True)
class Ergebnis:
    """Neuer Text einer Datei und die Zahl gelöschter oder gekürzter Kommentare."""

    text: str
    geloescht: int


IMPORTBLOECKE = ["check", "--select", "I001", "--fix-only"]


def formatiere(text: str, pfad: str, wurzel: Path, importe: bool = True) -> str:
    """Der Text nach ``ruff format`` mit den Repo-Einstellungen, mit ``importe``
    vorher nach der Importsortierung.

    Ein gelöschter Kommentar zwischen Importen lässt zwei Blöcke zusammenfallen."""
    for art in ([IMPORTBLOECKE] if importe else []) + [["format"]]:
        befehl = [sys.executable, "-m", "ruff", *art, "--stdin-filename", pfad, "-"]
        lauf = subprocess.run(
            befehl, input=text, cwd=wurzel, capture_output=True, text=True, check=True
        )
        text = lauf.stdout
    return text


def loesche(text: str, pfad: str, wurzel: Path) -> Ergebnis:
    """Löscht die Kommentare eines Quelltexts; scheitert bei geändertem Syntaxbaum.

    Ordnet die Importsortierung Namen um, bleibt es bei ``ruff format`` allein."""
    loescher = _Loescher(pfad)
    roh = cst.parse_module(text).visit(loescher).code
    if not loescher.geloescht:
        return Ergebnis(text, 0)
    baum = ast.dump(ast.parse(text))
    for importe in (True, False):
        neu = formatiere(roh, pfad, wurzel, importe)
        if ast.dump(ast.parse(neu)) == baum:
            return Ergebnis(neu, loescher.geloescht)
    raise SyntaxbaumGeaendert(pfad)


def main(argv: list[str] | None = None) -> int:
    """Exit 0, wenn jede Datei mit unverändertem Syntaxbaum durchläuft."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--wurzel", type=Path, default=WURZEL)
    parser.add_argument("--trocken", action="store_true", help="nichts schreiben")
    args = parser.parse_args(argv)
    befunde = kommentarwissen.befunde(args.wurzel)
    if befunde:
        print("Kommentarwissen nicht übernommen, nichts gelöscht:")
        print("\n".join(befunde))
        return 1
    rot = 0
    for pfad in regeln.kommentar_dateien(args.wurzel):
        datei = args.wurzel / pfad
        try:
            ergebnis = loesche(datei.read_text(encoding="utf-8"), pfad, args.wurzel)
        except SyntaxbaumGeaendert:
            print(f"{pfad}: Syntaxbaum geändert, nicht geschrieben")
            rot += 1
            continue
        if ergebnis.geloescht and not args.trocken:
            datei.write_text(ergebnis.text, encoding="utf-8")
        print(f"{pfad}: {ergebnis.geloescht} Kommentare, Syntaxbaum unverändert")
    return 1 if rot else 0


if __name__ == "__main__":
    sys.exit(main())
