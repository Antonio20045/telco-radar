"""Generic HTML newsroom collector.

Press/newsroom landing pages differ wildly between operators. This collector
uses conservative heuristics: it extracts links that look like individual
press releases / news articles, optionally narrowed by a per-source CSS
selector from the watchlist. Dates are parsed from the URL or nearby text
when possible; undated items rely on the seen-store for novelty.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from urllib.parse import urljoin, urlsplit

import httpx
from bs4 import BeautifulSoup

from ..config import Source
from ..models import Item

log = logging.getLogger(__name__)

# URL path fragments that indicate an article-like page
_ARTICLE_HINTS = re.compile(
    r"(news|press|media|release|announce|story|article|aktuell|presse)", re.I
)
# Path fragments that indicate navigation/utility pages -> skip
_SKIP_HINTS = re.compile(
    r"(login|signin|cookie|privacy|legal|terms|contact|careers|jobs|search|"
    r"subscribe|newsletter|archive\?|/tag/|/category/|/author/|#|mailto:|tel:|"
    r"\.(pdf|jpg|jpeg|png|gif|svg|mp4|zip)$)", re.I
)
# Date patterns inside URLs, e.g. /2026/07/ or /2026-07-14- or 20260714
_URL_DATE = re.compile(
    r"(?:/|[-_])(20\d{2})[/\-_]?(0[1-9]|1[0-2])(?:[/\-_]?(0[1-9]|[12]\d|3[01]))?"
)
_TEXT_DATE = re.compile(
    r"\b(0?[1-9]|[12]\d|3[01])[./\s]"
    r"(0?[1-9]|1[0-2]|Jan\w*|Feb\w*|Mar\w*|Apr\w*|May|Jun\w*|Jul\w*|Aug\w*|"
    r"Sep\w*|Oct\w*|Nov\w*|Dec\w*)[./\s,]+(20\d{2})\b", re.I
)
_MONTHS = {m: i + 1 for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun",
     "jul", "aug", "sep", "oct", "nov", "dec"])}


def _date_from_url(url: str) -> tuple[datetime | None, bool]:
    """Returns (date, has_day_precision)."""
    m = _URL_DATE.search(url)
    if not m:
        return None, False
    year, month = int(m.group(1)), int(m.group(2))
    has_day = m.group(3) is not None
    day = int(m.group(3)) if has_day else 1
    try:
        return datetime(year, month, day, tzinfo=timezone.utc), has_day
    except ValueError:
        return None, False


def _date_from_text(text: str) -> datetime | None:
    m = _TEXT_DATE.search(text)
    if not m:
        return None
    day, mon_raw, year = m.group(1), m.group(2).lower(), int(m.group(3))
    month = _MONTHS.get(mon_raw[:3]) if not mon_raw.isdigit() else int(mon_raw)
    if not month:
        return None
    try:
        return datetime(year, month, int(day), tzinfo=timezone.utc)
    except ValueError:
        return None


def parse_newsroom_html(html: str, source: Source, region: str,
                        operator: str | None, origin: str,
                        max_links: int = 30) -> list[Item]:
    """Extract article-like links from a newsroom page (testable, no I/O)."""
    soup = BeautifulSoup(html, "html.parser")
    scope = soup
    if source.item_selector:
        selected = soup.select(source.item_selector)
        if selected:
            wrapper = BeautifulSoup("<div></div>", "html.parser")
            for node in selected:
                wrapper.div.append(node)
            scope = wrapper

    base_host = urlsplit(source.url).netloc.removeprefix("www.")
    items: list[Item] = []
    seen_urls: set[str] = set()

    for a in scope.find_all("a", href=True):
        href = a["href"].strip()
        if not href or _SKIP_HINTS.search(href):
            continue
        url = urljoin(source.url, href)
        parts = urlsplit(url)
        if parts.scheme not in ("http", "https"):
            continue
        # stay on the operator's domain (subdomains allowed)
        if not parts.netloc.removeprefix("www.").endswith(base_host):
            continue
        if not _ARTICLE_HINTS.search(parts.path):
            continue
        # article pages have a real path, not just the section root
        if parts.path.rstrip("/") == urlsplit(source.url).path.rstrip("/"):
            continue

        title = " ".join(a.get_text(" ", strip=True).split())
        if len(title) < 25 or len(title) > 300:  # nav links are short
            continue
        if url in seen_urls:
            continue
        seen_urls.add(url)

        url_date, url_has_day = _date_from_url(url)
        published = url_date if url_has_day else None
        if published is None:
            context = a.find_parent(["article", "li", "div"])
            if context is not None:
                published = _date_from_text(context.get_text(" ", strip=True)[:400])
        if published is None:
            published = url_date  # month precision is better than nothing

        items.append(
            Item(
                title=title,
                url=url,
                source_name=source.name or base_host,
                region=region,
                operator=operator,
                published=published,
                origin=origin,
            )
        )
        if len(items) >= max_links:
            break
    return items


def collect_newsroom(source: Source, region: str, operator: str | None,
                     origin: str, http_cfg: dict) -> list[Item]:
    from .http import fetch
    resp = fetch(source.url, http_cfg)
    max_links = int(http_cfg.get("max_links_per_newsroom", 30))
    return parse_newsroom_html(resp.text, source, region, operator,
                               origin, max_links)
