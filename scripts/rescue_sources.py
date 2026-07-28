#!/usr/bin/env python3
"""Diagnose + attempt to rescue every currently-dead source (EMPTY/FAIL).

For each dead source this tries, in order, until one works:
  1. RSS/Atom autodiscovery on the ORIGINAL page (<link rel="alternate">
     tags + anchors whose href looks like a feed) - the most common reason
     a "newsroom_js" entry is dead is that the operator has a plain RSS feed
     nobody wired up.
  2. A fixed list of common feed paths on the same origin.
  3. For newsroom_js sources only: a longer render budget (35s render +
     networkidle fallback + 4s settle) in case the current 16s/1.8s budget
     is just too tight for a slow SPA.
  4. Otherwise: classify from the raw HTTP status (403/406/999/etc -> hard
     bot-block; timeout -> needs more time; 200 with no candidate -> the
     article list needs a real item_selector, not just more time).

Prints ONE machine-parseable line per dead source, prefixed RESCUE:, plus a
human summary. Needs real network + (for step 3) Playwright/Chromium - run
this in CI (radar.yml, sources_only input), not in a sandboxed session.

Usage: python scripts/rescue_sources.py [--root .]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.parse import urljoin, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import httpx
from bs4 import BeautifulSoup

from telco_radar.collect.newsroom import collect_newsroom, parse_newsroom_html  # noqa: E402
from telco_radar.collect.newsroom_js import collect_newsroom_js  # noqa: E402
from telco_radar.collect.json_api import collect_json  # noqa: E402
from telco_radar.collect.rss import collect_rss, parse_feed_bytes  # noqa: E402
from telco_radar.collect.http import BROWSER_UA, BOT_UA  # noqa: E402
from telco_radar.config import load_config  # noqa: E402

_COLLECTORS = {
    "rss": collect_rss, "trade_press": collect_rss,
    "json_api": collect_json, "newsroom": collect_newsroom,
    "newsroom_js": collect_newsroom_js,
}

_COMMON_FEED_PATHS = [
    "/feed", "/feed/", "/rss", "/rss/", "/rss.xml", "/feed.xml", "/atom.xml",
    "/en/rss", "/en/feed", "/media/rss", "/press/feed", "/press/rss",
    "/news/rss", "/news/feed", "/newsroom/rss", "/index.rss",
    "/feeds/posts/default",
]


def check_current(source, region, operator, origin, http_cfg):
    if source.kind == "official":
        return ("SKIP", 0, "reference-only (not crawled)")
    fn = _COLLECTORS.get(source.kind, collect_newsroom)
    try:
        items = fn(source, region, operator, origin, http_cfg)
        return ("OK" if items else "EMPTY", len(items), "")
    except Exception as exc:  # noqa: BLE001
        return ("FAIL", 0, f"{type(exc).__name__}: {str(exc)[:100]}")


def _raw_get(url: str, ua: str, timeout: float):
    headers = {"User-Agent": ua, "Accept": "text/html,application/xhtml+xml,*/*"}
    return httpx.get(url, timeout=timeout, headers=headers, follow_redirects=True)


def _try_feed_url(url: str, source, region, operator, origin, http_cfg):
    """Return (n_items, sample_titles) if *url* parses as a usable feed."""
    try:
        resp = httpx.get(url, timeout=15, follow_redirects=True,
                         headers={"User-Agent": http_cfg.get("user_agent", BROWSER_UA)})
        resp.raise_for_status()
        items = parse_feed_bytes(resp.content, source, region, operator, origin)
        if items:
            return len(items), [i.title[:60] for i in items[:2]]
    except Exception:  # noqa: BLE001
        pass
    return 0, []


def discover(source, region, operator, origin, http_cfg, current_error: str):
    """Best-effort rescue attempt. Returns a dict describing what was found."""
    url = source.url
    parsed = urlparse(url)
    origin_url = f"{parsed.scheme}://{parsed.netloc}"
    ua = http_cfg.get("user_agent", BROWSER_UA)
    timeout = float(http_cfg.get("timeout_seconds", 20))

    raw_status = None
    raw_error = ""
    candidates: list[str] = []
    try:
        resp = _raw_get(url, ua, timeout)
        raw_status = resp.status_code
        if resp.status_code < 400:
            soup = BeautifulSoup(resp.text, "html.parser")
            for link in soup.find_all("link", attrs={"type": re.compile("rss|atom")}):
                href = link.get("href")
                if href:
                    candidates.append(urljoin(url, href))
            for a in soup.find_all("a", href=True):
                href = a["href"].lower()
                if any(k in href for k in ("rss", "feed", "atom")) and \
                        not href.startswith(("mailto:", "tel:", "javascript:")):
                    candidates.append(urljoin(url, a["href"]))
    except Exception as exc:  # noqa: BLE001
        raw_error = f"{type(exc).__name__}: {str(exc)[:100]}"

    for path in _COMMON_FEED_PATHS:
        candidates.append(origin_url + path)

    seen = set()
    ordered = [c for c in candidates if not (c in seen or seen.add(c))]

    for cand in ordered[:20]:
        n, sample = _try_feed_url(cand, source, region, operator, origin, http_cfg)
        if n:
            return {"fix": "rss", "url": cand, "items": n, "sample": sample}

    if source.kind == "newsroom_js":
        try:
            from telco_radar.collect.newsroom_js import render_html
            html = render_html(url, timeout_s=35.0, ua=ua)
            items = parse_newsroom_html(
                html, source, region, operator, origin,
                int(http_cfg.get("max_links_per_newsroom", 30)))
            if items:
                return {"fix": "longer_render", "url": url, "items": len(items),
                        "sample": [i.title[:60] for i in items[:2]]}
        except Exception as exc:  # noqa: BLE001
            raw_error = raw_error or f"{type(exc).__name__}: {str(exc)[:100]}"

    if raw_status is not None and raw_status >= 400:
        return {"fix": "blocked", "status": raw_status}
    if raw_status is not None:
        return {"fix": "needs_selector", "status": raw_status}
    return {"fix": "unreachable", "error": raw_error or current_error}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--only", nargs="*", default=None,
                        help="Restrict to these operator/source names (substring match)")
    args = parser.parse_args()

    cfg = load_config(args.root.resolve())
    http_cfg = cfg.settings.get("http", {})

    jobs = []
    for op in cfg.operators:
        for src in op.sources:
            jobs.append((src, op.region_key, op.name, "operator"))
    for src in cfg.news_sources:
        jobs.append((src, "global", None, "industry_news"))

    if args.only:
        needles = [n.lower() for n in args.only]
        jobs = [j for j in jobs if any(n in (j[2] or j[0].name or "").lower() for n in needles)]

    print(f"Checking {len(jobs)} sources for dead ones to rescue...\n")
    dead = []
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = {pool.submit(check_current, s, r, o, g, http_cfg): (s, r, o, g)
                  for s, r, o, g in jobs}
        for fut in as_completed(futures):
            s, r, o, g = futures[fut]
            status, n, err = fut.result()
            if status in ("EMPTY", "FAIL"):
                dead.append((s, r, o, g, status, err))

    print(f"{len(dead)} dead sources out of {len(jobs)}.\n")
    print(f"{'NAME':24} {'STATUS':6} {'FIX':16} DETAIL")
    print("-" * 110)

    results = []
    with ThreadPoolExecutor(max_workers=6) as pool:
        futures = {
            pool.submit(discover, s, r, o, g, http_cfg, err): (s, o, status)
            for s, r, o, g, status, err in dead
        }
        for fut in as_completed(futures):
            s, o, status = futures[fut]
            res = fut.result()
            name = (o or s.name or "")[:24]
            fix = res.get("fix", "?")
            if fix in ("rss", "longer_render"):
                detail = f"{res['url']}  ({res['items']} items, e.g. {res.get('sample')})"
            elif fix == "blocked":
                detail = f"HTTP {res.get('status')} - likely bot-wall, needs proxy"
            elif fix == "needs_selector":
                detail = f"HTTP {res.get('status')} but no feed/links found - needs item_selector or is truly empty"
            else:
                detail = res.get("error", "")
            print(f"{name:24} {status:6} {fix:16} {detail}")
            results.append({"name": name, "kind": s.kind, "url": s.url,
                            "status": status, **res})

    print("\n--- JSON (for machine parsing) ---")
    print(json.dumps(results, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
