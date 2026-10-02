"""Baut die Website aus Berichten und State, ohne Sammeln und ohne LLM."""
from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

from ..config import load_config
from .html import render_site


def main(argv: list[str] | None = None) -> int:
    """Rendert `site/` unter `--root`; Exit 0 ohne Ausfall, sonst 1."""
    parser = argparse.ArgumentParser(description="Website neu bauen")
    parser.add_argument("--root", type=Path, default=Path("."))
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s")
    root = args.root.resolve()
    ausfaelle = render_site(root / "site", root / "data" / "reports",
                            load_config(root))
    ausgabe = os.environ.get("GITHUB_OUTPUT")
    if ausgabe:
        with open(ausgabe, "a", encoding="utf-8") as datei:
            datei.write("gerendert=true\n")
    for ausfall in ausfaelle:
        print(f"AUSFALL {ausfall.teil}: {ausfall.grund}", file=sys.stderr)
    return 1 if ausfaelle else 0


if __name__ == "__main__":
    raise SystemExit(main())
