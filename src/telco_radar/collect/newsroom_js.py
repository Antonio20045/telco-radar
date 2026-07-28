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

from ..config import Source
from ..models import Item
from .newsroom import parse_newsroom_html
from .http import BROWSER_UA

log = logging.getLogger(__name__)

_BLOCK_TYPES = {"image", "media", "font", "stylesheet"}

# Consent-management platforms whose overlay can block the whole page (no
# scroll, sometimes no client-side data fetch either) until dismissed. Best
# effort: try each known "accept all" button, short timeout, ignore misses.
# Order matters only for speed (most common CMPs first).
_CONSENT_SELECTORS = [
    "#onetrust-accept-btn-handler",                      # OneTrust
    "#CybotCookiebotDialogBodyLevelButtonLevelOptinAllowAll",  # Cookiebot
    "#CybotCookiebotDialogBodyButtonAccept",
    "button#didomi-notice-agree-button",                 # Didomi
    ".didomi-continue-without-agreeing",
    "button[data-testid='uc-accept-all-button']",        # Usercentrics
    "#usercentrics-root >>> button[data-testid='uc-accept-all-button']",
    "button:has-text('Accept All')",
    "button:has-text('Accept all')",
    "button:has-text('I Accept')",
    "button:has-text('Alle akzeptieren')",
    "button:has-text('Aceptar todo')",
    "button:has-text('Tümünü Kabul Et')",
]


def _dismiss_consent_banner(page) -> None:
    for selector in _CONSENT_SELECTORS:
        try:
            page.click(selector, timeout=800)
            page.wait_for_timeout(300)
            return
        except Exception:  # noqa: BLE001 - best effort, most selectors won't match
            continue


def render_html(url: str, timeout_s: float, ua: str, settle_ms: int = 1800) -> str:
    """Render *url* in headless Chromium and return the final DOM HTML."""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage",
                  "--disable-gpu", "--disable-blink-features=AutomationControlled",
                  # Some sites (seen on Optus) reset the connection with
                  # ERR_HTTP2_PROTOCOL_ERROR against this exact client/CI
                  # fingerprint; HTTP/1.1 has been reliable where h2 wasn't.
                  "--disable-http2"],
        )
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
            # A cookie-consent overlay can block client-side rendering
            # entirely on some sites (real content never fetches/mounts
            # until dismissed) - try the common "accept all" buttons before
            # the settle wait, not after.
            _dismiss_consent_banner(page)
            # A short settle for client-side rendering. We deliberately do NOT
            # wait for networkidle - many telco pages keep long-poll/analytics
            # connections open and would burn the whole timeout budget.
            page.wait_for_timeout(settle_ms)
            return page.content()
        finally:
            browser.close()


def collect_newsroom_js(source: Source, region: str, operator: str | None,
                        origin: str, http_cfg: dict) -> list[Item]:
    timeout_s = float(http_cfg.get("render_timeout_seconds",
                                   http_cfg.get("timeout_seconds", 25)))
    settle_ms = int(http_cfg.get("render_settle_ms", 1800))
    ua = http_cfg.get("user_agent", BROWSER_UA)
    max_links = int(http_cfg.get("max_links_per_newsroom", 30))
    html = render_html(source.url, timeout_s, ua, settle_ms)
    return parse_newsroom_html(html, source, region, operator, origin, max_links)
