"""RSS/Atom collector - preferred source type (entries carry publish dates).

Feeds are the operator's OWN feed (or a trade-press feed). There is deliberately
no keyword news-search here: that pulled in off-topic noise with the wrong
provenance and has been removed.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

import feedparser
from bs4 import BeautifulSoup

from ..config import Source
from ..models import Item

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
    return None


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
            )
        )
    return items


def collect_rss(source: Source, region: str, operator: str | None,
                origin: str, http_cfg: dict) -> list[Item]:
    from .http import fetch
    resp = fetch(source.url, http_cfg)
    return parse_feed_bytes(resp.content, source, region, operator, origin)
