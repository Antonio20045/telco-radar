"""Tests for the sitewide search index (report/html.py::_build_search_index).

Acceptance test from claude/suche-marktrecherche-konzept.md: a search for
"Perplexity" must surface the known differentiation-library hits (SK Telecom,
Deutsche Telekom, ...) even when the term does not appear in that week's
report highlights at all - the real-world case is that this term lives almost
exclusively in the differentiation DB, not in the weekly press digest.
"""
from telco_radar.report.html import _build_search_index


def _report(date, **highlight_kw):
    base = {"title": "Generic headline", "summary": "Generic summary text.",
            "operator": "X", "url": "http://example.com/a", "relevance": 3,
            "category": "Produktlaunch", "region": "Europa", "date": date,
            "source": "src"}
    base.update(highlight_kw)
    return {"date": date, "regions": {"Europa": {"highlights": [base]}}}


def _diff_entry(**kw):
    base = {"id": "http://example.com/perplexity", "theme": "ki",
            "operator": "SK Telecom", "region": "Asien",
            "what": "Perplexity Pro 12 Monate gratis fuer alle Kunden.",
            "url": "http://example.com/perplexity", "source": "perplexity.ai",
            "date": "2024-02", "why": "KI-Bundle als Tarif-Bonus.",
            "first_seen": "2026-06-15", "last_verified": "2026-07-21",
            "status": "aktiv"}
    base.update(kw)
    return base


def _find(q, items):
    q = q.lower()
    return [i for i in items
            if q in (i["title"] + " " + i.get("summary", "") + " "
                     + i.get("operator", "")).lower()]


def test_bericht_item_is_indexed_with_deep_link_to_its_own_week():
    report = _report("2026-07-20", title="Operator launches something")
    out = _build_search_index([report], [], {})
    bericht_items = [i for i in out if i["kind"] == "bericht"]
    assert len(bericht_items) == 1
    item = bericht_items[0]
    assert item["deep_link"] == "reports/2026-07-20.html"
    assert item["operator"] == "X"


def test_perplexity_findable_via_differentiation_even_absent_from_the_weekly_report():
    report = _report("2026-07-20")  # no mention of Perplexity in this week's report
    diff_entries = [
        _diff_entry(operator="SK Telecom", theme="ki"),
        _diff_entry(id="http://example.com/telekom", operator="Deutsche Telekom",
                    url="http://example.com/telekom",
                    what="Perplexity fest in die MeinMagenta-App integriert."),
    ]
    theme_labels = {"ki": "KI & Assistenten"}
    out = _build_search_index([report], diff_entries, theme_labels)

    hits = _find("perplexity", out)
    assert len(hits) == 2
    assert {h["operator"] for h in hits} == {"SK Telecom", "Deutsche Telekom"}
    assert all(h["kind"] == "differenzierung" for h in hits)
    assert all(h["category"] == "KI & Assistenten" for h in hits)
    assert all(h["deep_link"] == "differenzierung.html#dz-theme-ki" for h in hits)


def test_search_index_is_empty_when_theres_nothing_to_index():
    assert _build_search_index([], [], {}) == []
