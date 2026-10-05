"""Wochendigest per Mail, Ausnahmen per Teams, von Hand für den jüngsten Bericht.

PYTHONPATH=src python scripts/versand_von_hand.py --trocken --erzwinge --zeige
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import UTC, datetime
from pathlib import Path

from telco_radar.config import load_config
from telco_radar.versand import baue_mail, versende


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--root", type=Path, default=Path("."))
    p.add_argument(
        "--trocken", action="store_true", help="baut alles, verschickt nichts"
    )
    p.add_argument(
        "--erzwinge",
        action="store_true",
        help="ohne Ruecksicht auf Wochentag und Zustellbuch",
    )
    p.add_argument(
        "--zeige", action="store_true", help="die Textfassung auf die Konsole"
    )
    args = p.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    root = args.root.resolve()
    berichte = sorted((root / "data" / "reports").glob("*.json"))
    if not berichte:
        print("Kein Bericht gefunden.", file=sys.stderr)
        return 1
    report = json.loads(berichte[-1].read_text(encoding="utf-8"))
    if args.zeige:
        print(baue_mail(report)[1])
    bilanz = versende(
        root,
        report,
        load_config(root).settings,
        trocken=args.trocken,
        erzwinge=args.erzwinge,
        jetzt=datetime.now(UTC),
    )
    print(json.dumps(bilanz, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
