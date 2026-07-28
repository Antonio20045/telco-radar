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


def test_newsroom_recognises_non_english_article_hints():
    html = """
    <a href="/wom-en-prensa/ceo-anuncia-nueva-red-5g-en-todo-el-pais">CEO anuncia nueva red 5G en todo el pais</a>
    <a href="/sala-de-imprensa/nova-parceria-de-fibra-otica-anunciada-hoje">Nova parceria de fibra optica anunciada hoje</a>
    """
    src = Source(type="newsroom", url="https://example.com/prensa", name="S")
    items = parse_newsroom_html(html, src, "latin_america", "Example", "operator")
    assert len(items) == 2


def test_newsroom_item_selector_bypasses_article_hint_requirement():
    # Real article slugs with no news/press/media keyword at all (e.g. Turkish
    # operator press releases) - only a real item_selector should let them in.
    html = """
    <div class="relases-card">
      <a href="/turk-telekom-yeni-5g-yatirimi-aciklandi">Turk Telekom yeni 5G yatirimi acikladi bugun</a>
    </div>
    <a href="/turk-telekom-yeni-5g-yatirimi-disaridan">Should be dropped without item_selector present</a>
    """
    src_no_selector = Source(type="newsroom", url="https://example.com/basin", name="S")
    assert parse_newsroom_html(html, src_no_selector, "europe", "Example", "operator") == []

    src_with_selector = Source(type="newsroom", url="https://example.com/basin",
                               name="S", item_selector=".relases-card")
    items = parse_newsroom_html(html, src_with_selector, "europe", "Example", "operator")
    assert len(items) == 1
    assert "5G yatirimi" in items[0].title


def test_newsroom_item_selector_falls_back_to_container_text_for_short_anchor():
    # Card layout where the <a> only wraps a thumbnail/date, real headline
    # lives in a sibling element inside the same selected container.
    html = """
    <div class="mediaItem">
      <a href="/media/press/2026-07-launch"><span class="mediaDate">28 Jul</span></a>
      <div class="mediaExcerpt">Operator launches new nationwide 5G rollout across regional areas</div>
    </div>
    """
    src = Source(type="newsroom", url="https://example.com/news",
                 name="S", item_selector=".mediaItem")
    items = parse_newsroom_html(html, src, "asia", "Example", "operator")
    assert len(items) == 1
    assert "nationwide 5G rollout" in items[0].title


def test_newsroom_allows_pdf_press_releases_but_not_other_pdfs():
    html = """
    <a href="/media/press/p260326.pdf">China Mobile Announces 2025 Annual Results Today</a>
    <a href="/esg/cg/sc.pdf">Sustainability Committee Terms of Reference Document</a>
    """
    src = Source(type="newsroom", url="https://example.com/media/press.php", name="S")
    items = parse_newsroom_html(html, src, "asia", "Example", "operator")
    assert len(items) == 1
    assert "Annual Results" in items[0].title


def test_newsroom_item_selector_allows_pdf_attachment_outside_press_path():
    # TPG Telecom: the real release is a PDF attached from an explicitly
    # hand-picked card, not under any /press/ path - item_selector alone
    # should be enough of a signal to let it through.
    html = """
    <div class="mediaItem">
      <h5>TPG Telecom achieves its 100 per cent renewable electricity commitment</h5>
      <a href="/sites/default/files/media-release/tpg-renewable.pdf">View PDF</a>
    </div>
    """
    src = Source(type="newsroom", url="https://example.com/media_release",
                 name="S", item_selector=".mediaItem")
    items = parse_newsroom_html(html, src, "oceania", "Example", "operator")
    assert len(items) == 1
    assert "renewable electricity" in items[0].title


def test_newsroom_item_selector_falls_back_to_title_attribute():
    # Deutsche Telekom: a self-closing <a> whose only text lives in title=.
    html = """
    <a class="media-link" href="/en/media/media-information/archive/quantum-link"
       title="Media information: European Quantum Communication Infrastructure"></a>
    """
    src = Source(type="newsroom", url="https://example.com/en/media/media-information",
                 name="S", item_selector=".media-link")
    items = parse_newsroom_html(html, src, "europe", "Example", "operator")
    assert len(items) == 1
    assert "Quantum Communication" in items[0].title
