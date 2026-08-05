"""Themenfelder (config/tech_sources.yaml) als dritte Signalebene.

Der Ausbau bringt Quellen ins Projekt, die KEINE Netzbetreiber sind (Nvidia,
Qualcomm, GSMA, Ofcom). Diese Tests halten die drei Eigenschaften fest, an
denen genau das haengt:

  1. Themenquellen landen NICHT in der Betreiberliste - sonst bekaemen sie
     eine Region und einen Alias-Eintrag, und das Fachpresse-Tagging wuerde
     anfangen, jede Meldung mit "Nvidia" im Titel einer Region zuzuschlagen.
  2. Ihre Bereichsschluessel koennen sich nie mit einem Regionsschluessel der
     Watchlist ueberschneiden (Praefix "thema:").
  3. Fehlt die Datei, laeuft alles wie vorher - der Ausbau ist additiv.
"""
from __future__ import annotations

from pathlib import Path

from telco_radar.collect import collect_all, tag_news_regions
from telco_radar.config import (THEME_PREFIX, is_theme_key, load_config)
from telco_radar.models import Item

WATCHLIST = """
regions:
  europe:
    name: "Europa"
    operators:
      - name: "Example Telco"
        country: "DE"
        website: "example.com"
        aliases: ["Beispiel"]
        sources:
          - type: rss
            url: "https://example.com/feed"
"""

TECH = """
themen:
  ki:
    name: "KI-Anbieter"
    quellen:
      - {name: "OpenAI", type: rss, url: "https://openai.example/news.xml"}
      - {name: "Nvidia", type: rss, url: "https://nvidia.example/feed"}
  regulierung:
    name: "Regulierung & Verbände"
    quellen:
      - {name: "GSMA", type: rss, url: "https://gsma.example/feed"}
"""


def _projekt(tmp_path: Path, mit_themen: bool = True) -> Path:
    cfg = tmp_path / "config"
    cfg.mkdir()
    (cfg / "settings.yaml").write_text("report_language: de\n", encoding="utf-8")
    (cfg / "watchlist.yaml").write_text(WATCHLIST, encoding="utf-8")
    (cfg / "watchlist_extra.yaml").write_text("regions: {}\n", encoding="utf-8")
    (cfg / "news_sources.yaml").write_text(
        'news_sources:\n  - {name: "Fachblatt", type: rss, '
        'url: "https://presse.example/feed"}\n', encoding="utf-8")
    if mit_themen:
        (cfg / "tech_sources.yaml").write_text(TECH, encoding="utf-8")
    return tmp_path


def test_themenquellen_werden_geladen_und_getaggt(tmp_path):
    cfg = load_config(_projekt(tmp_path))

    assert len(cfg.tech_sources) == 3
    assert [s.name for s in cfg.tech_sources] == ["OpenAI", "Nvidia", "GSMA"]
    assert all(s.theme.startswith(THEME_PREFIX) for s in cfg.tech_sources)
    assert cfg.theme_names == {
        "thema:ki": "KI-Anbieter",
        "thema:regulierung": "Regulierung & Verbände",
    }


def test_themen_sind_keine_betreiber(tmp_path):
    """Der teuerste denkbare Fehler waere, sie in die Watchlist zu quetschen."""
    cfg = load_config(_projekt(tmp_path))

    assert [op.name for op in cfg.operators] == ["Example Telco"]
    # Kein Themenschluessel taucht als Region auf ...
    assert not any(is_theme_key(k) for k in cfg.region_names)
    # ... aber bereich_names kennt beides, denn jedes Themenfeld bekommt einen
    # eigenen Analysten wie eine Region.
    assert set(cfg.bereich_names) == set(cfg.region_names) | set(cfg.theme_names)
    assert not (set(cfg.region_names) & set(cfg.theme_names))


def test_ohne_datei_bleibt_alles_wie_vorher(tmp_path):
    cfg = load_config(_projekt(tmp_path, mit_themen=False))

    assert cfg.tech_sources == []
    assert cfg.theme_names == {}
    assert cfg.bereich_names == cfg.region_names


