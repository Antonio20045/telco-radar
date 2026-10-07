"""Klick-Ergebnisse der Matrix ins Repo legen (letzter Job von ``klick.yml``).

AUFRUF
------
    PYTHONPATH=src python scripts/klick_ablegen.py --quelle klick-artefakte [--root .]

Liest alle Ergebnisdateien unter ``--quelle`` (je Anbieter ein Artefakt), legt sie nach
``data/state/klick/<schluessel>.json`` und führt dort den Lesestand fort
(``telco_radar.analyze.klick_ablage``). Gibt es ``--quelle`` nicht (kein Artefakt),
bleibt alles, wie es war: Exit-Code 0. Ist eine Datei unlesbar oder abgelehnt, sind
die lesbaren trotzdem abgelegt und der Exit-Code ist 1. Dieses Skript stellt die Uhr.
"""

from __future__ import annotations

import argparse
import sys
from datetime import UTC, datetime
from pathlib import Path

from telco_radar.analyze.klick_ablage import lege_ab
from telco_radar.collect.geraete.klickergebnis import ORDNER, lies_ergebnisse
from telco_radar.geraete_config import lade_katalog

FEHLER_DATEI = 1


def main(argumente: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", default=".", type=Path)
    parser.add_argument("--quelle", required=True, type=Path)
    args = parser.parse_args(argumente)
    if not args.quelle.is_dir():
        print(f"Klick-Ablage: kein Ordner {args.quelle}, nichts abgelegt")
        return 0
    heute = datetime.now(UTC).date().isoformat()
    ergebnisse, unlesbar = lies_ergebnisse(args.quelle)
    ziel = args.root / ORDNER
    ablage = lege_ab(ergebnisse, ziel, lade_katalog(args.root), heute)
    for daten in ergebnisse:
        grund = f" ({daten.get('grund')})" if daten.get("grund") else ""
        print(f"{daten.get('anbieter')}: {daten.get('laufstatus')}{grund}")
    print(f"Klick-Ablage: {len(ablage.abgelegt)} Dateien nach {ziel}")
    for zeile in [*unlesbar, *ablage.abgelehnt]:
        print(f"Klick-Ablage: {zeile}", file=sys.stderr)
    return FEHLER_DATEI if unlesbar or ablage.abgelehnt else 0


if __name__ == "__main__":
    sys.exit(main())
