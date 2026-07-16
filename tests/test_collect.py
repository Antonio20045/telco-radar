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
