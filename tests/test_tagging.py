"""Tests for region tagging of industry-news items."""
from telco_radar.collect import tag_news_regions
from telco_radar.config import Operator
from telco_radar.models import Item


def _ops():
    return [
        Operator(name="Reliance Jio", region_key="asia", region_name="Asien",
                 aliases=["Jio"]),
        Operator(name="Vodafone Group", region_key="europe", region_name="Europa",
                 aliases=["Vodafone"]),
    ]


def test_tags_by_alias():
    item = Item(title="Jio unveils AI-powered family plan",
                url="https://news.example/jio", source_name="n",
                origin="industry_news")
    tag_news_regions([item], _ops())
    assert item.region == "asia"
    assert item.operator == "Reliance Jio"


def test_longest_match_wins():
    item = Item(title="Vodafone Group posts strong results",
                url="https://news.example/vf", source_name="n",
                origin="industry_news")
    tag_news_regions([item], _ops())
    assert item.operator == "Vodafone Group"


def test_untagged_stays_global():
    item = Item(title="Generic 6G spectrum auction announced",
                url="https://news.example/6g", source_name="n",
                origin="industry_news")
    tag_news_regions([item], _ops())
    assert item.region == "global"


def test_operator_items_untouched():
    item = Item(title="Jio mentioned but this is an operator source item",
                url="https://vodafone.com/news/x", source_name="Vodafone",
                region="europe", operator="Vodafone Group", origin="operator")
    tag_news_regions([item], _ops())
    assert item.region == "europe"
    assert item.operator == "Vodafone Group"
