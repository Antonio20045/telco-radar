"""Headless-browser newsroom collector (Playwright / Chromium).

For operator press pages that are JavaScript-rendered (the article list is not
in the static HTML). We render the operator's OWN page in headless Chromium,
then reuse the exact same article-extraction heuristics as the static newsroom
collector. Heavy resources (images/media/fonts) are blocked for speed.

The run environment installs Chromium (see .github/workflows/radar.yml). If
Playwright/Chromium is unavailable the source raises and is logged as a normal
source failure - it never aborts the run.
"""
from __future__ import annotations

import logging
import os

from ..config import Source
from ..models import Item
from .newsroom import parse_newsroom_html
from .http import BROWSER_UA

log = logging.getLogger(__name__)

_BLOCK_TYPES = {"image", "media", "font"}
# Stylesheets are deliberately NOT blocked: several operator sites (e.g.
# Zain) gate their article list's data-fill on CSS-driven visibility
# (an IntersectionObserver-style lazy load that never fires for elements
# the browser considers invisible without layout/CSS), so blocking CSS for
# speed silently broke content that otherwise renders fine.

# Common cookie-consent banner buttons across the CMP vendors telco sites
# use (OneTrust, Cookiebot, generic). A banner can sit on top of the article
# list and block lazy-loaded content from ever firing its fetch (some sites
# gate the fetch behind an intersection observer the banner obscures), so
# clicking one through - if present - happens before the content settle
# wait below. Best-effort: every selector is tried with a short timeout and
# failures are silently ignored, since most pages have no banner at all.
_CONSENT_SELECTORS = (
    "#onetrust-accept-btn-handler",
    "button:has-text(\"Accept All\")",
    "button:has-text(\"Accept all\")",
    "button:has-text(\"Accept\")",
    "button:has-text(\"I Agree\")",
    "button:has-text(\"Alle akzeptieren\")",
    "#CybotCookiebotDialogBodyLevelButtonLevelOptinAllowAll",
)


def render_html(url: str, timeout_s: float, ua: str) -> str:
    """Render *url* in headless Chromium and return the final DOM HTML."""
    from playwright.sync_api import sync_playwright

    launch_args = ["--no-sandbox", "--disable-dev-shm-usage",
                   "--disable-gpu", "--disable-blink-features=AutomationControlled",
                   # Some sites (e.g. Optus) fail HTTP/2 negotiation from
                   # datacenter IPs with ERR_HTTP2_PROTOCOL_ERROR; forcing
                   # HTTP/1.1 for the whole browser session is a safe,
                   # widely-used workaround since virtually every server also
                   # speaks HTTP/1.1.
                   "--disable-http2"]
    launch_kwargs: dict = {"headless": True, "args": launch_args}
    # Dev-sandbox escape hatch only: some local dev environments front all
    # outbound traffic with a TLS-terminating proxy whose ClientHello parser
    # chokes on Chromium's own handshake (GREASE/post-quantum extensions),
    # resetting every connection. Unset in CI/production, so this is a no-op
    # there. When set, point it at a local proxy that itself uses a normal
    # TLS stack for the outbound leg (see scripts/inspect_dom.py docs).
    proxy_server = os.environ.get("PLAYWRIGHT_PROXY_SERVER")
    if proxy_server:
        launch_kwargs["proxy"] = {"server": proxy_server}
        launch_args.append("--ignore-certificate-errors")

    with sync_playwright() as p:
        browser = p.chromium.launch(**launch_kwargs)
        try:
            page = browser.new_page(
                user_agent=ua,
                viewport={"width": 1366, "height": 900},
                locale="en-US",
            )
            page.route(
                "**/*",
                lambda route: route.abort()
                if route.request.resource_type in _BLOCK_TYPES else route.continue_(),
            )
            page.goto(url, wait_until="domcontentloaded",
                      timeout=int(timeout_s * 1000))
            for selector in _CONSENT_SELECTORS:
                try:
                    page.click(selector, timeout=1200)
                    break
                except Exception:  # noqa: BLE001 - no banner, or a different one
                    continue
            # A settle for client-side rendering: several operator sites lazy-
            # load the article list itself (not just images) behind an
            # intersection observer or a delayed XHR, so 1.8s was too short
            # and returned near-empty cards. We deliberately do NOT wait for
            # networkidle - many telco pages keep long-poll/analytics
            # connections open and would burn the whole timeout budget.
            page.wait_for_timeout(9000)
            return page.content()
        finally:
            browser.close()


def collect_newsroom_js(source: Source, region: str, operator: str | None,
                        origin: str, http_cfg: dict) -> list[Item]:
    timeout_s = float(http_cfg.get("render_timeout_seconds",
                                   http_cfg.get("timeout_seconds", 25)))
    ua = http_cfg.get("user_agent", BROWSER_UA)
    max_links = int(http_cfg.get("max_links_per_newsroom", 30))
    html = render_html(source.url, timeout_s, ua)
    return parse_newsroom_html(html, source, region, operator, origin, max_links)
