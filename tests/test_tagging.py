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


# --------------------------------------------------------------------------- #
# Vorgabe-Region fuer Fachpressequellen
# --------------------------------------------------------------------------- #

def test_vorgabe_region_wird_von_betreibername_ueberschrieben():
    """Steht ein Betreiber in der Ueberschrift, gewinnt dessen Region.

    Die Vorgabe ist eine Auffanglinie, keine Festlegung: eine polnische
    Meldung ueber Vodafone Deutschland gehoert nach Europa - was hier
    zufaellig dasselbe ist -, eine ueber MTN nach Afrika.
    """
    from telco_radar.collect import tag_news_regions
    from telco_radar.config import Operator, Source
    from telco_radar.models import Item

    mtn = Operator(name="MTN Group", country="ZA",
                   region_key="africa_middle_east",
                   region_name="Afrika & Naher Osten", website="mtn.com",
                   sources=[Source(type="rss", url="https://x/f", name="MTN")])
    items = [
        Item(title="MTN Group meldet Rekordquartal in Nigeria", url="https://a/1",
             source_name="Telepolis", region="europe", origin="industry_news"),
        Item(title="UKE versteigert 700-MHz-Band neu", url="https://a/2",
             source_name="Telepolis", region="europe", origin="industry_news"),
    ]
    tag_news_regions(items, [mtn])
    assert items[0].region == "africa_middle_east"   # Betreiber gewinnt
    assert items[1].region == "europe"               # Vorgabe bleibt


def test_unbekannte_vorgabe_region_wird_abgelehnt(tmp_path):
    """Ein Tippfehler in der Region darf nicht still in "Global" enden."""
    import pytest
    import yaml
    from telco_radar.config import load_config

    cfg = tmp_path / "config"
    cfg.mkdir()
    (cfg / "watchlist.yaml").write_text(yaml.safe_dump(
        {"regions": {"europe": {"name": "Europa", "operators": []}}}),
        encoding="utf-8")
    (cfg / "news_sources.yaml").write_text(yaml.safe_dump(
        {"news_sources": [{"name": "X", "type": "rss",
                           "url": "https://x/f", "region": "europa"}]}),
        encoding="utf-8")
    (cfg / "watchlist_extra.yaml").write_text("regions: {}\n", encoding="utf-8")
    (cfg / "tech_sources.yaml").write_text("themen: {}\n", encoding="utf-8")
    (cfg / "settings.yaml").write_text("language: de\n", encoding="utf-8")
    with pytest.raises(ValueError, match="Regionen"):
        load_config(tmp_path)
