#!/usr/bin/env python3
"""Dump the rendered DOM's anchor structure for specific sources, so a real
item_selector / hint fix can be designed by hand. Diagnostic only, run in CI
(needs real network + Playwright) - never committed logic depends on this.

Usage: python scripts/inspect_dom.py --only "Deutsche Telekom" "TIM" ...
"""
from __future__ import annotations

import argparse
import re
import sys
from collections import Counter
from pathlib import Path
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from bs4 import BeautifulSoup  # noqa: E402

from telco_radar.collect.newsroom_js import render_html  # noqa: E402
from telco_radar.collect.http import BROWSER_UA  # noqa: E402
from telco_radar.config import load_config  # noqa: E402


def inspect(url: str, ua: str) -> None:
    print(f"\n===== {url} =====")
    try:
        html = render_html(url, timeout_s=35.0, ua=ua)
    except Exception as exc:  # noqa: BLE001
        print(f"RENDER FAILED: {type(exc).__name__}: {exc}")
        return

    soup = BeautifulSoup(html, "html.parser")
    anchors = soup.find_all("a")
    print(f"total <a> tags: {len(anchors)}")

    base_host = urlsplit(url).netloc.removeprefix("www.")
    with_href = [a for a in anchors if a.get("href")]
    print(f"<a> with non-empty href: {len(with_href)}")

    host_counter = Counter()
    for a in with_href:
        href = a["href"].strip()
        if href.startswith(("http://", "https://")):
            host_counter[urlsplit(href).netloc.removeprefix("www.")] += 1
        else:
            host_counter["(relative -> " + base_host + ")"] += 1
    print("href hosts:", dict(host_counter.most_common(5)))

    # Longest-text anchors are usually the real article links/titles.
    scored = []
    for a in with_href:
        text = " ".join(a.get_text(" ", strip=True).split())
        if len(text) >= 20:
            scored.append((len(text), text[:90], a["href"][:110]))
    scored.sort(reverse=True)
    print(f"anchors with text >= 20 chars: {len(scored)}")
    for _, text, href in scored[:12]:
        print(f"  · {text}  ->  {href}")

    # Class-name signal on likely article containers.
    class_counter = Counter()
    for tag in soup.find_all(True, class_=True):
        for cls in tag.get("class", []):
            low = cls.lower()
            if any(k in low for k in ("press", "news", "article", "release",
                                       "teaser", "card", "list-item", "listitem",
                                       "media", "story")):
                class_counter[cls] += 1
    print("promising class names:", dict(class_counter.most_common(10)))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--only", nargs="+", required=True)
    args = parser.parse_args()

    cfg = load_config(args.root.resolve())
    ua = cfg.settings.get("http", {}).get("user_agent", BROWSER_UA)
    needles = [n.lower() for n in args.only]

    seen = set()
    for op in cfg.operators:
        if not any(n in op.name.lower() for n in needles):
            continue
        for src in op.sources:
            if src.kind != "newsroom_js" or src.url in seen:
                continue
            seen.add(src.url)
            print(f"\n######## {op.name} ########")
            inspect(src.url, ua)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
