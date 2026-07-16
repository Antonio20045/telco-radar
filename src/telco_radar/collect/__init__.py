"""Collectors: fetch items from RSS feeds and HTML newsroom pages."""
from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed

from ..config import Config, Source, Operator
from ..models import Item
from .rss import collect_rss
from .newsroom import collect_newsroom

log = logging.getLogger(__name__)


def _collect_source(source: Source, region: str, operator: str | None,
                    origin: str, http_cfg: dict) -> list[Item]:
    if source.type == "rss":
        return collect_rss(source, region, operator, origin, http_cfg)
    return collect_newsroom(source, region, operator, origin, http_cfg)


def collect_all(cfg: Config, max_workers: int = 8) -> tuple[list[Item], list[str]]:
    """Fetch every configured source concurrently.

    Returns (items, failed_source_urls). A failing source never aborts the run.
    """
    http_cfg = cfg.settings.get("http", {})
    jobs: list[tuple[Source, str, str | None, str]] = []

    for op in cfg.operators:
        for src in op.sources:
            jobs.append((src, op.region_key, op.name, "operator"))
    for src in cfg.news_sources:
        jobs.append((src, "global", None, "industry_news"))

    items: list[Item] = []
    failed: list[str] = []
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {
            pool.submit(_collect_source, src, region, operator, origin, http_cfg):
                (src, operator)
            for src, region, operator, origin in jobs
        }
        for fut in as_completed(futures):
            src, operator = futures[fut]
            try:
                got = fut.result()
                items.extend(got)
                log.info("OK  %-22s %-45s -> %d items",
                         (operator or src.name)[:22], src.url[:45], len(got))
            except Exception as exc:  # noqa: BLE001 - resilience by design
                failed.append(src.url)
                log.warning("FAIL %-22s %-45s -> %s: %s",
                            (operator or src.name)[:22], src.url[:45],
                            type(exc).__name__, str(exc)[:120])
    return items, failed


def tag_news_regions(items: list[Item], operators: list[Operator]) -> None:
    """Assign industry-news items to a region if the headline names a
    watchlist operator (longest alias wins)."""
    terms: list[tuple[str, Operator]] = []
    for op in operators:
        for term in op.match_terms:
            if len(term) >= 3:
                terms.append((term.lower(), op))
    terms.sort(key=lambda t: -len(t[0]))

    for item in items:
        if item.origin != "industry_news":
            continue
        hay = item.title.lower()
        for term, op in terms:
            if term in hay:
                item.region = op.region_key
                item.operator = op.name
                break
