"""Shared HTTP fetch with user-agent fallback and rate-limit backoff.

Some newsrooms block browser UAs from datacenter IPs, others block anything
that does not look like a browser -> we try the configured UA first and retry
once with the alternate style on 403/406.

News aggregators (notably Google News RSS) throttle bursts of requests from
shared cloud IPs with 429/503. We retry those a couple of times with a short
backoff, which clears the transient throttling that happens when many feeds
fire at once. A UA swap cannot fix a 5xx, so we do not waste a second UA on it.
"""
from __future__ import annotations

import logging
import random
import time
from urllib.parse import urlsplit

import httpx

log = logging.getLogger(__name__)

BROWSER_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
              "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36")
BOT_UA = "TelcoRadar/1.0 (+https://github.com/Antonio20045/telco-radar)"

_UA_SWAP_STATUSES = {403, 406}            # try the other UA
_BACKOFF_STATUSES = {429, 500, 502, 503}  # transient -> retry same UA, then give up
_BACKOFF_WAITS = (4.0, 9.0)               # waits used *between* retries


def fetch(url: str, http_cfg: dict,
          timeout_override: float | None = None,
          extra_headers: dict | None = None) -> httpx.Response:
    """GET with UA fallback + short backoff on rate limits.

    Gesamtbudget je Quelle
    ----------------------
    Zwei User-Agents mal drei Versuche mal Timeout plus 13 s Backoff - im
    schlimmsten Fall wartet ein einziger Abruf minutenlang. Solange die
    Sammelphase an der Zahl der Quellen hing, fiel das nicht auf. Seit sie
    host-gedrosselt parallel laeuft, haengt sie an der LANGSAMSTEN EINZELNEN
    Quelle: in Lauf #68 lag der Median bei 3,2 s, aber KT brauchte 299,8 s
    und bestimmte damit die 303-Sekunden-Phase im Alleingang.

    `source_budget_seconds` deckelt das. Ueberschritten wird es nur von
    Quellen, die ohnehin gerade nicht antworten - der letzte Fehler wird
    unveraendert geworfen, die Quelle steht also weiter als "fail" im
    Protokoll und nicht als leise uebersprungen.
    """
    timeout = float(timeout_override or http_cfg.get("timeout_seconds", 20))
    budget = float(http_cfg.get("source_budget_seconds", 0) or 0)
    frist = (time.monotonic() + budget) if budget else None
    primary = http_cfg.get("user_agent", BROWSER_UA)
    fallback = BOT_UA if primary != BOT_UA else BROWSER_UA

    # A same-origin Referer mimics a normal in-site navigation. Most sources
    # do not care, but some AEM/CMS "public" backend servlets (e.g. stc's
    # bin/public/assets) reject requests with no Referer at all as a light
    # CSRF/hotlink guard - sending one costs nothing and fixes those.
    site_root = f"{urlsplit(url).scheme}://{urlsplit(url).netloc}/"

    last_exc: Exception | None = None
    for ua in (primary, fallback):
        headers = {
            "User-Agent": ua,
            "Accept": "text/html,application/xhtml+xml,application/xml,*/*",
            "Accept-Language": "en;q=0.9,de;q=0.8",
            "Referer": site_root,
        }
        if extra_headers:
            headers.update(extra_headers)
        # attempt 0 immediate, then one retry per backoff wait
        for wait in (0.0, *_BACKOFF_WAITS):
            if frist is not None and time.monotonic() >= frist:
                log.info("Budget von %.0fs fuer %s erschoepft - Abbruch",
                         budget, url[:60])
                break
            if wait:
                time.sleep(wait + random.uniform(0, 1.0))
            try:
                resp = httpx.get(url, timeout=timeout, headers=headers,
                                 follow_redirects=True)
                if resp.status_code in _UA_SWAP_STATUSES:
                    last_exc = httpx.HTTPStatusError(
                        f"{resp.status_code} with UA '{ua[:24]}...'",
                        request=resp.request, response=resp)
                    break  # try the other UA (no backoff)
                if resp.status_code in _BACKOFF_STATUSES:
                    last_exc = httpx.HTTPStatusError(
                        f"status {resp.status_code}",
                        request=resp.request, response=resp)
                    continue  # transient -> back off and retry same UA
                resp.raise_for_status()
                return resp
            except httpx.HTTPError as exc:
                last_exc = exc
                continue
        # if the last failure was a transient 5xx/429, a UA swap won't help
        if isinstance(last_exc, httpx.HTTPStatusError) and \
                last_exc.response is not None and \
                last_exc.response.status_code in _BACKOFF_STATUSES:
            break
        if frist is not None and time.monotonic() >= frist:
            break
    raise last_exc if last_exc else RuntimeError(f"fetch failed: {url}")
