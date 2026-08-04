"""Collectors: fetch items from RSS feeds and HTML newsroom pages."""
from __future__ import annotations

import logging
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from ..config import Config, Source, Operator
from ..models import Item
from .rss import collect_rss
from .json_api import collect_json
from .newsroom import collect_newsroom
from .newsroom_js import collect_newsroom_js

log = logging.getLogger(__name__)


def _collect_source(source: Source, region: str, operator: str | None,
                    origin: str, http_cfg: dict) -> list[Item]:
    """Dispatch a source to the right collector based on its kind."""
    if source.kind in ("rss", "trade_press"):
        items = collect_rss(source, region, operator, origin, http_cfg)
    elif source.kind == "json_api":
        items = collect_json(source, region, operator, origin, http_cfg)
    elif source.kind == "newsroom_js":
        items = collect_newsroom_js(source, region, operator, origin, http_cfg)
    else:
        items = collect_newsroom(source, region, operator, origin, http_cfg)
    if source.exclude_url_pattern:
        # e.g. Verizon mirrors 7 of every 25 releases in Spanish under
        # /about/news/es/ - a different URL, so the seen-store treats it as a
        # separate story and the same news enters the report twice.
        drop = re.compile(source.exclude_url_pattern)
        items = [i for i in items if not drop.search(i.url)]
    return items


def collect_source(source: Source, region: str, operator: str | None = None,
                   origin: str = "operator", http_cfg: dict | None = None) -> list[Item]:
    """Public entry point for a single source - same path the pipeline takes.

    Tools that check sources (validate_sources.py, build_quellen_doc.py) must
    go through this rather than calling a collector directly, otherwise they
    report numbers the pipeline never sees (e.g. Verizon's Spanish mirrors,
    which exclude_url_pattern drops).
    """
    return _collect_source(source, region, operator, origin, http_cfg or {})


def collect_all(cfg: Config, max_workers: int | None = None) -> tuple[list[Item], list[dict]]:
    """Fetch every configured (crawlable) source concurrently.

    Returns (items, source_results). Each source_result is a dict describing
    what happened with that source (status/count/error) so the pipeline can
    build a transparent run log. A failing source never aborts the run.

    max_workers kommt aus settings.yaml (collect_max_workers). Mit dem
    Quellen-Ausbau ist das der Stellhebel gegen die Laufzeit: die Sammelphase
    ist reine Wartezeit auf fremde Server, also skaliert sie fast linear mit
    der Parallelitaet. Eine Kappung der Meldungen waere die falsche Antwort -
    was hier nicht gesammelt wird, sieht kein Analyst je.
    """
    http_cfg = cfg.settings.get("http", {})
    if max_workers is None:
        max_workers = int(cfg.settings.get("collect_max_workers", 4) or 4)
    jobs: list[tuple[Source, str, str | None, str]] = []

    for op in cfg.operators:
        for src in op.crawled_sources:
            jobs.append((src, op.region_key, op.name, "operator"))
    for src in cfg.news_sources:
        jobs.append((src, "global", None, "industry_news"))
    # Themenquellen laufen unter ihrem Themenschluessel als "Region" - so
    # bekommt jedes Themenfeld einen eigenen Analysten, ohne dass die
    # Regionslogik der Watchlist es fuer einen Betreiber haelt.
    for src in cfg.tech_sources:
        if src.crawlable:
            jobs.append((src, src.theme, src.name, "tech_watch"))

    items: list[Item] = []
    results: list[dict] = []
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {
            pool.submit(_collect_source, src, region, operator, origin, http_cfg):
                (src, region, operator, origin)
            for src, region, operator, origin in jobs
        }
        for fut in as_completed(futures):
            src, region, operator, origin = futures[fut]
            rec = {
                "name": operator or src.name,
                "operator": operator,
                "region": region,
                "url": src.url,
                "kind": src.kind,
                "label": src.label or src.kind,
                "origin": origin,
            }
            try:
                got = fut.result()
                items.extend(got)
                rec["status"] = "ok" if got else "empty"
                rec["count"] = len(got)
                log.info("%-5s %-22s %-45s -> %d items",
                         rec["status"].upper(), (operator or src.name)[:22],
                         src.url[:45], len(got))
            except Exception as exc:  # noqa: BLE001 - resilience by design
                rec["status"] = "fail"
                rec["count"] = 0
                rec["error"] = f"{type(exc).__name__}: {str(exc)[:140]}"
                log.warning("FAIL  %-22s %-45s -> %s",
                            (operator or src.name)[:22], src.url[:45],
                            rec["error"])
            results.append(rec)
    return items, results


# Single words that are too ambiguous in headlines to identify an operator
# on their own (multi-word terms containing them are still fine).
_AMBIGUOUS_TERMS = {
    "spark", "tim", "globe", "smart", "bell", "one", "free", "vi", "au",
}


def tag_news_regions(items: list[Item], operators: list[Operator]) -> None:
    """Assign industry-news items to a region if the headline names a
    watchlist operator. Word-boundary matching, longest term wins."""
    import re as _re

    terms: list[tuple[str, "_re.Pattern[str]", Operator]] = []
    for op in operators:
        for term in op.match_terms:
            t = term.lower().strip()
            if len(t) < 3:
                continue
            if " " not in t and t in _AMBIGUOUS_TERMS:
                continue
            pattern = _re.compile(r"(?<!\w)" + _re.escape(t) + r"(?!\w)")
            terms.append((t, pattern, op))
    terms.sort(key=lambda t: -len(t[0]))

    for item in items:
        if item.origin != "industry_news":
            continue
        hay = item.title.lower()
        for _t, pattern, op in terms:
            if pattern.search(hay):
                item.region = op.region_key
                item.operator = op.name
                break
