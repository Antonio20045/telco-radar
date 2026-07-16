"""Telco Radar pipeline: collect -> dedupe -> analyze -> report -> site.

Usage:
    python -m telco_radar.pipeline [--root .] [--no-llm] [--lookback-days N]
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

from .analyze import editor
from .analyze.agents import analyze_region
from .analyze.llm import llm_available
from .collect import collect_all, tag_news_regions
from .config import load_config
from .dedupe import ReportedTopics, SeenStore, filter_fresh
from .models import Item
from .report.html import render_site

log = logging.getLogger("telco_radar")

LANGUAGES = {"de": "Deutsch", "en": "English"}


def run(root: Path, use_llm: bool | None = None,
        lookback_days: int | None = None) -> Path:
    """Execute one full radar run. Returns the path of the written report."""
    cfg = load_config(root)
    lookback = lookback_days or cfg.lookback_days
    language = LANGUAGES.get(cfg.settings.get("report_language", "de"), "Deutsch")
    model = cfg.settings.get("model", "claude-sonnet-5")
    max_items = int(cfg.settings.get("max_items_per_region", 40))

    state_dir = root / "data" / "state"
    reports_dir = root / "data" / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------- collect
    items, failed = collect_all(cfg)
    tag_news_regions(items, cfg.operators)
    log.info("Collected %d items (%d sources failed)", len(items), len(failed))

    # -------------------------------------------------------------- dedupe
    seen = SeenStore(state_dir / "seen.jsonl")
    first_run = len(seen) == 0
    new_items = filter_fresh(seen.filter_new(items), lookback)
    log.info("Novelty filter: %d new items (seen store: %d known ids)",
             len(new_items), len(seen))

    items_by_region: dict[str, list[Item]] = defaultdict(list)
    for item in new_items:
        items_by_region[item.region].append(item)

    # ------------------------------------------------------------- analyze
    if use_llm is None:
        use_llm = llm_available()
    topics_store = ReportedTopics(
        state_dir / "reported_topics.jsonl",
        max_entries=int(cfg.settings.get("reported_topics_memory", 300)),
    )

    regional: dict[str, dict] = {}
    if use_llm and new_items:
        for region_key, region_items in items_by_region.items():
            region_name = cfg.region_names.get(region_key, region_key)
            try:
                regional[region_name] = analyze_region(
                    region_name, region_items, model=model,
                    language=language, max_items=max_items)
            except Exception as exc:  # noqa: BLE001
                log.error("Analyst %s failed: %s - falling back to raw list",
                          region_name, exc)
                regional[region_name] = {
                    "region_summary": "",
                    "highlights": [
                        {"title": i.title, "operator": i.operator or "",
                         "url": i.url, "category": "Sonstiges", "relevance": 2,
                         "summary": i.summary[:200], "why_it_matters": ""}
                        for i in region_items[:10]
                    ],
                }
        body, covered = editor.synthesize(
            regional, topics_store.recent(), model=model, language=language)
    else:
        if use_llm and not new_items:
            log.info("No new items - writing empty briefing")
        for region_key, region_items in items_by_region.items():
            region_name = cfg.region_names.get(region_key, region_key)
            regional[region_name] = {
                "region_summary": "",
                "highlights": [
                    {"title": i.title, "operator": i.operator or i.source_name,
                     "url": i.url, "category": "Unbewertet", "relevance": None,
                     "summary": i.summary[:220], "why_it_matters": ""}
                    for i in region_items[:max_items]
                ],
            }
        body, covered = editor.build_digest(items_by_region, cfg.region_names)
        if first_run:
            body = (
                "> **Erster Lauf (Baseline):** Alle Quellen wurden initial "
                "eingelesen. Ab dem nächsten Lauf erscheinen nur noch "
                "wirklich neue Meldungen.\n\n" + body
            )

    # enrich highlights with date + source from the collected items
    by_url = {i.url: i for i in new_items}
    for region in regional.values():
        for h in region.get("highlights", []):
            item = by_url.get(h.get("url", ""))
            if item is not None:
                h.setdefault("date", item.published.date().isoformat()
                             if item.published else None)
                h.setdefault("source", item.source_name)
            else:
                h.setdefault("date", None)
                h.setdefault("source", "")

    # -------------------------------------------------------------- report
    today = date.today()
    total_sources = sum(len(op.sources) for op in cfg.operators) + len(cfg.news_sources)
    stats = {
        "sources_total": total_sources,
        "sources_ok": total_sources - len(failed),
        "sources_failed": len(failed),
        "collected": len(items),
        "new": len(new_items),
        "operators": len(cfg.operators),
        "regions": len(cfg.region_names) - 1,
    }
    report_md = editor.report_header(today, stats) + body
    report_path = reports_dir / f"{today.isoformat()}.md"
    report_path.write_text(report_md, encoding="utf-8")

    report_json = {
        "date": today.isoformat(),
        "generated_with_llm": bool(use_llm and new_items),
        "stats": stats,
        "briefing_md": body,
        "regions": regional,
    }
    json_path = reports_dir / f"{today.isoformat()}.json"
    json_path.write_text(
        json.dumps(report_json, ensure_ascii=False, indent=1), encoding="utf-8")
    log.info("Report written: %s (+ .json)", report_path)

    # ------------------------------------------------------ persist state
    seen.add(new_items)
    if covered:
        topics_store.add(covered, today.isoformat())

    # ---------------------------------------------------------------- site
    render_site(root / "site", reports_dir, cfg)
    return report_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the Telco Radar pipeline")
    parser.add_argument("--root", type=Path, default=Path("."),
                        help="project root (contains config/, data/, site/)")
    parser.add_argument("--no-llm", action="store_true",
                        help="skip LLM analysis, produce raw digest")
    parser.add_argument("--lookback-days", type=int, default=None)
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        stream=sys.stdout,
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)

    try:
        run(args.root.resolve(),
            use_llm=False if args.no_llm else None,
            lookback_days=args.lookback_days)
    except Exception:  # noqa: BLE001
        log.exception("Pipeline failed")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
