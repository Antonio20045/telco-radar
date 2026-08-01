"""Tests for the JSON news-API collector (fixtures, no network)."""
import json
from datetime import datetime, timezone

from telco_radar.collect.json_api import parse_json_bytes
from telco_radar.config import Source


def test_flat_list_payload():
    """Original shape: a bare top-level list of records (e.g. Vodafone Group)."""
    payload = json.dumps([
        {"newsTitle": "Vodafone launches OneNumber", "newsUrl": "/news/one-number",
         "newsDate": "14 Jul 2026", "newsDesc": "A short summary."},
    ]).encode()
    src = Source(type="json_api", url="https://www.vodafone.com/news/feed", name="Vodafone Group")
    items = parse_json_bytes(payload, src, "europa", "Vodafone Group", "operator")
    assert len(items) == 1
    assert items[0].url == "https://www.vodafone.com/news/one-number"
    assert items[0].published == datetime(2026, 7, 14, tzinfo=timezone.utc)


def test_wrapped_data_list_payload():
    """dict with a top-level 'data'/'items' list, per the original design."""
    payload = json.dumps({"data": [
        {"title": "Item A", "url": "https://example.com/a", "date": "2026-07-01"},
    ]}).encode()
    src = Source(type="json_api", url="https://example.com/api", name="Example")
    items = parse_json_bytes(payload, src, "europa", "Example", "operator")
    assert len(items) == 1
    assert items[0].title == "Item A"


def test_nested_grouped_payload_like_jio():
    """Jio-style: records grouped in a dict keyed by month, several levels
    deep, with no single flat list anywhere - the recursive fallback must
    find and merge every group."""
    payload = json.dumps({
        "data": {"attributes": {
            "pressReleaseYears": [2026, 2025],
            "pressRelease": {
                "Jun-2026": [{"title": "June release", "link": "/pr/june.pdf",
                             "releaseDate": "2026-06-14"}],
                "Apr-2026": [{"title": "April release", "link": "/pr/april.pdf",
                             "releaseDate": "2026-04-13"}],
            },
        }},
    }).encode()
    src = Source(type="json_api", url="https://www.jio.com/jcms-api/v1-press-release-page",
                name="Reliance Jio")
    items = parse_json_bytes(payload, src, "asien", "Reliance Jio", "operator")
    titles = {i.title for i in items}
    assert titles == {"June release", "April release"}
    assert all(i.url.startswith("https://www.jio.com/pr/") for i in items)


def test_link_template_from_slug_like_indosat():
    payload = json.dumps({"data": {"items": [
        {"title": "Indosat announces AI plan", "slug": "indosat-ai-plan",
         "publishedAt": "2026-07-28T12:34:01.989Z"},
    ]}}).encode()
    src = Source(type="json_api", url="https://web-api.ioh.co.id/api/content-hub/public",
                name="Indosat Ooredoo Hutchison",
                link_template="https://ioh.co.id/EN/contents?slug={slug}")
    items = parse_json_bytes(payload, src, "asien", "Indosat Ooredoo Hutchison", "operator")
    assert len(items) == 1
    assert items[0].url == "https://ioh.co.id/EN/contents?slug=indosat-ai-plan"
    assert items[0].published.date().isoformat() == "2026-07-28"


def test_split_year_month_day_fields_like_pldt():
    payload = json.dumps([
        {"title": "PLDT launches new plan", "year": "2026", "month": "July", "day": "28",
         "view_node": "/drupal/article/pldt-launches-new-plan"},
    ]).encode()
    src = Source(type="json_api", url="https://cms.pldt.com/drupal/api/v1/newsroom-article-list",
                name="PLDT", link_template="https://cms.pldt.com{view_node}")
    items = parse_json_bytes(payload, src, "asien", "PLDT", "operator")
    assert len(items) == 1
    assert items[0].url == "https://cms.pldt.com/drupal/article/pldt-launches-new-plan"
    assert items[0].published == datetime(2026, 7, 28, tzinfo=timezone.utc)


def test_records_without_title_or_url_are_skipped():
    payload = json.dumps([{"date": "2026-07-01"}, {"title": "No link here"}]).encode()
    src = Source(type="json_api", url="https://example.com/api", name="Example")
    items = parse_json_bytes(payload, src, "europa", "Example", "operator")
    assert items == []


def test_publication_date_key_like_iliad():
    """Iliad's Strapi backend dates records under "publication_date"; without
    that key every one of its 40 items arrived undated and sank below the
    analyst's per-region cap."""
    payload = json.dumps({"newsItems": [
        {"title": "Free Max Plan adds destinations", "url": "free-max-plan",
         "publication_date": "2026-07-21T07:00:00.000Z"},
    ]}).encode()
    src = Source(type="json_api", url="https://api.example.fr/news", name="Iliad")
    items = parse_json_bytes(payload, src, "europa", "Iliad", "operator")
    assert len(items) == 1
    assert items[0].published == datetime(2026, 7, 21, tzinfo=timezone.utc)


def test_date_embedded_in_label_like_vodafone_idea():
    """Vodafone Idea returns {"newsDate": "Tamil Nadu | 10 Jun, 2026"} - the
    date has to be pulled out of the surrounding label."""
    payload = json.dumps([
        {"newsTitle": "Vi launches 5G", "newsUrl": "/news/vi-5g",
         "newsDate": "Tamil Nadu | 10 Jun, 2026"},
    ]).encode()
    src = Source(type="json_api", url="https://www.myvi.in/api/news", name="Vodafone Idea")
    items = parse_json_bytes(payload, src, "asien", "Vodafone Idea", "operator")
    assert len(items) == 1
    assert items[0].published == datetime(2026, 6, 10, tzinfo=timezone.utc)


def test_records_are_sorted_by_date_before_the_cap():
    """stc returns 281 releases whose first 40 are from 2021/2022, so capping
    before sorting made the newsroom look four years stale while the current
    releases sat further down the same response."""
    payload = json.dumps([
        {"title": f"Old release {n}", "link": f"https://example.com/old-{n}",
         "date": "May 27, 2021"} for n in range(45)
    ] + [
        {"title": "Current release", "link": "https://example.com/current",
         "date": "Jun 25, 2026"},
    ]).encode()
    src = Source(type="json_api", url="https://example.com/api", name="stc")
    items = parse_json_bytes(payload, src, "africa", "stc", "operator")
    assert items[0].title == "Current release"
    assert len(items) == 40


def test_html_entities_in_titles_are_decoded():
    """stc's content fragments carry &quot; literally; the report would print
    it verbatim."""
    payload = json.dumps([
        {"title": "stc wins the &quot;Excellence Award&quot; at WSIS &amp; more",
         "link": "https://example.com/a", "date": "2026-07-01"},
    ]).encode()
    src = Source(type="json_api", url="https://example.com/api", name="stc")
    items = parse_json_bytes(payload, src, "africa", "stc", "operator")
    assert items[0].title == 'stc wins the "Excellence Award" at WSIS & more'
