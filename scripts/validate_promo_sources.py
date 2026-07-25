#!/usr/bin/env python3
"""Check every source in config/promo_sources.yaml and report its health.

Mirrors scripts/validate_sources.py but for the Promo-Uebersicht branch
(consumer Aktionen pages, snapshot-fetched - see collect/promo_snapshot.py),
which is intentionally NOT covered by the main validate_sources.py since it
reads a different config file with a different schema.

Usage: python scripts/validate_promo_sources.py [--root .]
Exit code 0 always (informational tool); prints a table + summary.
"""
from __future__ import annotations

import argparse
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from telco_radar.collect.promo_snapshot import fetch_snapshot  # noqa: E402
from telco_radar.config import load_config  # noqa: E402
from telco_radar.promo_config import load_promo_config  # noqa: E402


def check(src, http_cfg):
    if src.kind == "skip":
        return ("SKIP", 0, src.note or "dokumentierter Sonderfall, nicht automatisiert")
    try:
        text = fetch_snapshot(src.url, src.kind, http_cfg)
        return ("OK" if text.strip() else "EMPTY", len(text), "")
    except Exception as exc:  # noqa: BLE001
        return ("FAIL", 0, f"{type(exc).__name__}: {str(exc)[:80]}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("."))
    args = parser.parse_args()
    root = args.root.resolve()

    promo_cfg = load_promo_config(root)
    http_cfg = load_config(root).settings.get("http", {})

    print(f"{'STATUS':7} {'CHARS':>6}  {'TIER':4} {'NAME':24} URL")
    print("-" * 110)
    counts = {"OK": 0, "EMPTY": 0, "FAIL": 0, "SKIP": 0}
    with ThreadPoolExecutor(max_workers=6) as pool:
        futures = {pool.submit(check, s, http_cfg): s for s in promo_cfg.sources}
        for fut in as_completed(futures):
            src = futures[fut]
            status, n, err = fut.result()
            counts[status] += 1
            print(f"{status:7} {n:>6}  {src.tier:<4} {src.name[:24]:24} {src.url}  {err}")

    total = sum(counts.values())
    print("-" * 110)
    print(f"Total: {total} | OK: {counts['OK']} | EMPTY: {counts['EMPTY']} "
          f"| FAIL: {counts['FAIL']} | SKIP: {counts['SKIP']}")
    print("\nHinweis: EMPTY/FAIL bei 'js'-Quellen kann Bot-Schutz oder ein "
          "geaendertes Seitenlayout bedeuten - nicht automatisch die Quelle "
          "entfernen, siehe TELCO_RADAR_HANDOVER.md Abschnitt zu Quellen.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
