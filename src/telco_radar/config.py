"""Load and validate the YAML configuration (watchlist, news sources, settings)."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

log = logging.getLogger(__name__)


_CRAWLED_KINDS = {"rss", "json_api", "newsroom", "newsroom_js"}

THEME_PREFIX = "thema:"


def is_theme_key(key: str) -> bool:
    return key.startswith(THEME_PREFIX)


@dataclass
class Source:
    type: str
    url: str
    name: str = ""
    item_selector: str | None = None
    kind: str = ""
    label: str = ""
    plan: str = ""
    link_template: str | None = None
    headers: dict | None = None
    exclude_url_pattern: str | None = None
    timeout_seconds: float | None = None
    region: str = ""
    theme: str = ""
    herkunft: str = ""
    abgenommen: str = ""
    allow_short_titles: bool = False

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
    tech_sources: list[Source] = field(default_factory=list)
    theme_names: dict[str, str] = field(default_factory=dict)

    @property
    def lookback_days(self) -> int:
        return int(self.settings.get("lookback_days", 8))

    @property
    def bereich_names(self) -> dict[str, str]:
        """Regionen UND Themenfelder - alles, was ein eigener Analyst ist."""
        return {**self.region_names, **self.theme_names}

    @property
    def themes(self) -> list[tuple[str, str]]:
        """(Schluessel, Anzeigename) je Themenfeld, in Konfigurationsreihenfolge."""
        return list(self.theme_names.items())


def _load_yaml(path: Path) -> dict:
    with open(path, "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def load_config(root: Path) -> Config:
    """Read config/{settings,watchlist,news_sources}.yaml below *root*."""
    cfg_dir = root / "config"
    settings = _load_yaml(cfg_dir / "settings.yaml")
    watchlist = _load_yaml(cfg_dir / "watchlist.yaml")
    news = _load_yaml(cfg_dir / "news_sources.yaml")

    extra = _load_yaml(cfg_dir / "watchlist_extra.yaml")
    if extra.get("regions"):
        base_regions = watchlist.setdefault("regions", {})
        for rk, rgn in extra["regions"].items():
            if rk in base_regions:
                base_regions[rk].setdefault("operators", []).extend(
                    rgn.get("operators") or []
                )
            else:
                base_regions[rk] = rgn

    operators: list[Operator] = []
    region_names: dict[str, str] = {"global": "Global"}
    for region_key, region in (watchlist.get("regions") or {}).items():
        region_name = region.get("name", region_key)
        region_names[region_key] = region_name
        for op in region.get("operators") or []:
            sources: list[Source] = []
            for s in op.get("sources") or []:
                stype = s.get("type", "newsroom")
                sources.append(
                    Source(
                        type=stype,
                        url=s["url"],
                        name=op["name"],
                        item_selector=s.get("item_selector"),
                        kind=s.get("kind", stype),
                        label=s.get("label", ""),
                        plan=s.get("plan", ""),
                        link_template=s.get("link_template"),
                        headers=s.get("headers"),
                        exclude_url_pattern=s.get("exclude_url_pattern"),
                        timeout_seconds=s.get("timeout_seconds"),
                        herkunft=s.get("herkunft", ""),
                        abgenommen=str(s.get("abgenommen", "") or ""),
                        allow_short_titles=s.get("allow_short_titles", False),
                    )
                )
            operators.append(
                Operator(
                    name=op["name"],
                    region_key=region_key,
                    region_name=region_name,
                    country=op.get("country", ""),
                    website=op.get("website", ""),
                    aliases=op.get("aliases") or [],
                    sources=sources,
                )
            )

    news_sources = []
    for s in news.get("news_sources") or []:
        stype = s.get("type", "rss")
        news_sources.append(
            Source(
                type=stype,
                url=s["url"],
                name=s.get("name", s["url"]),
                kind=s.get("kind") or ("trade_press" if stype == "rss" else stype),
                label=s.get("name", ""),
                item_selector=s.get("item_selector"),
                link_template=s.get("link_template"),
                headers=s.get("headers"),
                exclude_url_pattern=s.get("exclude_url_pattern"),
                timeout_seconds=s.get("timeout_seconds"),
                allow_short_titles=s.get("allow_short_titles", False),
                region=str(s.get("region", "") or ""),
                herkunft=s.get("herkunft", ""),
                abgenommen=str(s.get("abgenommen", "") or ""),
            )
        )
    for s in news_sources:
        if s.region and s.region not in region_names:
            log.warning(
                "news_sources.yaml: %s hat region: %r - diese Region "
                "steht nicht in der Watchlist, die Vorgabe wird "
                "ignoriert",
                s.name,
                s.region,
            )
            s.region = ""

    tech_sources, theme_names = _load_tech_sources(cfg_dir / "tech_sources.yaml")

    n_crawled = sum(len(o.crawled_sources) for o in operators)
    log.info(
        "Config loaded: %d operators in %d regions, %d crawlable operator "
        "sources, %d trade-press sources, %d theme sources in %d themes",
        len(operators),
        len(region_names) - 1,
        n_crawled,
        len(news_sources),
        len(tech_sources),
        len(theme_names),
    )
    return Config(
        root=root,
        settings=settings,
        operators=operators,
        news_sources=news_sources,
        region_names=region_names,
        focus_competitors=settings.get("focus_competitors") or [],
        tech_sources=tech_sources,
        theme_names=theme_names,
    )


def _load_tech_sources(path: Path) -> tuple[list[Source], dict[str, str]]:
    """Themenquellen laden (config/tech_sources.yaml).

    Bewusst eine eigene Datei statt zusaetzlicher Eintraege in der Watchlist:
    Nvidia, die GSMA oder Qualcomm sind keine Netzbetreiber. In der Watchlist
    haetten sie eine Region und einen Alias-Eintrag - beides falsch, und das
    Alias-Tagging der Fachpresse wuerde anfangen, jede Meldung mit "Nvidia" im
    Titel einer Region zuzuschlagen. Hier tragen sie stattdessen ein
    Themen-Tag und laufen als eigener Analyst durch die Pipeline.

    Fehlt die Datei, laeuft alles wie vorher - der Ausbau ist additiv.
    """
    if not path.exists():
        return [], {}
    raw = _load_yaml(path)
    sources: list[Source] = []
    names: dict[str, str] = {}
    for theme_key, theme in (raw.get("themen") or {}).items():
        key = THEME_PREFIX + theme_key
        names[key] = theme.get("name", theme_key)
        for s in theme.get("quellen") or []:
            stype = s.get("type", "rss")
            sources.append(
                Source(
                    type=stype,
                    url=s["url"],
                    name=s.get("name", s["url"]),
                    item_selector=s.get("item_selector"),
                    kind=s.get("kind", stype),
                    label=s.get("label", "") or s.get("name", ""),
                    plan=s.get("plan", ""),
                    link_template=s.get("link_template"),
                    headers=s.get("headers"),
                    exclude_url_pattern=s.get("exclude_url_pattern"),
                    timeout_seconds=s.get("timeout_seconds"),
                    herkunft=s.get("herkunft", ""),
                    abgenommen=str(s.get("abgenommen", "") or ""),
                    theme=key,
                    allow_short_titles=s.get("allow_short_titles", False),
                )
            )
    return sources, names
