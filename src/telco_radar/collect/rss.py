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

MAX_ENTRIES_PER_FEED = 60


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
    for key in ("published", "updated", "date", "dc_date", "pubDate"):
        raw = entry.get(key)
        if isinstance(raw, str) and raw.strip():
            parsed_text = _date_from_text(raw[:60])
            if parsed_text:
                return parsed_text
    return _datum_aus_url((entry.get("link") or "").strip())


_URL_DATUM = re.compile(
    r"/(20\d{2})[-/_]?(0[1-9]|1[0-2])[-/_]?(0[1-9]|[12]\d|3[01])(?![\d])"
)


def _datum_aus_url(url: str) -> datetime | None:
    m = _URL_DATUM.search(url or "")
    if not m:
        return None
    try:
        return datetime(
            int(m.group(1)), int(m.group(2)), int(m.group(3)), tzinfo=timezone.utc
        )
    except ValueError:
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
        for m in entry.get(feld) or []:
            url = (m.get("url") or "").strip()
            if url:
                return url
    for link in entry.get("links") or []:
        if link.get("rel") == "enclosure" and str(link.get("type") or "").startswith(
            "image"
        ):
            url = (link.get("href") or "").strip()
            if url:
                return url
    blob = (entry.get("summary") or "") + "".join(
        c.get("value") or "" for c in (entry.get("content") or [])
    )
    m = _IMG_IM_TEXT.search(blob)
    return m.group(1).strip() if m else ""


VOLLTEXT_MINDESTLAENGE = 1200


def _entry_volltext(entry, summary: str) -> str:
    """Der Artikeltext, wenn der Feed ihn schon mitliefert.

    feedparser legt <content:encoded> unter `entry.content` ab - das Feld,
    in dem WordPress und viele andere Redaktionssysteme den ganzen Artikel
    transportieren und das dieses Projekt bis zum 13.08.2026 nicht gelesen
    hat. Gemessen ueber 1329 Eintraege: 45,2 % haben eins, in 33,2 % steht
    Volltext. Das ist der mit Abstand billigste Zugewinn im ganzen Vorhaben
    - er kostet keinen einzigen zusaetzlichen Abruf.

    Der Teaser zaehlt hier mit: bei 9,7 % der Eintraege steht der ganze
    Artikel in `description` (TeleSemana: 15 289 Zeichen). Das laengere von
    beiden gewinnt, ohne Kappung - die 600 Zeichen gelten fuer `summary`
    und damit fuer den Analysten, nicht fuer dieses Feld.
    """
    bester = ""
    for c in entry.get("content") or []:
        wert = _strip_html(c.get("value") or "")
        if len(wert) > len(bester):
            bester = wert
    if len(summary) > len(bester):
        bester = summary
    return bester if len(bester) >= VOLLTEXT_MINDESTLAENGE else ""


def parse_feed_bytes(
    raw: bytes,
    source: Source,
    region: str,
    operator: str | None,
    origin: str,
    max_entries: int | None = None,
) -> list[Item]:
    """Parse feed content into Items (separated from fetching for testability)."""
    feed = feedparser.parse(raw)
    if feed.bozo and not feed.entries:
        raise ValueError(f"unparseable feed: {feed.bozo_exception}")

    default_name = source.name or source.url
    items: list[Item] = []
    for entry in feed.entries[: (max_entries or MAX_ENTRIES_PER_FEED)]:
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
                volltext=_entry_volltext(entry, summary),
            )
        )
    return items


_PARSE_RETRIES = 2
_PARSE_RETRY_WAIT = 1.5


def collect_rss(
    source: Source, region: str, operator: str | None, origin: str, http_cfg: dict
) -> list[Item]:
    from .http import fetch

    last_exc: ValueError | None = None
    for attempt in range(_PARSE_RETRIES + 1):
        resp = fetch(source.url, http_cfg, source.timeout_seconds, source.headers)
        try:
            return parse_feed_bytes(
                resp.content,
                source,
                region,
                operator,
                origin,
                max_entries=int(
                    http_cfg.get("max_entries_per_feed") or MAX_ENTRIES_PER_FEED
                ),
            )
        except ValueError as exc:
            last_exc = exc
            if attempt < _PARSE_RETRIES:
                log.info("Feed %s did not parse (%s) - retrying", source.url, exc)
                time.sleep(_PARSE_RETRY_WAIT * (attempt + 1))
    raise last_exc
