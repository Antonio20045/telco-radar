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
import re
from html import unescape
from datetime import datetime, timezone
from urllib.parse import urljoin, urlsplit

from ..config import Source
from ..models import Item

log = logging.getLogger(__name__)

_TITLE_KEYS = ("newsTitle", "title", "headline", "name", "articleSubtitle",
              "alternative")
_URL_KEYS = ("newsUrl", "url", "link", "href", "path")
# Ordered by trust: an explicit publication date beats a generic "created"/
# "updated" timestamp, which for some CMSes is the day an editor touched the
# record rather than the day the release went out.
_DATE_KEYS = ("newsDate", "date", "published", "publishedDate", "pubDate",
             "releaseDate", "publishedAt", "field_news_date_raw", "publishDate",
             "publication_date", "publicationDate", "publication_date_display",
             "datePublished", "date_published", "news_date", "post_date",
             "createdDt", "created_at", "createdAt")
_DESC_KEYS = ("newsDesc", "description", "summary", "excerpt", "field_summary")

_DATE_FORMATS = (
    "%d %b %Y", "%d %B %Y", "%Y-%m-%d", "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%dT%H:%M:%SZ", "%d/%m/%Y", "%b %d, %Y", "%B %d, %Y",
)


_TAG_RE = re.compile(r"<[^>]+>")

# Records are read up to MAX_RECORDS, then sorted newest-first and cut to
# MAX_ITEMS, so a long unsorted archive still yields its newest releases.
MAX_RECORDS = 1200
MAX_ITEMS = 250
_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)


# Some CMS content-fragment models (e.g. stc's press-release fragments) use
# a generic "call to action" label as the subtitle/title field on older
# records instead of the real headline ({"articleSubtitle": "Details", ...})
# - the real headline for those records is only recoverable from a longer
# text field (description/body), never from this field, so treat these
# values as absent rather than returning a useless title.
_TITLE_PLACEHOLDERS = {"details", "read more", "more", "more details",
                       "learn more", "view details", "click here"}


def _first(d: dict, keys, skip_values: frozenset[str] = frozenset()) -> str:
    for k in keys:
        v = d.get(k)
        if isinstance(v, str) and v.strip() and v.strip().lower() not in skip_values:
            return v.strip()
        # WordPress REST API (wp-json/wp/v2/posts and friends) nests text
        # fields as {"rendered": "..."} instead of a bare string, e.g.
        # {"title": {"rendered": "Headline"}}. Unwrap that shape too.
        if isinstance(v, dict):
            rendered = v.get("rendered")
            if isinstance(rendered, str) and rendered.strip():
                return " ".join(_TAG_RE.sub(" ", rendered).split())
    # Gatsby GraphQL nodes (e.g. Charter Communications' page-data static
    # query dumps) compute derived values - notably the page path/URL - into
    # a nested "fields" object instead of a top-level key, e.g.
    # {"title": "...", "fields": {"url": "/newsroom/..."}}. Check there too.
    fields = d.get("fields")
    if isinstance(fields, dict):
        for k in keys:
            v = fields.get(k)
            if isinstance(v, str) and v.strip() and v.strip().lower() not in skip_values:
                return v.strip()
    return ""


_SPLIT_DATE_KEYS = (("year", "month", "day"), ("Year", "Month", "Day"))


def _split_date(rec: dict) -> str:
    """Some CMS APIs (e.g. PLDT) expose year/month/day as separate string
    fields instead of one combined date string."""
    for year_k, month_k, day_k in _SPLIT_DATE_KEYS:
        year, month, day = rec.get(year_k), rec.get(month_k), rec.get(day_k)
        if year and month and day:
            return f"{day} {month} {year}"
    return ""


# Some APIs don't hand back a clean date string but a composite label, e.g.
# Vodafone Idea's {"newsDate": "Tamil Nadu | 10 Jun, 2026"}. Pulling the date
# out of the surrounding text is the difference between a dated item and one
# that sinks to the bottom of the analyst queue.
_EMBEDDED_DATE_RES = (
    re.compile(r"(\d{4})-(\d{2})-(\d{2})"),
    re.compile(r"(\d{1,2})\s+([A-Za-z]{3,9})\.?,?\s+(\d{4})"),
    re.compile(r"([A-Za-z]{3,9})\.?\s+(\d{1,2}),?\s+(\d{4})"),
)
_MONTH_NAMES = {m: n for n, m in enumerate(
    ("jan", "feb", "mar", "apr", "may", "jun",
     "jul", "aug", "sep", "oct", "nov", "dec"), start=1)}


def _from_parts(year: str, month: str, day: str) -> datetime | None:
    num = _MONTH_NAMES.get(month[:3].lower()) if not month.isdigit() else int(month)
    if not num:
        return None
    try:
        return datetime(int(year), num, int(day), tzinfo=timezone.utc)
    except ValueError:
        return None


