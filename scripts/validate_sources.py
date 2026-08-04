#!/usr/bin/env python3
"""Check every source in the watchlist + news sources and report its health.

Usage: python scripts/validate_sources.py [--root .] [--lookback 8]
Exit code 0 always (informational tool); prints a table + summary.

Item- und Datums-Zahlen allein reichen nicht: stc lieferte 40 sauber datierte
Meldungen, deren neueste von 2022 war - in einer reinen OK/ITEMS/DATED-Tabelle
sieht das kerngesund aus, obwohl die Quelle fuer den Wochenbericht tot ist.
Deshalb stehen hier auch das neueste Datum und die Zahl der Meldungen im
Frischefenster; Quellen ohne frische Meldung werden unten aufgelistet.
"""
from __future__ import annotations

import argparse
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from telco_radar.collect import collect_source  # noqa: E402
from telco_radar.config import load_config  # noqa: E402


def check(source, region, operator, origin, http_cfg, lookback):
    if source.kind == "official":
        return ("SKIP", 0, 0, None, 0, "reference-only (not crawled)")
    try:
        items = collect_source(source, region, operator, origin, http_cfg)
        dates = [i.published for i in items if i.published]
        newest = max(dates) if dates else None
        fresh = sum(1 for i in items
                    if i.age_days() is not None and -1 <= i.age_days() <= lookback)
        return ("OK" if items else "EMPTY", len(items), len(dates), newest, fresh, "")
    except Exception as exc:  # noqa: BLE001
        return ("FAIL", 0, 0, None, 0, f"{type(exc).__name__}: {str(exc)[:80]}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--lookback", type=int, default=None,
                        help="Frischefenster in Tagen (Standard: lookback_days "
                             "aus config/settings.yaml)")
    args = parser.parse_args()

    cfg = load_config(args.root.resolve())
    http_cfg = cfg.settings.get("http", {})
    lookback = args.lookback or int(cfg.settings.get("lookback_days", 8))

    jobs = []
    for op in cfg.operators:
        for src in op.sources:
            jobs.append((src, op.region_key, op.name, "operator"))
    for src in cfg.news_sources:
        jobs.append((src, "global", None, "industry_news"))
    # Themenquellen (config/tech_sources.yaml) gehoeren in denselben
    # Gesundheits-Check - sie sind seit dem Quellen-Ausbau eine dritte
    # Signalebene und keine Nebensache.
    for src in cfg.tech_sources:
        jobs.append((src, src.theme, src.name, "tech_watch"))

    print(f"{'STATUS':7} {'ITEMS':>5} {'DATED':>5} {'NEWEST':>11} {'FRESH':>5}  "
          f"{'NAME':24} URL")
    print("-" * 130)
    counts = {"OK": 0, "EMPTY": 0, "FAIL": 0, "SKIP": 0}
    stale: list[tuple[str, str, str]] = []
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = {
            pool.submit(check, s, r, o, g, http_cfg, lookback): (s, o)
            for s, r, o, g in jobs
        }
        for fut in as_completed(futures):
            src, operator = futures[fut]
            status, n, dated, newest, fresh, err = fut.result()
            counts[status] += 1
            name = (operator or src.name or "")[:24]
            newest_txt = newest.date().isoformat() if newest else "-"
            print(f"{status:7} {n:>5} {dated:>5} {newest_txt:>11} {fresh:>5}  "
                  f"{name:24} {src.url}  {err}")
            if status == "OK" and not fresh:
                stale.append((name, newest_txt, src.url))

    total = sum(counts.values())
    print("-" * 130)
    print(f"Total: {total} | OK: {counts['OK']} | EMPTY: {counts['EMPTY']} "
          f"| FAIL: {counts['FAIL']}")

    if stale:
        print(f"\nLiefern Inhalte, aber nichts im {lookback}-Tage-Fenster "
              f"({len(stale)}) - jeweils pruefen, ob der Betreiber wirklich "
              f"nicht publiziert oder ob die Seite/das Datum falsch gelesen wird:")
        for name, newest_txt, url in sorted(stale, key=lambda x: x[1]):
            print(f"  {name:24} neuestes {newest_txt:>11}  {url}")
    if counts["FAIL"] or counts["EMPTY"]:
        print("\nHint: EMPTY newsroom pages are often JavaScript-rendered. "
              "Options: find the operator's RSS feed, add an item_selector, "
              "or rely on the industry-news layer for that operator.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
