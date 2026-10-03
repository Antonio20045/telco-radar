"""End-to-end pipeline test with mocked HTTP (no network, no LLM)."""

import json
import shutil
from datetime import UTC, date, datetime
from functools import partial
from pathlib import Path

import httpx
import pytest
from test_collect import SAMPLE_FEED, SAMPLE_NEWSROOM

from telco_radar import dedupe, pipeline
from telco_radar.report import geraete_bewegung

JETZT = datetime(2026, 7, 15, 12, 0, tzinfo=UTC)
FIXTURE_LOOKBACK = (JETZT.date() - date(2026, 7, 13)).days + 1

PROJECT_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture()
def project(tmp_path):
    """Minimal project root with real config structure."""
    shutil.copytree(PROJECT_ROOT / "config", tmp_path / "config")
    # this end-to-end test exercises the newsroom parser, so enable that path
    # (production keeps crawl_newsrooms: false) and drop auto Bing feeds/focus
    settings = (tmp_path / "config" / "settings.yaml").read_text(encoding="utf-8")
    settings += (
        "\ncrawl_newsrooms: true\nauto_operator_news: false\nfocus_competitors: []\n"
    )
    # The copied config/ also brings config/promo_sources.yaml. Its "js" brands
    # go through Playwright (collect/newsroom_js.py), which the fake_http
    # fixture below cannot mock (it only patches httpx.get) - so leaving the
    # promo stage on here would make this "offline" test hit the real network.
    settings += "\npromo_enabled: false\n"
    (tmp_path / "config" / "settings.yaml").write_text(settings, encoding="utf-8")
    # shrink watchlist to one operator + one news feed for the test
    (tmp_path / "config" / "watchlist.yaml").write_text(
        """
regions:
  europe:
    name: "Europa"
    operators:
      - name: "Example Telco"
        aliases: ["ExTel"]
        country: "DE"
        sources:
          - type: newsroom
            url: "https://www.example-telco.com/news"
""",
        encoding="utf-8",
    )
    (tmp_path / "config" / "news_sources.yaml").write_text(
        """
news_sources:
  - name: "Sample Telco News"
    type: rss
    url: "https://example-telconews.com/feed"
""",
        encoding="utf-8",
    )
    return tmp_path


@pytest.fixture()
def fake_http(monkeypatch):
    feed = SAMPLE_FEED.encode("utf-8")
    newsroom = SAMPLE_NEWSROOM

    def fake_get(url, **kwargs):
        request = httpx.Request("GET", url)
        if "feed" in url:
            return httpx.Response(200, content=feed, request=request)
        return httpx.Response(200, text=newsroom, request=request)

    monkeypatch.setattr(httpx, "get", fake_get)
    # Die Artikelseiten der Beispielquelle haben kein og:image; ohne diese Zeile
    # fragte report/bilder.py sie über einen eigenen httpx.Client im Netz ab.
    monkeypatch.setattr(pipeline.report_bilder, "og_bild", lambda url, client: "")
    monkeypatch.setattr(
        pipeline, "filter_fresh", partial(dedupe.filter_fresh, jetzt=JETZT)
    )


def test_full_run_no_llm(project, fake_http):
    # Keep the fixture stable as the calendar advances: the newest fixture
    # item is dated 14 Jul 2026, so the production 8-day window is borderline
    # on 22 Jul depending on the current clock time.
    report, _ = pipeline.run(project, use_llm=False, lookback_days=FIXTURE_LOOKBACK)

    assert report.exists()
    text = report.read_text(encoding="utf-8")
    assert "Telco Radar" in text
    assert "Unlimited 5G+" in text  # newsroom item made it in
    assert "eSIM roaming" in text  # rss item made it in
    assert "Old story" not in text  # freshness filter worked

    site = project / "site"
    assert (site / "index.html").exists()
    assert (site / "style.css").exists()
    assert list((site / "reports").glob("*.html"))

    # state persisted
    assert (project / "data" / "state" / "seen.jsonl").exists()


def test_berichts_json_traegt_den_geraetebewegungsblock(project, fake_http):
    """Der Versand rendert nur aus dem Berichts-JSON; ohne den Schluessel
    "geraete_bewegung" fehlt der Mail der Wochenblock der Geraeteseite.
    Erwartung: derselbe Block, den `fuer_bericht` fuer diesen Projektstand
    und dieses Berichtsdatum unabhaengig liefert."""
    report, _ = pipeline.run(project, use_llm=False, lookback_days=FIXTURE_LOOKBACK)
    daten = json.loads(report.with_suffix(".json").read_text(encoding="utf-8"))
    assert daten["date"] == report.stem
    assert "geraete_bewegung" in daten
    erwartet = geraete_bewegung.fuer_bericht(
        project, date.fromisoformat(report.stem), report.parent
    )
    assert daten["geraete_bewegung"] == json.loads(
        json.dumps(erwartet, ensure_ascii=False)
    )


def test_second_run_reports_nothing_new(project, fake_http):
    pipeline.run(project, use_llm=False, lookback_days=FIXTURE_LOOKBACK)
    report2, _ = pipeline.run(project, use_llm=False, lookback_days=FIXTURE_LOOKBACK)

    text = report2.read_text(encoding="utf-8")
    assert "davon neu: 0" in text  # everything already seen
    assert "Unlimited 5G+" not in text  # not re-reported


