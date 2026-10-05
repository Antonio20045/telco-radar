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
NACHLADEZEIT_MS = 9000

_CONSENT_SELECTORS = (
    "#onetrust-accept-btn-handler",
    'button:has-text("Accept All")',
    'button:has-text("Accept all")',
    'button:has-text("Accept")',
    'button:has-text("I Agree")',
    'button:has-text("Alle akzeptieren")',
    "#CybotCookiebotDialogBodyLevelButtonLevelOptinAllowAll",
)


def render_html(url: str, timeout_s: float, ua: str) -> str:
    """Render *url* in headless Chromium and return the final DOM HTML."""
    from playwright.sync_api import sync_playwright

    launch_args = [
        "--no-sandbox",
        "--disable-dev-shm-usage",
        "--disable-gpu",
        "--disable-blink-features=AutomationControlled",
        "--disable-http2",
    ]
    launch_kwargs: dict = {"headless": True, "args": launch_args}
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
                lambda route: (
                    route.abort()
                    if route.request.resource_type in _BLOCK_TYPES
                    else route.continue_()
                ),
            )
            page.goto(url, wait_until="domcontentloaded", timeout=int(timeout_s * 1000))
            for selector in _CONSENT_SELECTORS:
                try:
                    page.click(selector, timeout=1200)
                    break
                except Exception:  # noqa: BLE001
                    continue
            page.wait_for_timeout(NACHLADEZEIT_MS)
            return page.content()
        finally:
            browser.close()


def collect_newsroom_js(
    source: Source, region: str, operator: str | None, origin: str, http_cfg: dict
) -> list[Item]:
    timeout_s = float(
        http_cfg.get("render_timeout_seconds", http_cfg.get("timeout_seconds", 25))
    )
    ua = http_cfg.get("user_agent", BROWSER_UA)
    max_links = int(http_cfg.get("max_links_per_newsroom", 30))
    html = render_html(source.url, timeout_s, ua)
    return parse_newsroom_html(html, source, region, operator, origin, max_links)
