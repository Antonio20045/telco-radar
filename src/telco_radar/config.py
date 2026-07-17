"""Load and validate the YAML configuration (watchlist, news sources, settings)."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

log = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# Source kinds. EVERY crawlable operator source points at the operator's OWN
# official domain. Third-party telco trade press is a separate, explicitly
# labelled second layer (see news_sources.yaml) - never an operator's primary
# source.
#
#   rss         : RSS/Atom feed on the operator's domain (httpx + feedparser)
#   json_api    : the operator newsroom's own JSON news API (httpx + json)
#   newsroom    : operator press page whose article links are already in the
#                 static HTML (httpx)
#   newsroom_js : operator press page that is JavaScript-rendered -> crawled
#                 with a headless browser (Playwright) in the run environment
#   official    : operator press page that is bot-blocked / not yet crawlable;
#                 shown as a VERIFIED reference link only (NOT crawled), always
#                 with a documented plan to enable crawling later
# --------------------------------------------------------------------------- #
_CRAWLED_KINDS = {"rss", "json_api", "newsroom", "newsroom_js"}


@dataclass
class Source:
    type: str  # yaml source type == kind (rss|json_api|newsroom|newsroom_js|official)
    url: str
    name: str = ""
    item_selector: str | None = None  # optional CSS selector for newsroom pages
    kind: str = ""  # display/crawl kind (see above); defaults from type
    label: str = ""  # human label for the source card
    plan: str = ""   # for 'official' sources: why not yet crawled + the plan

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
    website: str = ""
    aliases: list[str] = field(default_factory=list)
    sources: list[Source] = field(default_factory=list)

    @property
    def match_terms(self) -> list[str]:
        return [self.name] + list(self.aliases)

    @property
    def crawled_sources(self) -> list[Source]:
        return [s for s in self.sources if s.crawlable]

    @property
    def primary_source(self) -> "Source | None":
        return self.sources[0] if self.sources else None


@dataclass
class Config:
    root: Path
    settings: dict[str, Any]
    operators: list[Operator]
    news_sources: list[Source]
    region_names: dict[str, str]
    focus_competitors: list[dict] = field(default_factory=list)

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

    # Optional extra operators (kept in a separate file so the main watchlist
    # stays clean). Merged by region key.
    extra = _load_yaml(cfg_dir / "watchlist_extra.yaml")
    if extra.get("regions"):
        base_regions = watchlist.setdefault("regions", {})
        for rk, rgn in extra["regions"].items():
            if rk in base_regions:
                base_regions[rk].setdefault("operators", []).extend(
                    rgn.get("operators") or [])
            else:
                base_regions[rk] = rgn

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
                    plan=s.get("plan", ""),
                ))
            operators.append(Operator(
                name=op["name"],
                region_key=region_key,
                region_name=region_name,
                country=op.get("country", ""),
                website=op.get("website", ""),
                aliases=op.get("aliases") or [],
                sources=sources,
            ))

    news_sources = [
        Source(type=s.get("type", "rss"), url=s["url"],
               name=s.get("name", s["url"]), kind="trade_press",
               label=s.get("name", ""))
        for s in (news.get("news_sources") or [])
    ]

    n_crawled = sum(len(o.crawled_sources) for o in operators)
    log.info(
        "Config loaded: %d operators in %d regions, %d crawlable operator "
        "sources, %d trade-press sources",
        len(operators), len(region_names) - 1, n_crawled, len(news_sources),
    )
    return Config(
        root=root,
        settings=settings,
        operators=operators,
        news_sources=news_sources,
        region_names=region_names,
        focus_competitors=settings.get("focus_competitors") or [],
    )
