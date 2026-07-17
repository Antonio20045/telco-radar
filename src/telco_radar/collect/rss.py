"""RSS/Atom collector - preferred source type (entries carry publish dates).

Handles two shapes:
  * normal operator / trade-press feeds
  * per-operator web-news search feeds (kind "news_search"). We use Bing News
    RSS: its item links are redirects of the form
    bing.com/news/apiclick.aspx?...&url=<REAL_URL>. We pull out the `url=`
    param so the stored link is the DIRECT publisher article - not an
    aggregator/consent page.
"""
from __future__ import annotations

import logging
import random
import time
import urllib.parse
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


def _direct_url(link: str) -> str | None:
    """Extract the real publisher URL from a Bing news redirect link.

    Returns None if the link is a bare aggregator link with no target, so the
    caller can drop it rather than store a non-article URL.
    """
    parts = urllib.parse.urlsplit(link)
    host = parts.netloc.lower()
    if "bing.com" in host and "apiclick" in parts.path:
        qs = urllib.parse.parse_qs(parts.query)
        target = qs.get("url", [None])[0]
        if target and target.startswith(("http://", "https://")):
            return target
        return None
    # already a direct link (some Bing items are direct)
    if "bing.com" in host or "news.google.com" in host:
        return None
    return link


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

        source_name = default_name
        if is_news_search:
            direct = _direct_url(link)
            if not direct:
                continue  # no real article behind it -> skip, never store a redirect
            link = direct
            # publisher = the article's own domain (honest + human readable)
            source_name = urllib.parse.urlsplit(link).netloc.removeprefix("www.")

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
    # Spread out the many per-operator news-search feeds so they don't hit the
    # search engine as one synchronized burst (which triggers 429/503).
    if source.kind == "news_search":
        time.sleep(random.uniform(0, 3.0))
    resp = fetch(source.url, http_cfg)
    return parse_feed_bytes(resp.content, source, region, operator, origin)
