"""Shared HTTP fetch with user-agent fallback.

Some newsrooms block browser UAs coming from datacenter IPs, others block
anything that does not look like a browser. We try the configured UA first
and retry once with the alternate style on 403/406.
"""
from __future__ import annotations

import logging

import httpx

log = logging.getLogger(__name__)

BROWSER_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
              "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36")
BOT_UA = "TelcoRadar/1.0 (+https://github.com/Antonio20045/telco-radar)"

_RETRY_STATUSES = {403, 406}


def fetch(url: str, http_cfg: dict) -> httpx.Response:
    """GET with UA fallback. Raises on final failure."""
    timeout = float(http_cfg.get("timeout_seconds", 20))
    primary = http_cfg.get("user_agent", BROWSER_UA)
    fallback = BOT_UA if primary != BOT_UA else BROWSER_UA

    last_exc: Exception | None = None
    for ua in (primary, fallback):
        headers = {
            "User-Agent": ua,
            "Accept": "text/html,application/xhtml+xml,application/xml,*/*",
            "Accept-Language": "en;q=0.9,de;q=0.8",
        }
        try:
            resp = httpx.get(url, timeout=timeout, headers=headers,
                             follow_redirects=True)
            if resp.status_code in _RETRY_STATUSES:
                last_exc = httpx.HTTPStatusError(
                    f"{resp.status_code} with UA '{ua[:24]}...'",
                    request=resp.request, response=resp)
                continue
            resp.raise_for_status()
            return resp
        except httpx.HTTPError as exc:
            last_exc = exc
            continue
    raise last_exc if last_exc else RuntimeError(f"fetch failed: {url}")
