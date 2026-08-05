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

# Praefix der Pseudo-Regionsschluessel, unter denen die Themenfelder durch die
# Pipeline laufen. Ein Themenfeld bekommt damit einen eigenen Analysten (wie
# eine Region), ohne dass die Regionslogik der Watchlist es je fuer einen
# Betreiber haelt: Alias-Tagging und Rundlauf-Sortierung fassen nur an, was
# unter einem echten Regionsschluessel steht.
THEME_PREFIX = "thema:"


def is_theme_key(key: str) -> bool:
    return key.startswith(THEME_PREFIX)


@dataclass
class Source:
    type: str  # yaml source type == kind (rss|json_api|newsroom|newsroom_js|official)
    url: str
    name: str = ""
    item_selector: str | None = None  # optional CSS selector for newsroom pages
    kind: str = ""  # display/crawl kind (see above); defaults from type
    label: str = ""  # human label for the source card
    plan: str = ""   # for 'official' sources: why not yet crawled + the plan
    link_template: str | None = None  # json_api: build item URL from a record
    # field when the payload has no direct url/link field, e.g. only a slug
    # ("https://example.com/news?slug={slug}"). Formatted with str.format_map
    # against the raw record dict.
    headers: dict | None = None  # extra HTTP headers for this source, e.g. the
    # public client apikey a newsroom's own JSON API expects (Verizon). Not a
    # secret of ours - it is embedded in the operator's public page.
    exclude_url_pattern: str | None = None  # drop items whose URL matches this
    # regex. Some newsrooms mirror every release in a second language under a
    # path like /news/es/, which would otherwise enter as a separate item.
    timeout_seconds: float | None = None  # per-source HTTP timeout override,
    # for hosts that are simply slow to reach from the CI runner (KT's Korean
    # API ran into the global 20s connect timeout in 3 of 9 runs).
    region: str = ""  # news_sources.yaml only: default region for this
    # source's items when no watchlist operator is named in the headline.
    # Without it every regional trade-press feed lands in "Global": in run #77
    # Europe, North America and Africa finished with ZERO scored items while
    # Global got 86, because tag_news_regions only assigns a region when it
    # recognises an operator name. A Polish feed is about Poland even when the
    # headline says "UKE" and not "Orange".
    theme: str = ""  # tech_sources.yaml only: the theme key this source feeds
    # ("ki", "geraete", "chips", ...). Operators carry a region instead; a
    # theme source has no region, which is exactly why it lives in its own
    # file and not in the watchlist (see config/tech_sources.yaml).
    # Redaktionelle Angaben, die bei der ABNAHME der Quelle bekannt sind und
    # nicht gemessen werden koennen. Bei 130 Quellen reichte dafuer ein
    # deutscher Kommentar im YAML; bei 1000 nicht mehr, weil dann niemand mehr
    # nachlesen kann, woher eine Quelle stammt und ob sie je geprueft wurde.
    # Das Gegenstueck - seit wann bekannt, wann zuletzt geliefert - pflegt die
    # Pipeline in data/state/quellen_register.json.
    herkunft: str = ""    # z. B. "muster:cision", "rel=alternate", "Recherche"
    abgenommen: str = ""  # ISO-Datum des bestandenen Abnahme-Checks
    allow_short_titles: bool = False  # newsroom(_js): explicit opt-in to drop
    # the 25-char title-length floor down to 6, for sources whose real
    # content is legitimately terse (e.g. RNS/regulatory-announcement
    # tables like "Q1 Results") - NOT a general item_selector relaxation,
    # since that would also let short nav-link text ("About Us") through.

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
    # Themenfelder (config/tech_sources.yaml): KI-Anbieter, Geraete, Chips,
    # Netzausruester, Satellit, Regulierung. Kein Betreiber, keine Region -
    # deshalb eine eigene Liste und ein eigener Namensraum. Die Schluessel
    # tragen das Praefix THEME_PREFIX, damit sie sich in items_by_region nie
    # mit einem Regionsschluessel der Watchlist ueberschneiden koennen.
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
                    link_template=s.get("link_template"),
                    headers=s.get("headers"),
                    exclude_url_pattern=s.get("exclude_url_pattern"),
                    timeout_seconds=s.get("timeout_seconds"),
                    herkunft=s.get("herkunft", ""),
                    abgenommen=str(s.get("abgenommen", "") or ""),
                    allow_short_titles=s.get("allow_short_titles", False),
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

    # `kind` steuert BEIDES: welcher Collector laeuft (collect/__init__.py) und
    # wie die Quelle auf der Website beschriftet wird. Bis 08/2026 stand hier
    # fest "trade_press" - was funktionierte, solange jede Fachpressequelle ein
    # RSS-Feed war, weil collect_rss beide Werte annimmt. Beim Quellen-Ausbau
    # ist die erste Fachpresse mit JSON-API dazugekommen (Capacity Media), und
    # die lief damit in den RSS-Parser: "unparseable feed: syntax error". Der
    # Typ gewinnt jetzt, "trade_press" bleibt nur der Normalfall RSS.
    news_sources = []
    for s in (news.get("news_sources") or []):
        stype = s.get("type", "rss")
        news_sources.append(Source(
            type=stype, url=s["url"], name=s.get("name", s["url"]),
            kind=s.get("kind") or ("trade_press" if stype == "rss" else stype),
            label=s.get("name", ""),
            item_selector=s.get("item_selector"),
            link_template=s.get("link_template"),
            headers=s.get("headers"),
            exclude_url_pattern=s.get("exclude_url_pattern"),
            timeout_seconds=s.get("timeout_seconds"),
            allow_short_titles=s.get("allow_short_titles", False),
            region=s.get("region", ""),
            herkunft=s.get("herkunft", ""),
            abgenommen=str(s.get("abgenommen", "") or "")))

    unbekannt = {s.region for s in news_sources
                 if s.region and s.region not in region_names}
    if unbekannt:
        raise ValueError(
            "news_sources.yaml nennt Regionen, die die Watchlist nicht kennt: "
            + ", ".join(sorted(unbekannt)))

    tech_sources, theme_names = _load_tech_sources(cfg_dir / "tech_sources.yaml")

    n_crawled = sum(len(o.crawled_sources) for o in operators)
    log.info(
        "Config loaded: %d operators in %d regions, %d crawlable operator "
        "sources, %d trade-press sources, %d theme sources in %d themes",
        len(operators), len(region_names) - 1, n_crawled, len(news_sources),
        len(tech_sources), len(theme_names),
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
        for s in (theme.get("quellen") or []):
            stype = s.get("type", "rss")
            sources.append(Source(
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
            ))
    return sources, names