def test_collect_all_nimmt_themenquellen_mit(tmp_path, monkeypatch):
    """Sie muessen im Sammellauf auftauchen - mit Thema als Bereich und
    origin='tech_watch', damit das Alias-Tagging sie in Ruhe laesst."""
    cfg = load_config(_projekt(tmp_path))
    gesehen: list[tuple[str, str, str]] = []

    def fake_collect(source, region, operator, origin, http_cfg):
        gesehen.append((source.url, region, origin))
        return [Item(title="Beispielmeldung mit ausreichender Laenge",
                     url=source.url + "/1", source_name=source.name,
                     region=region, operator=operator, origin=origin)]

    monkeypatch.setattr("telco_radar.collect._collect_source", fake_collect)
    items, results = collect_all(cfg, max_workers=1)

    themen_jobs = {u: (r, o) for u, r, o in gesehen if o == "tech_watch"}
    assert set(themen_jobs) == {
        "https://openai.example/news.xml",
        "https://nvidia.example/feed",
        "https://gsma.example/feed",
    }
    assert themen_jobs["https://openai.example/news.xml"] == ("thema:ki", "tech_watch")
    assert themen_jobs["https://gsma.example/feed"] == \
        ("thema:regulierung", "tech_watch")
    # Betreiber- und Fachpressequellen laufen unveraendert weiter
    assert ("https://example.com/feed", "europe", "operator") in gesehen
    assert ("https://presse.example/feed", "global", "industry_news") in gesehen
    assert len(items) == len(results) == 5


def test_alias_tagging_fasst_themenmeldungen_nicht_an(tmp_path):
    """tag_news_regions darf nur Fachpresse umsortieren. Eine Themenmeldung,
    die zufaellig einen Betreibernamen im Titel hat, muss in ihrem Themenfeld
    bleiben - sonst verschwindet sie zwischen den Betreibermeldungen."""
    cfg = load_config(_projekt(tmp_path))
    thema = Item(title="Beispiel Telco setzt auf neue Chips",
                 url="https://nvidia.example/1", source_name="Nvidia",
                 region="thema:ki", origin="tech_watch")
    presse = Item(title="Beispiel Telco senkt Preise",
                  url="https://presse.example/1", source_name="Fachblatt",
                  region="global", origin="industry_news")

    tag_news_regions([thema, presse], cfg.operators)

    assert (thema.region, thema.operator) == ("thema:ki", None)
    assert (presse.region, presse.operator) == ("europe", "Example Telco")


def test_fachpresse_mit_json_api_laeuft_nicht_in_den_rss_parser(tmp_path):
    """Bis 08/2026 stand fuer jede Fachpressequelle fest kind="trade_press",
    und collect_rss nimmt beide Werte an. Solange jede Fachpresse ein RSS-Feed
    war, fiel das nicht auf. Capacity Media ist die erste mit JSON-API und
    scheiterte deshalb mit "unparseable feed: syntax error" - eine sauber
    abgenommene Quelle, die der Lauf trotzdem nicht lesen konnte."""
    from telco_radar.config import load_config

    cfg_dir = tmp_path / "config"
    cfg_dir.mkdir()
    (cfg_dir / "settings.yaml").write_text("report_language: de\n", encoding="utf-8")
    (cfg_dir / "watchlist.yaml").write_text("regions: {}\n", encoding="utf-8")
    (cfg_dir / "watchlist_extra.yaml").write_text("regions: {}\n", encoding="utf-8")
    (cfg_dir / "news_sources.yaml").write_text(
        'news_sources:\n'
        '  - {name: "Feed-Presse", type: rss, url: "https://a.de/feed"}\n'
        '  - {name: "JSON-Presse", type: json_api, url: "https://b.de/api"}\n',
        encoding="utf-8")

    quellen = {s.name: s for s in load_config(tmp_path).news_sources}
    assert quellen["Feed-Presse"].kind == "trade_press"
    assert quellen["JSON-Presse"].kind == "json_api"
    assert quellen["JSON-Presse"].crawlable
