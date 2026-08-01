"""Tests for RSS + newsroom parsing (fixtures, no network)."""
from datetime import datetime, timezone
from pathlib import Path

from telco_radar.collect.newsroom import parse_newsroom_html
from telco_radar.collect.rss import parse_feed_bytes
from telco_radar.config import Source

FIXTURES = Path(__file__).parent / "fixtures"


def test_rss_parsing():
    raw = (FIXTURES / "sample_feed.xml").read_bytes()
    src = Source(type="rss", url="https://example-telconews.com/feed",
                 name="Sample Telco News")
    items = parse_feed_bytes(raw, src, "global", None, "industry_news")
    assert len(items) == 3
    first = items[0]
    assert "eSIM roaming" in first.title
    assert first.published == datetime(2026, 7, 14, 9, 0, tzinfo=timezone.utc)
    assert first.origin == "industry_news"
    assert first.summary.startswith("Vodafone introduced")


def test_rss_tracking_params_do_not_change_id():
    raw = (FIXTURES / "sample_feed.xml").read_bytes()
    src = Source(type="rss", url="https://example-telconews.com/feed", name="S")
    items = parse_feed_bytes(raw, src, "global", None, "industry_news")
    from telco_radar.models import Item
    clean = Item(title=items[0].title,
                 url="https://example-telconews.com/2026/07/vodafone-esim-roaming-pass",
                 source_name="S")
    assert items[0].id == clean.id  # utm_source stripped before hashing


def test_newsroom_parsing():
    html = (FIXTURES / "sample_newsroom.html").read_text()
    src = Source(type="newsroom", url="https://www.example-telco.com/news",
                 name="Example Telco")
    items = parse_newsroom_html(html, src, "europe", "Example Telco", "operator")
    titles = [i.title for i in items]

    assert len(items) == 2  # external domain, short link, footer links skipped
    assert any("Unlimited 5G+" in t for t in titles)
    assert any("StreamCo" in t for t in titles)
    # date extracted from URL path /2026/07/
    assert all(i.published is not None and i.published.year == 2026 for i in items)
    # relative link resolved against source URL
    assert items[0].url.startswith("https://www.example-telco.com/")


def test_newsroom_respects_item_selector():
    html = (FIXTURES / "sample_newsroom.html").read_text()
    src = Source(type="newsroom", url="https://www.example-telco.com/news",
                 name="Example Telco", item_selector="footer")
    items = parse_newsroom_html(html, src, "europe", "Example Telco", "operator")
    assert items == []  # footer links are all skip-hinted or too short


def test_newsroom_item_selector_bypasses_url_keyword_heuristic():
    # Some CMS card layouts (e.g. Presspage) use opaque slugs with no
    # news/press/media keyword in the path - only a configured item_selector
    # can tell these apart from navigation, since the URL heuristic can't.
    html = (FIXTURES / "sample_card_newsroom.html").read_text()
    src = Source(type="newsroom_js", url="https://www.example-telco.com/press-browser/",
                 name="Example Telco", item_selector="a.card")
    items = parse_newsroom_html(html, src, "europe", "Example Telco", "operator")
    assert len(items) == 2
    assert all("/content/" in i.url for i in items)


def test_newsroom_item_selector_still_applies_skip_hints():
    html = (FIXTURES / "sample_card_newsroom.html").read_text()
    src = Source(type="newsroom_js", url="https://www.example-telco.com/press-browser/",
                 name="Example Telco", item_selector="nav a")
    items = parse_newsroom_html(html, src, "europe", "Example Telco", "operator")
    assert items == []  # mailto: link is still skip-hinted even with a selector


def test_newsroom_parses_ordinal_day_month_year_dates():
    # UK-style press dates ("28th May 2026") appear as plain surrounding text,
    # not in the URL - seen on threemediacentre.co.uk press-release cards.
    html = """
    <article><a href="/news/example-telco-launches-a-thing">Example Telco launches a thing</a>
      <span>Press release 28th May 2026</span></article>
    """
    src = Source(type="newsroom", url="https://example.com/news", name="S")
    items = parse_newsroom_html(html, src, "europe", "Example", "operator")
    assert len(items) == 1
    assert items[0].published.date().isoformat() == "2026-05-28"


def test_newsroom_skips_navigation_and_parses_common_date_formats():
    html = """
    <a href="/media-relations">Media contacts for journalists</a>
    <a href="/support/articledetail?artid=123">How to reset your router</a>
    <article><a href="/press-release/07-2026/new-service">New customer service launch</a>
      <time>July 9, 2026</time></article>
    """
    src = Source(type="newsroom", url="https://example.com/news", name="S")
    items = parse_newsroom_html(html, src, "europe", "Example", "operator")
    assert len(items) == 1
    assert items[0].published.date().isoformat() == "2026-07-09"


def test_rss_falls_back_to_human_readable_date():
    """Fierce Network prints "Jul 31, 2026 12:57pm" instead of RFC822, so
    feedparser leaves published_parsed empty. Undated items sort below the
    analyst's per-region cap, so the busiest trade-press feed would never be
    read - the collector must parse the raw string instead."""
    raw = b"""<?xml version="1.0" encoding="UTF-8"?>
    <rss version="2.0"><channel><title>Fierce-style</title>
      <item>
        <title>NTIA tees up 4.4 GHz band</title>
        <link>https://example.com/ntia-4-4-ghz</link>
        <description>Spectrum news.</description>
        <pubDate>Jul 31, 2026 12:57pm</pubDate>
      </item>
    </channel></rss>"""
    src = Source(type="rss", url="https://example.com/rss/xml", name="Fierce-style")
    items = parse_feed_bytes(raw, src, "global", None, "industry_news")
    assert len(items) == 1
    assert items[0].published == datetime(2026, 7, 31, tzinfo=timezone.utc)


def test_url_date_ignores_numeric_id_after_a_year_in_the_slug():
    """Deutsche Telekom's ".../fifa-wm-2030-1116606" parsed as 16 Nov 2030,
    so the release was discarded as "published in the future" instead of
    using the date printed on the card."""
    from telco_radar.collect.newsroom import _date_from_url

    assert _date_from_url("https://x.test/detail/fifa-wm-2030-1116606") == (None, False)
    # real date paths keep working
    assert _date_from_url("https://x.test/news/2026/07/31/foo") == (
        datetime(2026, 7, 31, tzinfo=timezone.utc), True)
