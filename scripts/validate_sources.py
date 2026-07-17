#!/usr/bin/env python3
"""Check every source in the watchlist + news sources and report its health.

Usage: python scripts/validate_sources.py [--root .]
Exit code 0 always (informational tool); prints a table + summary.
"""
from __future__ import annotations

import argparse
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from telco_radar.collect.newsroom import collect_newsroom  # noqa: E402
from telco_radar.collect.newsroom_js import collect_newsroom_js  # noqa: E402
from telco_radar.collect.json_api import collect_json  # noqa: E402
from telco_radar.collect.rss import collect_rss  # noqa: E402
from telco_radar.config import load_config  # noqa: E402


_COLLECTORS = {
    "rss": collect_rss,
    "trade_press": collect_rss,
    "json_api": collect_json,
    "newsroom": collect_newsroom,
    "newsroom_js": collect_newsroom_js,
}


def check(source, region, operator, origin, http_cfg):
    if source.kind == "official":
        return ("SKIP", 0, 0, "reference-only (not crawled)")
    fn = _COLLECTORS.get(source.kind, collect_newsroom)
    try:
        items = fn(source, region, operator, origin, http_cfg)
        dated = sum(1 for i in items if i.published)
        return ("OK" if items else "EMPTY", len(items), dated, "")
    except Exception as exc:  # noqa: BLE001
        return ("FAIL", 0, 0, f"{type(exc).__name__}: {str(exc)[:80]}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("."))
    args = parser.parse_args()

    cfg = load_config(args.root.resolve())
    http_cfg = cfg.settings.get("http", {})

    jobs = []
    for op in cfg.operators:
        for src in op.sources:
            jobs.append((src, op.region_key, op.name, "operator"))
    for src in cfg.news_sources:
        jobs.append((src, "global", None, "industry_news"))

    print(f"{'STATUS':7} {'ITEMS':>5} {'DATED':>5}  {'NAME':24} URL")
    print("-" * 110)
    counts = {"OK": 0, "EMPTY": 0, "FAIL": 0, "SKIP": 0}
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = {
            pool.submit(check, s, r, o, g, http_cfg): (s, o) for s, r, o, g in jobs
        }
        for fut in as_completed(futures):
            src, operator = futures[fut]
            status, n, dated, err = fut.result()
            counts[status] += 1
            name = (operator or src.name or "")[:24]
            print(f"{status:7} {n:>5} {dated:>5}  {name:24} {src.url}  {err}")

    total = sum(counts.values())
    print("-" * 110)
    print(f"Total: {total} | OK: {counts['OK']} | EMPTY: {counts['EMPTY']} "
          f"| FAIL: {counts['FAIL']}")
    if counts["FAIL"] or counts["EMPTY"]:
        print("\nHint: EMPTY newsroom pages are often JavaScript-rendered. "
              "Options: find the operator's RSS feed, add an item_selector, "
              "or rely on the industry-news layer for that operator.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