def _parse_date(raw: str) -> datetime | None:
    raw = raw.strip()
    if not raw:
        return None
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(raw[:len(fmt) + 6], fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    try:  # leading YYYY-MM-DD (also covers ISO stamps with millis/offset)
        return datetime.strptime(raw[:10], "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except ValueError:
        pass
    # last resort: a date embedded in a longer label
    for pattern in _EMBEDDED_DATE_RES:
        m = pattern.search(raw)
        if not m:
            continue
        a, b, c = m.groups()
        parsed = (_from_parts(a, b, c) if pattern is _EMBEDDED_DATE_RES[0]
                  else _from_parts(c, b, a) if pattern is _EMBEDDED_DATE_RES[1]
                  else _from_parts(c, a, b))
        if parsed:
            return parsed
    return None


def _looks_like_record(rec: dict) -> bool:
    keys = {k.lower() for k in rec}
    return any(k.lower() in keys for k in _TITLE_KEYS)


def _find_record_lists(node, depth: int = 0, max_depth: int = 8) -> list[list[dict]]:
    """Recursively collect every list-of-dicts in *node* that looks like a
    set of press-release records (title-ish key present). Some newsroom
    JSON APIs bury the actual list several levels deep (e.g. grouped by
    month, or nested under result/collection wrappers) instead of exposing
    a single flat array, so a fixed set of top-level keys isn't enough."""
    found: list[list[dict]] = []
    if depth > max_depth:
        return found
    if isinstance(node, list):
        dict_items = [x for x in node if isinstance(x, dict)]
        if dict_items and sum(_looks_like_record(d) for d in dict_items) >= max(1, len(dict_items) // 2):
            found.append(dict_items)
            return found  # a matched list's own items aren't recursed into
        for item in node:
            found.extend(_find_record_lists(item, depth + 1, max_depth))
    elif isinstance(node, dict):
        for val in node.values():
            found.extend(_find_record_lists(val, depth + 1, max_depth))
    return found


def _records(payload) -> list[dict]:
    if isinstance(payload, list):
        cand = [r for r in payload if isinstance(r, dict)]
        if cand:
            return cand
    if isinstance(payload, dict):
        for key in ("data", "items", "results", "news", "articles", "entries"):
            val = payload.get(key)
            if isinstance(val, list):
                return [r for r in val if isinstance(r, dict)]
    # Fallback: recursively hunt for record-shaped lists anywhere in the
    # payload (grouped/nested APIs) and merge them, de-duplicating by title.
    merged: list[dict] = []
    seen_titles: set[str] = set()
    for lst in _find_record_lists(payload):
        for rec in lst:
            title = _first(rec, _TITLE_KEYS)
            if title and title in seen_titles:
                continue
            if title:
                seen_titles.add(title)
            merged.append(rec)
    return merged


def parse_json_bytes(raw: bytes, source: Source, region: str,
                     operator: str | None, origin: str) -> list[Item]:
    payload = json.loads(raw)
    site_root = f"{urlsplit(source.url).scheme}://{urlsplit(source.url).netloc}"
    items: list[Item] = []
    # Do NOT cap before sorting: an API's natural record order is not
    # necessarily chronological. stc returns 281 releases whose first 40 are
    # from 2021/2022, so the newsroom looked four years stale while the 2026
    # releases sat further down the same response.
    for rec in _records(payload)[:MAX_RECORDS]:
        title = _first(rec, _TITLE_KEYS, skip_values=_TITLE_PLACEHOLDERS)
        if not title:
            # The title field held only a generic CTA label (or was empty) -
            # some records' only readable headline is a short HTML-wrapped
            # description (e.g. stc's press-release fragments), so strip
            # tags and use that as a last resort before giving up.
            desc_raw = _first(rec, _DESC_KEYS)
            if desc_raw:
                title = " ".join(_TAG_RE.sub(" ", unescape(desc_raw)).split())
        if not title:
            continue
        rel = ""
        if source.link_template:
            # A configured link_template always wins over a raw url/link
            # field: some APIs expose a bare slug under a key that *looks*
            # like a URL (e.g. Iliad's "url": "free-max-plan-...") which
            # would otherwise be resolved against the wrong host (the API's,
            # not the public site's) by the generic urljoin below.
            try:
                rel = source.link_template.format_map(rec)
            except (KeyError, IndexError):
                rel = ""
        if not rel:
            rel = _first(rec, _URL_KEYS)
        if not rel:
            continue
        url = rel if rel.startswith("http") else urljoin(site_root + "/", rel.lstrip("/"))
        items.append(Item(
            title=unescape(title),
            url=url,
            source_name=source.name or urlsplit(url).netloc.removeprefix("www."),
            region=region,
            operator=operator,
            published=_parse_date(_first(rec, _DATE_KEYS) or _split_date(rec)),
            summary=" ".join(_TAG_RE.sub(" ", unescape(_first(rec, _DESC_KEYS))).split())[:600],
            origin=origin,
        ))
    items.sort(key=lambda i: (i.published is not None,
                             i.published or _EPOCH), reverse=True)
    return items[:MAX_ITEMS]


def collect_json(source: Source, region: str, operator: str | None,
                 origin: str, http_cfg: dict) -> list[Item]:
    from .http import fetch
    resp = fetch(source.url, http_cfg, source.timeout_seconds, source.headers)
    return parse_json_bytes(resp.content, source, region, operator, origin)
