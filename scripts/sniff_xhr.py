#!/usr/bin/env python3
"""Sniff XHR/fetch network responses while rendering a source in Chromium.

Many newsroom pages are React/Vue SPAs whose article list is not in the
static DOM at all - it arrives via a background XHR/fetch call to a JSON
API a few hundred ms after the shell loads. scripts/inspect_dom.py only
dumps the DOM after a short settle, so it never sees that data. This script
instead listens on the page's `response` event for the whole render window
and prints every same-site (or clearly news-shaped) JSON/XHR response it
saw, with a short body preview - so a human/agent can identify the real
press-release endpoint and turn it into a `json_api` source.

Usage:
    PLAYWRIGHT_PROXY_SERVER=... python scripts/sniff_xhr.py --names "Jio,TIM" [--timeout 25]
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from telco_radar.collect.http import BROWSER_UA  # noqa: E402
from telco_radar.config import load_config  # noqa: E402

_BLOCK_TYPES = {"image", "media", "font"}
_JSON_HINTS = ("json", "javascript")
_NEWS_HINTS = ("press", "news", "media", "article", "release", "story",
              "newsroom", "content", "search", "listing")


def sniff(url: str, timeout_s: float, ua: str) -> None:
    from playwright.sync_api import sync_playwright

    responses: list[dict] = []

    launch_args = ["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu",
                  "--disable-blink-features=AutomationControlled", "--disable-http2"]
    launch_kwargs: dict = {"headless": True, "args": launch_args}
    proxy_server = os.environ.get("PLAYWRIGHT_PROXY_SERVER")
    if proxy_server:
        launch_kwargs["proxy"] = {"server": proxy_server}
        launch_args.append("--ignore-certificate-errors")

    with sync_playwright() as p:
        browser = p.chromium.launch(**launch_kwargs)
        try:
            page = browser.new_page(user_agent=ua, viewport={"width": 1366, "height": 900},
                                    locale="en-US")
            page.route("**/*", lambda route: route.abort()
                      if route.request.resource_type in _BLOCK_TYPES else route.continue_())

            def on_response(resp):
                try:
                    ctype = resp.headers.get("content-type", "")
                except Exception:
                    ctype = ""
                rtype = resp.request.resource_type
                if rtype not in ("xhr", "fetch") and "json" not in ctype:
                    return
                responses.append({"url": resp.url, "status": resp.status,
                                  "ctype": ctype, "resp": resp})

            page.on("response", on_response)
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=int(timeout_s * 1000))
            except Exception as exc:  # noqa: BLE001
                print(f"  goto FAILED: {type(exc).__name__}: {exc}")
            # Click common cookie-consent buttons in case they block XHRs.
            for sel in ("#onetrust-accept-btn-handler", "button:has-text(\"Accept\")",
                       "button:has-text(\"Accept All\")", "button:has-text(\"I Agree\")",
                       "button:has-text(\"Alle akzeptieren\")"):
                try:
                    page.click(sel, timeout=1500)
                    break
                except Exception:
                    continue
            page.wait_for_timeout(int(max(timeout_s * 1000 - 5000, 4000)))

            print(f"  captured {len(responses)} xhr/fetch/json response(s)")
            base_host = urlsplit(url).netloc.removeprefix("www.")
            for rec in responses:
                u = rec["url"]
                host = urlsplit(u).netloc.removeprefix("www.")
                same_ish = base_host in host or host in base_host
                hint = any(h in u.lower() for h in _NEWS_HINTS)
                marker = "***" if (same_ish and hint) else ("*  " if hint else "   ")
                print(f"  {marker}[{rec['status']}] {rec['ctype'][:30]:30} {u[:140]}")
                if marker.strip() and rec["status"] == 200:
                    try:
                        body = rec["resp"].text()[:300]
                        print(f"        preview: {body!r}")
                    except Exception as exc:  # noqa: BLE001
                        print(f"        (body read failed: {exc})")
        finally:
            browser.close()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--names", required=True, help="Comma-separated operator names")
    parser.add_argument("--timeout", type=float, default=25.0)
    args = parser.parse_args()

    cfg = load_config(args.root.resolve())
    wanted = {n.strip() for n in args.names.split(",") if n.strip()}
    missing = set(wanted)

    for op in cfg.operators:
        if op.name not in wanted:
            continue
        missing.discard(op.name)
        for source in op.sources:
            print(f"\n{'=' * 90}\n{op.name} [{source.kind}] — {source.url}\n{'=' * 90}")
            sniff(source.url, args.timeout, BROWSER_UA)

    if missing:
        print(f"\nWARNING: no operator matched: {', '.join(sorted(missing))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
