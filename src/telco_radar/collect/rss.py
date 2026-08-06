"""RSS/Atom collector - preferred source type (entries carry publish dates).

Feeds are the operator's OWN feed (or a trade-press feed). There is deliberately
no keyword news-search here: that pulled in off-topic noise with the wrong
provenance and has been removed.
"""
from __future__ import annotations

import logging
import re
import time
from datetime import datetime, timezone

import feedparser
from bs4 import BeautifulSoup

from ..config import Source
from ..models import Item
from .newsroom import _date_from_text

log = logging.getLogger(__name__)

MAX_ENTRIES_PER_FEED = 40


def _strip_html(text: str) -> str:
    if "<" not in text:
        return text.strip()
    return BeautifulSoup(text, "html.parser").get_text(" ", strip=True)


def _entry_date(entry) -> datetime | None:
    for key in ("published_parsed", "updated_parsed"):
        parsed = entry.get(key)
        if parsed:
            try:
                return datetime(*parsed[:6], tzinfo=timezone.utc)
            except (TypeError, ValueError):
                continue
    # feedparser only pre-parses RFC822/ISO stamps. Feeds that print a human
    # date instead (Fierce Network: "Jul 31, 2026 12:57pm") leave *_parsed
    # empty, and an undated item sinks below the analyst's per-region cap -
    # so the busiest trade-press feed would never be read. Fall back to the
    # same text parser the newsroom scraper uses.
    for key in ("published", "updated", "date", "dc_date", "pubDate"):
        raw = entry.get(key)
        if isinstance(raw, str) and raw.strip():
            parsed_text = _date_from_text(raw[:60])
            if parsed_text:
                return parsed_text
    return None


_IMG_IM_TEXT = re.compile(r'<img[^>]+src=["\']([^"\']+)', re.I)


def _entry_image(entry) -> str:
    """Bild-URL eines Feed-Eintrags, falls der Feed eine mitliefert.

    Feeds transportieren Bilder auf vier verschiedene Arten, je nach
    Redaktionssystem. Keine davon ist verlaesslich vorhanden - Mobile World
    Live liefert gar keine, Light Reading ein media:content. Deshalb alle
    vier probieren und leer zurueckgeben, wenn keine greift.
    """
    for feld in ("media_content", "media_thumbnail"):
        for m in (entry.get(feld) or []):
            url = (m.get("url") or "").strip()
            if url:
                return url
    for link in (entry.get("links") or []):
        if (link.get("rel") == "enclosure"
                and str(link.get("type") or "").startswith("image")):
            url = (link.get("href") or "").strip()
            if url:
                return url
    blob = (entry.get("summary") or "") + "".join(
        c.get("value") or "" for c in (entry.get("content") or []))
    m = _IMG_IM_TEXT.search(blob)
    return m.group(1).strip() if m else ""


def parse_feed_bytes(raw: bytes, source: Source, region: str,
                     operator: str | None, origin: str) -> list[Item]:
    """Parse feed content into Items (separated from fetching for testability)."""
    feed = feedparser.parse(raw)
    if feed.bozo and not feed.entries:
        raise ValueError(f"unparseable feed: {feed.bozo_exception}")

    default_name = source.name or source.url
    items: list[Item] = []
    for entry in feed.entries[:MAX_ENTRIES_PER_FEED]:
        title = _strip_html(entry.get("title") or "")
        link = (entry.get("link") or "").strip()
        if not title or not link:
            continue
        summary = _strip_html(entry.get("summary") or entry.get("description") or "")
        items.append(
            Item(
                title=title,
                url=link,
                source_name=default_name,
                region=region,
                operator=operator,
                published=_entry_date(entry),
                summary=summary[:600],
                origin=origin,
                image_url=_entry_image(entry),
            )
        )
    return items


_PARSE_RETRIES = 2
_PARSE_RETRY_WAIT = 1.5


def collect_rss(source: Source, region: str, operator: str | None,
                origin: str, http_cfg: dict) -> list[Item]:
    from .http import fetch

    # A feed can answer with HTTP 200 (or 202) and still not be a feed: Telecoms
    # Tech News serves a WAF captcha page instead of RSS in roughly 4 of 10
    # runs, and two Joomla feeds (The Fast Mode, Developing Telecoms) hand back
    # truncated XML now and then. The HTTP layer sees nothing wrong, so only a
    # re-fetch after the parse failure helps - and it does: the same feeds
    # answer correctly on the immediate next try.
    last_exc: ValueError | None = None
    for attempt in range(_PARSE_RETRIES + 1):
        resp = fetch(source.url, http_cfg, source.timeout_seconds, source.headers)
        try:
            return parse_feed_bytes(resp.content, source, region, operator, origin)
        except ValueError as exc:
            last_exc = exc
            if attempt < _PARSE_RETRIES:
                log.info("Feed %s did not parse (%s) - retrying", source.url, exc)
                time.sleep(_PARSE_RETRY_WAIT * (attempt + 1))
    raise last_exc
