"""End-to-end pipeline test with mocked HTTP (no network, no LLM)."""
import shutil
from pathlib import Path

import httpx
import pytest

from telco_radar import pipeline

FIXTURES = Path(__file__).parent / "fixtures"
PROJECT_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture()
def project(tmp_path):
    """Minimal project root with real config structure."""
    shutil.copytree(PROJECT_ROOT / "config", tmp_path / "config")
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
""", encoding="utf-8")
    (tmp_path / "config" / "news_sources.yaml").write_text(
        """
news_sources:
  - name: "Sample Telco News"
    type: rss
    url: "https://example-telconews.com/feed"
""", encoding="utf-8")
    return tmp_path


@pytest.fixture()
def fake_http(monkeypatch):
    feed = (FIXTURES / "sample_feed.xml").read_bytes()
    newsroom = (FIXTURES / "sample_newsroom.html").read_text()

    def fake_get(url, **kwargs):
        request = httpx.Request("GET", url)
        if "feed" in url:
            return httpx.Response(200, content=feed, request=request)
        return httpx.Response(200, text=newsroom, request=request)

    monkeypatch.setattr(httpx, "get", fake_get)


def test_full_run_no_llm(project, fake_http):
    report = pipeline.run(project, use_llm=False)

    assert report.exists()
    text = report.read_text(encoding="utf-8")
    assert "Telco Radar" in text
    assert "Unlimited 5G+" in text            # newsroom item made it in
    assert "eSIM roaming" in text             # rss item made it in
    assert "Old story" not in text            # freshness filter worked

    site = project / "site"
    assert (site / "index.html").exists()
    assert (site / "style.css").exists()
    assert list((site / "reports").glob("*.html"))

    # state persisted
    assert (project / "data" / "state" / "seen.jsonl").exists()


def test_second_run_reports_nothing_new(project, fake_http):
    pipeline.run(project, use_llm=False)
    report2 = pipeline.run(project, use_llm=False)

    text = report2.read_text(encoding="utf-8")
    assert "davon neu: 0" in text             # everything already seen
    assert "Unlimited 5G+" not in text        # not re-reported
