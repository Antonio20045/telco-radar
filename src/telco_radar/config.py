"""Load and validate the YAML configuration (watchlist, news sources, settings)."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

log = logging.getLogger(__name__)


@dataclass
class Source:
    type: str  # "rss" | "newsroom"
    url: str
    name: str = ""
    item_selector: str | None = None  # optional CSS selector for newsroom pages


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

    operators: list[Operator] = []
    region_names: dict[str, str] = {"global": "Global"}
    for region_key, region in (watchlist.get("regions") or {}).items():
        region_name = region.get("name", region_key)
        region_names[region_key] = region_name
        for op in region.get("operators") or []:
            sources = [
                Source(
                    type=s.get("type", "newsroom"),
                    url=s["url"],
                    name=op["name"],
                    item_selector=s.get("item_selector"),
                )
                for s in (op.get("sources") or [])
            ]
            operators.append(
                Operator(
                    name=op["name"],
                    region_key=region_key,
                    region_name=region_name,
                    country=op.get("country", ""),
                    aliases=op.get("aliases") or [],
                    sources=sources,
                )
            )

    news_sources = [
        Source(type=s.get("type", "rss"), url=s["url"], name=s.get("name", s["url"]))
        for s in (news.get("news_sources") or [])
    ]

    log.info(
        "Config loaded: %d operators in %d regions, %d industry news sources",
        len(operators), len(region_names) - 1, len(news_sources),
    )
    return Config(
        root=root,
        settings=settings,
        operators=operators,
        news_sources=news_sources,
        region_names=region_names,
    )
