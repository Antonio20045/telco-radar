"""Collectors: fetch items from RSS feeds and HTML newsroom pages."""
from __future__ import annotations

import logging
import time
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


def collect_all(cfg: Config, max_workers: int = 5) -> tuple[list[Item], list[dict]]:
    """Fetch every configured (crawlable) source concurrently.

    Returns (items, source_results). Each source_result is a dict describing
    what happened with that source (status/count/error) so the pipeline can
    build a transparent run log. A failing source never aborts the run.
    """
    http_cfg = cfg.settings.get("http", {})
    jobs: list[tuple[Source, str, str | None, str]] = []

    for op in cfg.operators:
        for src in op.crawled_sources:
            jobs.append((src, op.region_key, op.name, "operator"))
    for src in cfg.news_sources:
        jobs.append((src, "global", None, "industry_news"))

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
