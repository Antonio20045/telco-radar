"""JSON news-API collector.

Some operator newsrooms are JavaScript front-ends over a clean JSON API that
returns the press releases. Reading that API directly gives dated, on-domain
items without a headless browser. The mapping is tolerant of common key names
so one collector serves several operators (currently Vodafone Group).

Item URLs are resolved against the API host so relative newsUrl paths become
absolute links on the operator's own domain.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from urllib.parse import urljoin, urlsplit

from ..config import Source
from ..models import Item

log = logging.getLogger(__name__)

_TITLE_KEYS = ("newsTitle", "title", "headline", "name")
_URL_KEYS = ("newsUrl", "url", "link", "href", "path")
_DATE_KEYS = ("newsDate", "date", "published", "publishedDate", "pubDate")
_DESC_KEYS = ("newsDesc", "description", "summary", "excerpt")

_DATE_FORMATS = (
    "%d %b %Y", "%d %B %Y", "%Y-%m-%d", "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%dT%H:%M:%SZ", "%d/%m/%Y", "%b %d, %Y", "%B %d, %Y",
)


def _first(d: dict, keys) -> str:
    for k in keys:
        v = d.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return ""


def _parse_date(raw: str) -> datetime | None:
    raw = raw.strip()
    if not raw:
        return None
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(raw[:len(fmt) + 6], fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    try:  # last resort: leading YYYY-MM-DD
        return datetime.strptime(raw[:10], "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _records(payload) -> list[dict]:
    if isinstance(payload, list):
        return [r for r in payload if isinstance(r, dict)]
    if isinstance(payload, dict):
        for key in ("data", "items", "results", "news", "articles", "entries"):
            val = payload.get(key)
            if isinstance(val, list):
                return [r for r in val if isinstance(r, dict)]
    return []


def parse_json_bytes(raw: bytes, source: Source, region: str,
                     operator: str | None, origin: str) -> list[Item]:
    payload = json.loads(raw)
    site_root = f"{urlsplit(source.url).scheme}://{urlsplit(source.url).netloc}"
    items: list[Item] = []
    for rec in _records(payload)[:40]:
        title = _first(rec, _TITLE_KEYS)
        rel = _first(rec, _URL_KEYS)
        if not title or not rel:
            continue
        url = rel if rel.startswith("http") else urljoin(site_root + "/", rel.lstrip("/"))
        items.append(Item(
            title=title,
            url=url,
            source_name=source.name or urlsplit(url).netloc.removeprefix("www."),
            region=region,
            operator=operator,
            published=_parse_date(_first(rec, _DATE_KEYS)),
            summary=_first(rec, _DESC_KEYS)[:600],
            origin=origin,
        ))
    return items


def collect_json(source: Source, region: str, operator: str | None,
                 origin: str, http_cfg: dict) -> list[Item]:
    from .http import fetch
    resp = fetch(source.url, http_cfg)
    return parse_json_bytes(resp.content, source, region, operator, origin)