def test_interleave_gives_every_source_a_slot():
    """The analyst only reads the first `max_items_per_region` items, so one
    high-volume feed must not take the whole budget from the operator
    newsrooms."""

    from telco_radar.models import Item
    from telco_radar.pipeline import _interleave_by_source

    def mk(source, day, operator=None):
        return Item(
            title=f"{source} {day}",
            url=f"https://x.test/{source}/{day}",
            source_name=source,
            region="europa",
            operator=operator,
            published=datetime(2026, 7, day, tzinfo=UTC),
        )

    items = [mk("Light Reading", d) for d in (31, 30, 29, 28, 27)]
    items += [mk("Orange Newsroom", 26, "Orange"), mk("Telia Newsroom", 25, "Telia")]

    ordered = _interleave_by_source(items)
    # both operator newsrooms must appear within the first three items
    top3 = {i.operator or i.source_name for i in ordered[:3]}
    assert "Orange" in top3 and "Telia" in top3
    # nothing is lost, and the freshest item still leads
    assert len(ordered) == len(items)
    assert ordered[0].source_name == "Light Reading"


def test_interleave_keeps_dated_sources_ahead_of_undated():

    from telco_radar.models import Item
    from telco_radar.pipeline import _interleave_by_source

    dated = Item(
        title="dated",
        url="https://x.test/a",
        source_name="A",
        region="europa",
        operator="A",
        published=datetime(2026, 7, 30, tzinfo=UTC),
    )
    undated = Item(
        title="undated",
        url="https://x.test/b",
        source_name="B",
        region="europa",
        operator="B",
        published=None,
    )
    assert _interleave_by_source([undated, dated])[0].title == "dated"


def test_analyst_reads_every_item_when_uncapped():
    """The seen-store marks every new item as known regardless of whether an
    analyst read it, so a dropped item is dropped for good. max_items=None
    (config 0) therefore means: assess everything."""
    from unittest.mock import patch

    from telco_radar.analyze import agents

    # Zwei volle Stapel plus ein Rest - die Zahl wird aus BATCH_SIZE
    # gerechnet, nicht festgeschrieben: als Literal (37 bei Stapelgroesse 15)
    # zerbrach der Test an der Erhoehung auf 24 am 27.08.2026, obwohl die
    # gepruefte Zusicherung "es wird nichts weggeworfen" unberuehrt blieb.
    anzahl = agents.BATCH_SIZE * 2 + 7
    items = [_mk_item(n) for n in range(anzahl)]
    seen_batches = []

    def fake_complete(system, user, model=None, max_tokens=None, **kw):
        seen_batches.append(user)
        return '{"region_summary": "s", "highlights": []}'

    with patch.object(agents, "complete", fake_complete):
        agents.analyze_region("Europa", items, model="m", max_items=None)
    assert len(seen_batches) == 3
    for n in range(anzahl):
        assert any(
            f"item-{n}\n" in b or f"item-{n} " in b or f"item-{n}" in b
            for b in seen_batches
        ), n

    seen_batches.clear()
    with patch.object(agents, "complete", fake_complete):
        agents.analyze_region("Europa", items, model="m", max_items=agents.BATCH_SIZE)
    assert len(seen_batches) == 1  # old behaviour still available


def _mk_item(n):

    from telco_radar.models import Item

    return Item(
        title=f"item-{n}",
        url=f"https://x.test/{n}",
        source_name="S",
        region="europa",
        operator=f"Op{n}",
        published=datetime(2026, 7, 30, tzinfo=UTC),
    )


def test_editor_gets_everything_by_default():
    """Default is no limit: a weekly briefing that silently skips half the
    week is not a briefing, and the seen-store gives no second chance."""
    from telco_radar.analyze.editor import EDITOR_HIGHLIGHT_BUDGET, _select_for_editor

    assert EDITOR_HIGHLIGHT_BUDGET == 0
    clean = {"Global": {"highlights": [{"t": i, "relevance": 1} for i in range(500)]}}
    out, omitted = _select_for_editor(clean, EDITOR_HIGHLIGHT_BUDGET)
    assert out == clean and omitted == 0


def test_editor_budget_keeps_breadth_across_regions():
    """Fallback for providers that force a shorter prompt: one busy region
    must not crowd out the rest."""
    from telco_radar.analyze.editor import _select_for_editor

    clean = {
        "Global": {"highlights": [{"t": i, "relevance": 5} for i in range(120)]},
        "Ozeanien": {"highlights": [{"t": "o", "relevance": 3}]},
    }
    out, omitted = _select_for_editor(clean, 90)
    assert len(out["Ozeanien"]["highlights"]) == 1
    assert len(out["Global"]["highlights"]) == 89
    assert omitted == 31

    # under budget: nothing is touched
    small = {"Europa": {"highlights": [{"t": 1, "relevance": 2}]}}
    out2, omitted2 = _select_for_editor(small, 90)
    assert out2 == small and omitted2 == 0
