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


# ------------------------------------- Vorgabe-Region fuer Fachpressequellen
# Der erste der vier Schritte aus CLAUDE.md §9. Lauf #75 schloss EUROPA MIT
# NULL bewerteten Meldungen ab, waehrend "Global" 62 von 92 bekam: seit
# Session 5 stehen deutsche, franzoesische, spanische und italienische Feeds
# in der Liste, und `tag_news_regions` ordnet eine Fachpressemeldung nur zu,
# wenn ein BETREIBERNAME in der Ueberschrift steht.

def test_regionale_fachpresse_landet_in_ihrer_region():
    from pathlib import Path
    from telco_radar.config import load_config
    cfg = load_config(Path(__file__).resolve().parents[1])
    nach_region = {}
    for s in cfg.news_sources:
        nach_region.setdefault(s.region or "global", []).append(s.name)
    # Genau die Quellen, wegen derer der Regionsteil leer blieb.
    assert "teltarif" in nach_region.get("europe", [])
    assert "TeleSemana (LatAm)" in nach_region.get("latin_america", [])
    assert "Telecom Review Africa" in nach_region.get("africa_middle_east", [])
    # Die weltweiten Fachmedien bleiben global - eine Vorgabe fuer sie waere
    # eine Behauptung.
    assert "Light Reading" in nach_region.get("global", [])


def test_betreibername_schlaegt_die_vorgabe_region():
    """Eine Meldung ueber Verizon in einem deutschen Feed gehoert nach
    Nordamerika, nicht nach Europa."""
    from telco_radar.collect import tag_news_regions
    from telco_radar.config import Operator, Source
    from telco_radar.models import Item

    verizon = Operator(name="Verizon", country="US", region_key="north_america",
                       region_name="Nordamerika", aliases=["Verizon"],
                       sources=[Source(type="rss", url="https://x.test/f")])
    aus_deutschem_feed = Item(
        title="Verizon startet neuen Tarif", url="https://teltarif.de/1",
        source_name="teltarif", region="europe", origin="industry_news")
    ohne_betreiber = Item(
        title="Preise für Allnet-Flats sinken weiter", url="https://teltarif.de/2",
        source_name="teltarif", region="europe", origin="industry_news")
    tag_news_regions([aus_deutschem_feed, ohne_betreiber], [verizon])
    assert aus_deutschem_feed.region == "north_america"
    assert ohne_betreiber.region == "europe"


def test_unbekannte_vorgabe_region_wird_verworfen(tmp_path):
    """Eine Region, die es nicht gibt, waere ein eigener Analysten-Bereich mit
    einem Tippfehler als Namen."""
    import shutil
    from pathlib import Path
    from telco_radar.config import load_config
    wurzel = Path(__file__).resolve().parents[1]
    shutil.copytree(wurzel / "config", tmp_path / "config")
    (tmp_path / "config" / "news_sources.yaml").write_text(
        'news_sources:\n'
        '  - {name: "Test", type: rss, url: "https://x.test/f", region: atlantis}\n',
        encoding="utf-8")
    cfg = load_config(tmp_path)
    assert cfg.news_sources[0].region == ""
