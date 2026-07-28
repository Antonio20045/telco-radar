#!/usr/bin/env python3
"""Dump the real (rendered) DOM structure of one or more operator sources.

Diagnostic tool for figuring out why a newsroom/newsroom_js source returns
EMPTY or FAIL: prints how many <a> tags exist, a sample of same-domain anchors
with their text/class, and - if the watchlist already has an item_selector -
the raw HTML of the matched elements plus the nearest ancestor that carries a
real <a href> (useful for card layouts where the title is not itself a link).

Usage:
    python scripts/inspect_dom.py --names "KT,Optus" [--root .] [--timeout 30]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from bs4 import BeautifulSoup  # noqa: E402

from telco_radar.collect.http import BROWSER_UA, fetch  # noqa: E402
from telco_radar.collect.newsroom_js import render_html  # noqa: E402
from telco_radar.config import load_config  # noqa: E402


def dump_source(op_name: str, source, timeout: float) -> None:
    print(f"\n{'=' * 90}\n{op_name} [{source.kind}] — {source.url}\n{'=' * 90}")

    if source.kind == "newsroom_js" or source.kind == "official":
        try:
            html = render_html(source.url, timeout, BROWSER_UA)
        except Exception as exc:  # noqa: BLE001
            print(f"  Playwright render FAILED: {type(exc).__name__}: {exc}")
            return
    else:
        try:
            resp = fetch(source.url, {"timeout_seconds": timeout})
            html = resp.text
        except Exception as exc:  # noqa: BLE001
            print(f"  static fetch FAILED: {type(exc).__name__}: {exc}")
            return

    soup = BeautifulSoup(html, "html.parser")
    base_host = urlsplit(source.url).netloc.removeprefix("www.")
    all_links = soup.find_all("a", href=True)
    same_host = [
        a for a in all_links
        if (urlsplit(a["href"]).netloc.removeprefix("www.") or base_host)
        in (base_host, "") or base_host in urlsplit(a["href"]).netloc
    ]
    print(f"  DOM size: {len(html)} chars | <a> tags: {len(all_links)} "
          f"| same-host-ish: {len(same_host)}")

    print("  --- sample anchors (first 60 with non-trivial text) ---")
    shown = 0
    for a in all_links:
        text = " ".join(a.get_text(" ", strip=True).split())
        if len(text) < 10:
            continue
        cls = " ".join(a.get("class") or [])
        print(f"    href={a['href'][:90]!r} class={cls!r} text={text[:70]!r}")
        shown += 1
        if shown >= 60:
            break
    if shown == 0:
        print("    (no anchor had >=10 chars of text - likely icon-only nav "
              "or a card layout where the title lives outside the <a>)")

    if source.item_selector:
        matched = soup.select(source.item_selector)
        print(f"  --- item_selector {source.item_selector!r}: "
              f"{len(matched)} matches ---")
        for i, node in enumerate(matched[:5]):
            print(f"    [{i}] raw: {str(node)[:300]}")
            if not node.find("a", href=True):
                ancestor = node.find_parent(
                    lambda t: t.find("a", href=True) is not None
                )
                if ancestor is not None:
                    link = ancestor.find("a", href=True)
                    print(f"        nearest ancestor <a>: "
                          f"href={link['href'][:90]!r} "
                          f"text={link.get_text(' ', strip=True)[:70]!r}")
                else:
                    print("        no ancestor with <a href> found either")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--names", required=True,
                       help="Comma-separated operator names")
    parser.add_argument("--timeout", type=float, default=30.0)
    args = parser.parse_args()

    cfg = load_config(args.root.resolve())
    wanted = {n.strip() for n in args.names.split(",") if n.strip()}
    missing = set(wanted)

    for op in cfg.operators:
        if op.name not in wanted:
            continue
        missing.discard(op.name)
        for source in op.sources:
            dump_source(op.name, source, args.timeout)

    if missing:
        print(f"\nWARNING: no operator matched: {', '.join(sorted(missing))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
