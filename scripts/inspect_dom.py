#!/usr/bin/env python3
"""Dump the rendered DOM's anchor structure for specific sources, so a real
item_selector / hint fix can be designed by hand. Diagnostic only, run in CI
(needs real network + Playwright) - never committed logic depends on this.

Usage: python scripts/inspect_dom.py --only "Deutsche Telekom" "TIM" ...
"""
from __future__ import annotations

import argparse
import io
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from bs4 import BeautifulSoup  # noqa: E402

from telco_radar.collect.newsroom_js import render_html  # noqa: E402
from telco_radar.collect.http import BROWSER_UA  # noqa: E402
from telco_radar.config import load_config  # noqa: E402


def inspect(url: str, ua: str, item_selector: str | None = None) -> str:
    out = io.StringIO()
    p = lambda *a: print(*a, file=out)  # noqa: E731

    p(f"\n===== {url} =====")
    try:
        html = render_html(url, timeout_s=35.0, ua=ua)
    except Exception as exc:  # noqa: BLE001
        p(f"RENDER FAILED: {type(exc).__name__}: {exc}")
        return out.getvalue()

    soup = BeautifulSoup(html, "html.parser")

    if item_selector:
        matched = soup.select(item_selector)
        p(f"item_selector {item_selector!r} matched {len(matched)} elements")
        for node in matched[:2]:
            p(f"  --- raw HTML of one matched element ---\n{str(node)[:1500]}")
        if not matched:
            return out.getvalue()

    anchors = soup.find_all("a")
    p(f"total <a> tags: {len(anchors)}")

    base_host = urlsplit(url).netloc.removeprefix("www.")
    with_href = [a for a in anchors if a.get("href")]
    p(f"<a> with non-empty href: {len(with_href)}")

    host_counter = Counter()
    for a in with_href:
        href = a["href"].strip()
        if href.startswith(("http://", "https://")):
            host_counter[urlsplit(href).netloc.removeprefix("www.")] += 1
        else:
            host_counter["(relative -> " + base_host + ")"] += 1
    p("href hosts:", dict(host_counter.most_common(5)))

    # Longest-text anchors are usually the real article links/titles.
    scored = []
    for a in with_href:
        text = " ".join(a.get_text(" ", strip=True).split())
        if len(text) >= 20:
            scored.append((len(text), text[:90], a["href"][:110]))
    scored.sort(reverse=True)
    p(f"anchors with text >= 20 chars: {len(scored)}")
    for _, text, href in scored[:12]:
        p(f"  · {text}  ->  {href}")

    # Class-name signal on likely article containers.
    class_counter = Counter()
    for tag in soup.find_all(True, class_=True):
        for cls in tag.get("class", []):
            low = cls.lower()
            if any(k in low for k in ("press", "news", "article", "release",
                                       "teaser", "card", "list-item", "listitem",
                                       "media", "story")):
                class_counter[cls] += 1
    p("promising class names:", dict(class_counter.most_common(10)))
    return out.getvalue()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--only", required=True,
                        help="Comma-separated operator names/substrings "
                             "(comma-separated so shell quoting of names "
                             "like 'e&' or multi-word names is a non-issue)")
    parser.add_argument("--workers", type=int, default=6)
    args = parser.parse_args()

    cfg = load_config(args.root.resolve())
    ua = cfg.settings.get("http", {}).get("user_agent", BROWSER_UA)
    needles = [n.strip().lower() for n in args.only.split(",") if n.strip()]

    jobs = []
    seen = set()
    for op in cfg.operators:
        if not any(n in op.name.lower() for n in needles):
            continue
        for src in op.sources:
            if src.kind != "newsroom_js" or src.url in seen:
                continue
            seen.add(src.url)
            jobs.append((op.name, src.url, src.item_selector))

    print(f"Inspecting {len(jobs)} sources with {args.workers} workers...")
    results = {}
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(inspect, url, ua, sel): (name, url)
                  for name, url, sel in jobs}
        for fut in as_completed(futures):
            name, url = futures[fut]
            results[(name, url)] = fut.result()

    for name, url, _sel in jobs:  # print in stable, requested order
        print(f"\n######## {name} ########")
        print(results[(name, url)])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
