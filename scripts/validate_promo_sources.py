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


def check(page, http_cfg):
    if page.kind == "skip":
        return ("SKIP", 0, page.note or "dokumentierter Sonderfall, nicht automatisiert")
    try:
        snap = fetch_snapshot(page.url, page.kind, http_cfg)
        text = snap["text"]
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

    # Geprueft wird je SEITE, nicht je Marke: seit dem 08.08.2026 hat eine
    # Marke mehrere (siehe config/promo_sources.yaml). Eine Marke, deren
    # Leitseite laeuft und deren drei weitere Seiten tot sind, saehe sonst
    # gesund aus.
    seiten = [(s, p) for s in promo_cfg.sources for p in s.pages]
    print(f"{'STATUS':7} {'CHARS':>6}  {'TIER':4} {'NAME':24} URL")
    print("-" * 110)
    counts = {"OK": 0, "EMPTY": 0, "FAIL": 0, "SKIP": 0}
    je_marke: dict[str, list[str]] = {}
    with ThreadPoolExecutor(max_workers=6) as pool:
        futures = {pool.submit(check, p, http_cfg): (s, p) for s, p in seiten}
        for fut in as_completed(futures):
            src, page = futures[fut]
            status, n, err = fut.result()
            counts[status] += 1
            je_marke.setdefault(src.name, []).append(status)
            print(f"{status:7} {n:>6}  {src.tier:<4} {src.name[:24]:24} "
                  f"{page.url}  {err}")

    total = sum(counts.values())
    print("-" * 110)
    print(f"Seiten: {total} bei {len(promo_cfg.sources)} Marken | OK: {counts['OK']} "
          f"| EMPTY: {counts['EMPTY']} | FAIL: {counts['FAIL']} | SKIP: {counts['SKIP']}")
    blind = [m for m, st in je_marke.items() if "OK" not in st]
    if blind:
        print(f"\nMarken OHNE eine einzige lieferfaehige Seite ({len(blind)}): "
              + ", ".join(sorted(blind)))
    print("\nHinweis: EMPTY/FAIL bei 'js'-Quellen kann Bot-Schutz oder ein "
          "geaendertes Seitenlayout bedeuten - nicht automatisch die Quelle "
          "entfernen, siehe TELCO_RADAR_HANDOVER.md Abschnitt zu Quellen.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
