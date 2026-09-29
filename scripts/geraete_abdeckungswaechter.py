"""Bündelabdeckung prüfen und den Lauf rot machen, wenn etwas fehlt.

    python scripts/geraete_abdeckungswaechter.py --root .
    python scripts/geraete_abdeckungswaechter.py --root . --bericht /tmp/a.md

Schreibt die Matrix als Markdown (nach --bericht, sonst auf stdout, und in
GitHub Actions zusätzlich in die Job-Zusammenfassung) und endet mit
Rückgabecode 1, sobald es einen Befund gibt. Rechnet nichts selbst, das
macht `analyze/buendel_abdeckung.py`.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from telco_radar.analyze.buendel_abdeckung import (  # noqa: E402
    als_markdown,
    lade_pflicht,
    lade_und_pruefe,
)

EXIT_GRUEN = 0
EXIT_ROT = 1


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Bündelabdeckung prüfen")
    p.add_argument("--root", default=".")
    p.add_argument("--bericht", help="Markdown-Bericht hierhin schreiben")
    args = p.parse_args(argv)
    root = Path(args.root)

    ergebnis = lade_und_pruefe(root)
    text = als_markdown(
        ergebnis, lade_pflicht(root / "config" / "geraete_abdeckung.yaml"))
    if args.bericht:
        Path(args.bericht).write_text(text, encoding="utf-8")
    else:
        print(text)
    zusammenfassung = os.environ.get("GITHUB_STEP_SUMMARY")
    if zusammenfassung:
        with open(zusammenfassung, "a", encoding="utf-8") as f:
            f.write(text)
    for befund in ergebnis.befunde:
        # Eine Annotation je Befund: sie steht oben auf der Laufseite.
        print(f"::error::{befund.text}")
    return EXIT_ROT if ergebnis.rot else EXIT_GRUEN


if __name__ == "__main__":
    sys.exit(main())
