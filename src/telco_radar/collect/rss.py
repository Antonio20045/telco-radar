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

# Wie viele Eintraege eines Feeds gelesen werden. Der Wert ist ein DECKEL,
# kein Ziel - und er ist am 08.08.2026 von 40 auf 60 gestiegen. Der Grund:
# genau die zehn ergiebigsten Quellen lieferten exakt 40 Meldungen, also den
# Deckel und nicht ihren Bestand (Light Reading, Telecoms.com, The Fast Mode).
# Zwischen einem Freitags- und einem Dienstagslauf liegen vier Tage; eine
# Fachpresse mit 12 Meldungen am Tag laeuft in dieser Zeit ueber 40 hinaus,
# und was dabei aus dem Feed faellt, sieht dieses Projekt nie.
#
# Der Preis ist Laufzeit: mehr Meldungen heisst mehr Analysten-Stapel. Er ist
# seit dem Ereignis-Clustering kleiner geworden (analyze/clustering.py bricht
# die Mehrfachberichterstattung heraus, bevor bewertet wird), und das
# Job-Timeout liegt bei 50 Minuten gegen zuletzt 27,4 gemessene.
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
    # Letzter Ausweg: das Datum im LINK. Manche Behoerden- und
    # Redaktionssysteme liefern ueberhaupt kein <pubDate> - der RSS-Feed der
    # Bundesnetzagentur zum Beispiel hat weder pubDate noch dc:date, seine
    # Pressemitteilungen tragen das Datum aber im Pfad
    # (/Pressemitteilungen/DE/2026/20260806_Agnes.html).
    #
    # Ohne diesen Ausweg fiel eine solche Quelle durch Kriterium 3 des
    # Abnahme-Checks (>= 80 % datiert) - zu Recht, denn eine undatierte
    # Meldung sortiert ans Ende und ist damit faktisch unsichtbar. Der Weg
    # ueber den Link macht aus "unsichtbar" ein normales Datum, ohne dass
    # irgendwo eine Ausnahme eingetragen werden muesste.
    return _datum_aus_url((entry.get("link") or "").strip())


# /2026/08/06/, /2026-08-06-, /20260806_ - die drei Formen, in denen ein
# Datum in einem Pfad vorkommt. Bewusst NICHT sechsstellig (260806): das
# faende jede Artikelnummer.
_URL_DATUM = re.compile(
    r"/(20\d{2})[-/_]?(0[1-9]|1[0-2])[-/_]?(0[1-9]|[12]\d|3[01])(?![\d])")


def _datum_aus_url(url: str) -> datetime | None:
    m = _URL_DATUM.search(url or "")
    if not m:
        return None
    try:
        return datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)),
                        tzinfo=timezone.utc)
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
                     operator: str | None, origin: str,
                     max_entries: int | None = None) -> list[Item]:
    """Parse feed content into Items (separated from fetching for testability)."""
    feed = feedparser.parse(raw)
    if feed.bozo and not feed.entries:
        raise ValueError(f"unparseable feed: {feed.bozo_exception}")

    default_name = source.name or source.url
    items: list[Item] = []
    for entry in feed.entries[:(max_entries or MAX_ENTRIES_PER_FEED)]:
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
            return parse_feed_bytes(
                resp.content, source, region, operator, origin,
                max_entries=int(http_cfg.get("max_entries_per_feed")
                                or MAX_ENTRIES_PER_FEED))
        except ValueError as exc:
            last_exc = exc
            if attempt < _PARSE_RETRIES:
                log.info("Feed %s did not parse (%s) - retrying", source.url, exc)
                time.sleep(_PARSE_RETRY_WAIT * (attempt + 1))
    raise last_exc
