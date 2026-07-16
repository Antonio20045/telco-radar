"""Load and validate the YAML configuration (watchlist, news sources, settings)."""
from __future__ import annotations

import logging
import urllib.parse
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

log = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# Source kinds:
#   newsroom     : HTML press page, scraped for article links (crawled)
#   rss          : RSS/Atom feed (crawled, has dates)
#   news_search  : auto-generated Google News feed for one operator (crawled)
#   official     : operator's official press page - shown as a reference link
#                  on the Quellen page, NOT crawled (used when the newsroom is
#                  JS-only / bot-protected but we still want a real URL to show)
# --------------------------------------------------------------------------- #
_CRAWLED_KINDS = {"newsroom", "rss", "news_search"}


def google_news_rss(query: str, window_days: int = 8,
                    hl: str = "en-US", gl: str = "US",
                    ceid: str = "US:en") -> str:
    """Build a Google News RSS search URL for one operator/topic."""
    q = f"{query} when:{window_days}d"
    return ("https://news.google.com/rss/search?q="
            + urllib.parse.quote(q)
            + f"&hl={hl}&gl={gl}&ceid={ceid}")


@dataclass
class Source:
    type: str  # "rss" | "newsroom"
    url: str
    name: str = ""
    item_selector: str | None = None  # optional CSS selector for newsroom pages
    kind: str = ""  # display kind (see above); defaults from type
    label: str = ""  # human label for the source card, e.g. publisher/newsroom

    def __post_init__(self) -> None:
        if not self.kind:
            self.kind = self.type

    @property
    def crawlable(self) -> bool:
        return self.kind in _CRAWLED_KINDS


@dataclass
class Operator:
    name: str
    region_key: str
    region_name: str
    country: str = ""
    aliases: list[str] = field(default_factory=list)
    sources: list[Source] = field(default_factory=list)

    @property
    def match_terms(self) -> list[str]:
        return [self.name] + list(self.aliases)

    @property
    def crawled_sources(self) -> list[Source]:
        return [s for s in self.sources if s.crawlable]


@dataclass
class Config:
    root: Path
    settings: dict[str, Any]
    operators: list[Operator]
    news_sources: list[Source]
    region_names: dict[str, str]

    @property
    def lookback_days(self) -> int:
        return int(self.settings.get("lookback_days", 8))


def _load_yaml(path: Path) -> dict:
    with open(path, "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def load_config(root: Path) -> Config:
    """Read config/{settings,watchlist,news_sources}.yaml below *root*."""
    cfg_dir = root / "config"
    settings = _load_yaml(cfg_dir / "settings.yaml")
    watchlist = _load_yaml(cfg_dir / "watchlist.yaml")
    news = _load_yaml(cfg_dir / "news_sources.yaml")

    # Optional extra operators (kept in a separate file so the main, richly
    # commented watchlist stays clean). Merged by region key.
    extra = _load_yaml(cfg_dir / "watchlist_extra.yaml")
    if extra.get("regions"):
        base_regions = watchlist.setdefault("regions", {})
        for rk, rgn in extra["regions"].items():
            if rk in base_regions:
                base_regions[rk].setdefault("operators", []).extend(
                    rgn.get("operators") or [])
            else:
                base_regions[rk] = rgn

    auto_news = bool(settings.get("auto_operator_news", True))
    window = int(settings.get("lookback_days", 8))

    operators: list[Operator] = []
    region_names: dict[str, str] = {"global": "Global"}
    for region_key, region in (watchlist.get("regions") or {}).items():
        region_name = region.get("name", region_key)
        region_names[region_key] = region_name
        for op in region.get("operators") or []:
            sources: list[Source] = []
            for s in (op.get("sources") or []):
                stype = s.get("type", "newsroom")
                sources.append(Source(
                    type=stype,
                    url=s["url"],
                    name=op["name"],
                    item_selector=s.get("item_selector"),
                    kind=s.get("kind", stype),
                    label=s.get("label", ""),
                ))
            # Auto per-operator Google News feed: guarantees every operator has
            # a crawlable, dated, linked source (unless explicitly opted out).
            if auto_news and not op.get("no_auto_news"):
                query = op.get("news_query") or f'"{op["name"]}"'
                sources.append(Source(
                    type="rss",
                    url=google_news_rss(query, window_days=window),
                    name=op["name"],
                    kind="news_search",
                    label="Google News",
                ))
            operators.append(Operator(
                name=op["name"],
                region_key=region_key,
                region_name=region_name,
                country=op.get("country", ""),
                aliases=op.get("aliases") or [],
                sources=sources,
            ))

    news_sources = [
        Source(type=s.get("type", "rss"), url=s["url"],
               name=s.get("name", s["url"]), kind="trade_press",
               label=s.get("name", ""))
        for s in (news.get("news_sources") or [])
    ]

    log.info(
        "Config loaded: %d operators in %d regions, %d trade-press sources, "
        "auto-news=%s",
        len(operators), len(region_names) - 1, len(news_sources), auto_news,
    )
    return Config(
        root=root,
        settings=settings,
        operators=operators,
        news_sources=news_sources,
        region_names=region_names,
    )
