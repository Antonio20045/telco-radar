"""Tests for the novelty layer (seen store, freshness, topic memory)."""
from datetime import datetime, timedelta, timezone

from telco_radar.dedupe import ReportedTopics, SeenStore, filter_fresh
from telco_radar.models import Item, normalize_url


def _item(title, url, days_old=None):
    published = None
    if days_old is not None:
        published = datetime.now(timezone.utc) - timedelta(days=days_old)
    return Item(title=title, url=url, source_name="test", published=published)


def test_normalize_url_strips_noise():
    assert normalize_url("https://www.Example.com/News/?utm_source=x&utm_medium=y") \
        == normalize_url("http://example.com/News")


def test_seen_store_roundtrip(tmp_path):
    store_path = tmp_path / "seen.jsonl"
    a = _item("Story A", "https://x.com/news/a")
    b = _item("Story B", "https://x.com/news/b")

    store = SeenStore(store_path)
    assert store.filter_new([a, b]) == [a, b]
    store.add([a])

    # reload from disk -> a is known, b is new
    store2 = SeenStore(store_path)
    assert store2.filter_new([a, b]) == [b]
    assert len(store2) == 1


def test_filter_new_dedupes_within_run(tmp_path):
    store = SeenStore(tmp_path / "seen.jsonl")
    a1 = _item("Same story", "https://x.com/news/a?utm_source=feed1")
    a2 = _item("Same story again", "https://x.com/news/a?utm_source=feed2")
    assert len(store.filter_new([a1, a2])) == 1  # same normalized URL


def test_filter_fresh():
    fresh = _item("fresh", "https://x.com/1", days_old=2)
    stale = _item("stale", "https://x.com/2", days_old=30)
    undated = _item("undated", "https://x.com/3")
    kept = filter_fresh([fresh, stale, undated], lookback_days=8)
    assert fresh in kept and undated in kept and stale not in kept


def test_filter_fresh_rejects_far_future_dates():
    future = _item("scheduled", "https://x.com/future", days_old=-3)
    assert future not in filter_fresh([future], lookback_days=8)


def test_reported_topics_memory(tmp_path):
    path = tmp_path / "topics.jsonl"
    topics = ReportedTopics(path, max_entries=2)
    topics.add(["Vodafone: OneNumber Launch", "Jio: AI plan", "MTN: MoMo"], "2026-07-16")

    reloaded = ReportedTopics(path, max_entries=2)
    assert reloaded.recent() == ["Jio: AI plan", "MTN: MoMo"]  # capped at 2
