"""RSS/Atom collector - preferred source type (entries carry publish dates).

Handles two shapes:
  * normal operator / trade-press feeds
  * Google News search feeds (kind "news_search"): the entry <source> element
    carries the real publisher, which we surface as the item's source name so
    the report shows "Reuters" / "Light Reading" instead of "news.google.com".
"""
from __future__ import annotations

import logging
import random
import time
from datetime import datetime, timezone

import feedparser
from bs4 import BeautifulSoup

from ..config import Source
from ..models import Item

log = logging.getLogger(__name__)

MAX_ENTRIES_PER_FEED = 40


def _strip_html(text: str) -> str:
    """Some feeds embed HTML inside titles/summaries - flatten to plain text."""
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


def _publisher(entry, fallback: str) -> str:
    """For Google-News-style feeds, entry.source.title is the real outlet."""
    src = entry.get("source")
    if src is not None:
        title = getattr(src, "title", None)
        if not title and isinstance(src, dict):
            title = src.get("title")
        if title:
            return str(title).strip()
    return fallback


def parse_feed_bytes(raw: bytes, source: Source, region: str,
                     operator: str | None, origin: str) -> list[Item]:
    """Parse feed content into Items (separated from fetching for testability)."""
    feed = feedparser.parse(raw)
    if feed.bozo and not feed.entries:
        raise ValueError(f"unparseable feed: {feed.bozo_exception}")

    is_news_search = source.kind == "news_search"
    default_name = source.name or source.url
    items: list[Item] = []
    for entry in feed.entries[:MAX_ENTRIES_PER_FEED]:
        title = _strip_html(entry.get("title") or "")
        link = (entry.get("link") or "").strip()
        if not title or not link:
            continue
        # Google News appends " - Publisher" to the title; keep it clean.
        source_name = default_name
        if is_news_search:
            source_name = _publisher(entry, default_name)
            if title.endswith(f" - {source_name}"):
                title = title[: -(len(source_name) + 3)].strip()
        summary = _strip_html(entry.get("summary") or entry.get("description") or "")
        items.append(
            Item(
                title=title,
                url=link,
                source_name=source_name,
                region=region,
                operator=operator,
                published=_entry_date(entry),
                summary=summary[:600],
                origin="news_search" if is_news_search else origin,
            )
        )
    return items


def collect_rss(source: Source, region: str, operator: str | None,
                origin: str, http_cfg: dict) -> list[Item]:
    from .http import fetch
    # Spread out the many per-operator news-search feeds so they don't hit
    # the aggregator as one synchronized burst (which triggers 429/503).
    if source.kind == "news_search":
        time.sleep(random.uniform(0, 3.0))
    resp = fetch(source.url, http_cfg)
    return parse_feed_bytes(resp.content, source, region, operator, origin)
