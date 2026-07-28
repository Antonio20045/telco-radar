#!/usr/bin/env python3
"""Try to find a working feed/newsroom replacement for dead operator sources.

For every targeted source this probes, in order:
  1. RSS/Atom autodiscovery (<link rel="alternate" type="application/(rss|atom)+xml">)
     on the source URL and, if different, on the operator's bare website.
  2. A list of common feed paths on the same domain (and on the website root).
  3. A longer Playwright render (for kind newsroom_js/official pages) to see
     whether a slow-loading article list eventually appears in the DOM.

It never edits the watchlist - it only reports candidates with real evidence
(entry count, latest title/date) so a human/agent can verify and apply them.

Usage:
    python scripts/rescue_sources.py [--root .] [--names "AT&T,Zain"]
    (default: every source with kind == official)
"""
from __future__ import annotations

import argparse
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.parse import urljoin, urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import feedparser  # noqa: E402
import httpx  # noqa: E402
from bs4 import BeautifulSoup  # noqa: E402

from telco_radar.collect.http import BROWSER_UA, BOT_UA  # noqa: E402
from telco_radar.config import Config, Operator, Source, load_config  # noqa: E402

COMMON_FEED_PATHS = [
    "feed", "feed/", "rss", "rss/", "rss.xml", "atom.xml", "index.rss",
    "index.xml", "news/feed", "news/rss", "news/rss.xml",
    "press/feed", "press/rss", "press-releases/feed", "press-releases/rss",
    "media/feed", "media/rss", "newsroom/feed", "newsroom/rss",
    "?feed=rss2", "?feed=rss", "feeds/posts/default", "rss/news",
]

_HEADERS_UA = (BROWSER_UA, BOT_UA)


def _get(url: str, timeout: float = 15.0) -> httpx.Response | None:
    for ua in _HEADERS_UA:
        try:
            resp = httpx.get(
                url, timeout=timeout, follow_redirects=True,
                headers={
                    "User-Agent": ua,
                    "Accept": "text/html,application/xhtml+xml,application/xml,*/*",
                    "Accept-Language": "en;q=0.9,de;q=0.8",
                },
            )
            if resp.status_code < 400:
                return resp
        except httpx.HTTPError:
            continue
    return None


def _autodiscover(html: str, base_url: str) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    found = []
    for link in soup.find_all("link", attrs={"rel": True}):
        rels = link.get("rel")
        rels = rels if isinstance(rels, list) else [rels]
        rels = [r.lower() for r in rels if r]
        ltype = (link.get("type") or "").lower()
        if "alternate" in rels and ("rss" in ltype or "atom" in ltype):
            href = link.get("href")
            if href:
                found.append(urljoin(base_url, href))
    return found


def _candidate_bases(url: str, website: str) -> list[str]:
    bases = set()
    parts = urlsplit(url)
    bases.add(f"{parts.scheme}://{parts.netloc}/")
    if website:
        bases.add(f"https://{website.rstrip('/')}/")
        bases.add(f"https://www.{website.rstrip('/')}/")
    return sorted(bases)


def _try_feed(url: str) -> tuple[bool, str]:
    resp = _get(url)
    if resp is None:
        return False, ""
    feed = feedparser.parse(resp.content)
    if feed.bozo and not feed.entries:
        return False, ""
    if not feed.entries:
        return False, ""
    top = feed.entries[0]
    title = (top.get("title") or "")[:80]
    date = top.get("published") or top.get("updated") or ""
    return True, f"{len(feed.entries)} entries, latest: '{title}' ({date})"


def rescue_one(op: Operator, source: Source) -> list[str]:
    lines = [f"\n=== {op.name} — {source.url} ==="]
    candidates: list[str] = []

    page = _get(source.url)
    if page is not None:
        candidates.extend(_autodiscover(page.text, source.url))
    for base in _candidate_bases(source.url, op.website):
        home = _get(base)
        if home is not None:
            candidates.extend(_autodiscover(home.text, base))
        for path in COMMON_FEED_PATHS:
            candidates.append(urljoin(base, path))

    seen = set()
    hits = []
    for cand in candidates:
        if cand in seen:
            continue
        seen.add(cand)
        ok, detail = _try_feed(cand)
        if ok:
            hits.append((cand, detail))

    if page is None:
        lines.append("  base fetch: FAILED (likely bot-blocked, see validate_sources)")
    if hits:
        for cand, detail in hits:
            lines.append(f"  FEED CANDIDATE: {cand}\n    -> {detail}")
    else:
        lines.append(f"  no working feed found among {len(seen)} candidates tried")
    return lines


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--names", default="",
                       help="Comma-separated operator names to check "
                            "(default: every kind=official source)")
    args = parser.parse_args()

    cfg: Config = load_config(args.root.resolve())
    wanted = {n.strip() for n in args.names.split(",") if n.strip()}

    jobs: list[tuple[Operator, Source]] = []
    for op in cfg.operators:
        for src in op.sources:
            if wanted:
                if op.name in wanted:
                    jobs.append((op, src))
            elif src.kind == "official":
                jobs.append((op, src))

    print(f"Rescuing {len(jobs)} source(s)...")
    with ThreadPoolExecutor(max_workers=6) as pool:
        futures = {pool.submit(rescue_one, op, src): op.name for op, src in jobs}
        results = {}
        for fut in as_completed(futures):
            results[futures[fut]] = fut.result()
    # print in the original job order for stable diffs
    for op, _src in jobs:
        for line in results.get(op.name, []):
            print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
