"""Telco Radar pipeline: collect -> dedupe -> analyze -> report -> site.

Usage:
    python -m telco_radar.pipeline [--root .] [--no-llm] [--lookback-days N]
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timezone
from pathlib import Path

from .analyze import editor
from .analyze.agents import analyze_region
from .analyze import competitors as competitor_mod
from .analyze import diff_curator
from .analyze import idea_radar
from .analyze.diff_curator import DiffStore
from .analyze.llm import llm_available, active_backend
from .collect import collect_all, tag_news_regions
from .config import load_config
from .dedupe import ReportedTopics, SeenStore, filter_fresh
from .models import Item
from .report.html import render_site

log = logging.getLogger("telco_radar")

LANGUAGES = {"de": "Deutsch", "en": "English"}


def _sort_key(item: Item):
    """Freshest first; undated items last."""
    pub = item.published
    if pub is None:
        return (0, "")
    return (1, pub.isoformat())


def run(root: Path, use_llm: bool | None = None,
        lookback_days: int | None = None) -> Path:
    """Execute one full radar run. Returns the path of the written report."""
    t0 = time.monotonic()
    started_at = datetime.now(timezone.utc)
    cfg = load_config(root)
    lookback = lookback_days or cfg.lookback_days
    language = LANGUAGES.get(cfg.settings.get("report_language", "de"), "Deutsch")
    fallback_model = cfg.settings.get("model", "claude-sonnet-5")
    # Provider selection: if an OpenAI-compatible key is present, use that
    # provider (cheap, e.g. Moonshot/Kimi); otherwise fall back to Anthropic.
    use_openai = bool(os.environ.get("LLM_API_KEY")) and bool(cfg.settings.get("llm_api_base"))
    if use_openai:
        os.environ.setdefault("LLM_API_BASE", cfg.settings["llm_api_base"])
        analyst_model = cfg.settings.get("openai_analyst_model", fallback_model)
        editor_model = cfg.settings.get("openai_editor_model", fallback_model)
    else:
        analyst_model = cfg.settings.get("analyst_model", fallback_model)
        editor_model = cfg.settings.get("editor_model", fallback_model)
    log.info("LLM backend: %s | analyst=%s editor=%s",
             active_backend(), analyst_model, editor_model)
    max_items = int(cfg.settings.get("max_items_per_region", 45))

    state_dir = root / "data" / "state"
    reports_dir = root / "data" / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)

    phases: list[dict] = []

    def phase(name: str, seconds: float, detail: str = "") -> None:
        phases.append({"name": name, "seconds": round(seconds, 1), "detail": detail})

    # ------------------------------------------------------------- collect
    tc = time.monotonic()
    items, source_results = collect_all(cfg)
    tag_news_regions(items, cfg.operators)
    failed = [r["url"] for r in source_results if r["status"] == "fail"]
    n_ok = sum(1 for r in source_results if r["status"] == "ok")
    n_empty = sum(1 for r in source_results if r["status"] == "empty")
    n_fail = len(failed)
    phase("Sammeln", time.monotonic() - tc,
          f"{len(source_results)} Quellen abgefragt, {len(items)} Meldungen gefunden")
    log.info("Collected %d items (%d ok / %d leer / %d fehlgeschlagen)",
             len(items), n_ok, n_empty, n_fail)

    # -------------------------------------------------------------- dedupe
    td = time.monotonic()
    seen = SeenStore(state_dir / "seen.jsonl")
    first_run = len(seen) == 0
    new_items = filter_fresh(seen.filter_new(items), lookback)
    phase("Nur Neues", time.monotonic() - td,
          f"{len(new_items)} neue Meldungen (Gedaechtnis: {len(seen)} bekannt)")
    log.info("Novelty filter: %d new items (seen store: %d known ids)",
             len(new_items), len(seen))

    items_by_region: dict[str, list[Item]] = defaultdict(list)
    for item in sorted(new_items, key=_sort_key, reverse=True):
        items_by_region[item.region].append(item)

    # ------------------------------------------------------------- analyze
    llm_was_explicitly_disabled = use_llm is False
    if use_llm is None:
        use_llm = llm_available()
    topics_store = ReportedTopics(
        state_dir / "reported_topics.jsonl",
        max_entries=int(cfg.settings.get("reported_topics_memory", 300)),
    )

    ta = time.monotonic()
    regional: dict[str, dict] = {}
    analyst_telemetry: list[dict] = []
    editor_used = False
    if use_llm and new_items:
        # Analysts are independent per region -> run them concurrently. Only
        # ~6 calls, well under any rate cap, but overlapping their latency
        # turns a ~9x sequential wait into ~1-2x. Same models, same output.
        llm_workers = int(cfg.settings.get("llm_max_workers", 4))

        def _analyze_one(region_key, region_items):
            region_name = cfg.region_names.get(region_key, region_key)
            try:
                res = analyze_region(
                    region_name, region_items, model=analyst_model,
                    language=language, max_items=max_items)
                tel = dict(res.get("_telemetry", {}))
                tel["region"] = region_name
                return region_name, res, tel
            except Exception as exc:  # noqa: BLE001
                log.error("Analyst %s failed: %s - falling back to raw list",
                          region_name, exc)
                fallback = {
                    "region_summary": "",
                    "highlights": [
                        {"title": i.title, "operator": i.operator or "",
                         "url": i.url, "category": "Sonstiges", "relevance": 2,
                         "summary": i.summary[:200], "why_it_matters": ""}
                        for i in region_items[:10]
                    ],
                }
                return region_name, fallback, None

        with ThreadPoolExecutor(max_workers=max(1, llm_workers)) as _pool:
            _futs = [_pool.submit(_analyze_one, rk, ri)
                     for rk, ri in items_by_region.items()]
            for _fut in as_completed(_futs):
                region_name, res, tel = _fut.result()
                regional[region_name] = res
                if tel is not None:
                    analyst_telemetry.append(tel)
        try:
            body, covered = editor.synthesize(
                regional, topics_store.recent(), model=editor_model,
                language=language)
            editor_used = True
        except Exception as exc:  # noqa: BLE001
            # The weekly public site is an editorial product. Publishing a raw
            # source list after an editor/provider failure is worse than
            # retaining last week's verified briefing, so stop before any
            # report, state or site artefact is written.
            raise RuntimeError(
                "Editorial synthesis failed; refusing to publish a raw "
                "source digest. The previous briefing remains live."
            ) from exc
    else:
        if (new_items and not llm_was_explicitly_disabled
                and cfg.settings.get("publish_requires_editorial_briefing", True)):
            raise RuntimeError(
                "No editorial model is available; refusing to publish a raw "
                "source digest. The previous briefing remains live."
            )
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
        body, covered = editor.build_digest(
            items_by_region, cfg.region_names, llm_was_available=bool(use_llm))
        if first_run:
            body = (
                "> **Erster Lauf (Baseline):** Alle Quellen wurden initial "
                "eingelesen. Ab dem naechsten Lauf erscheinen nur noch "
                "wirklich neue Meldungen.\n\n" + body
            )
    phase("Bewerten & Schreiben", time.monotonic() - ta,
          f"{sum(len(r.get('highlights') or []) for r in regional.values())} "
          f"bewertete Meldungen" if use_llm else "ohne KI (Roh-Digest)")

    # strip internal telemetry from the regional dict before it is stored
    for r in regional.values():
        r.pop("_telemetry", None)

    # ------------------------------------------------ competitor deep-dives
    competitor_profiles: list[dict] = []
    if use_llm and cfg.focus_competitors:
        tcomp = time.monotonic()
        try:
            comp_model = cfg.settings.get("openai_analyst_model", editor_model) if use_openai else editor_model
            competitor_profiles = competitor_mod.analyze_all(
                cfg.focus_competitors, items, comp_model, language,
                max_workers=int(cfg.settings.get('llm_max_workers', 4)))
        except Exception as exc:  # noqa: BLE001
            log.error("Competitor deep-dive failed: %s", exc)
        phase("Wettbewerber-Analyse", time.monotonic() - tcomp,
              f"{len(competitor_profiles)} Profile "
              f"({sum(len(c.get('moves') or []) for c in competitor_profiles)} Moves)")

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

    # -------------------------------------------- Differenzierungs-Kurator
    # Nimmt aufnahmewuerdige Differenzierungs-Moves dieser Woche in den
    # persistenten Speicher auf (data/state/differentiation.jsonl), damit sie
    # auch spaeter noch als Inspiration sichtbar bleiben. Failsafe: Fehler
    # brechen den Lauf nicht ab.
    try:
        flat_new = []
        for region_name, r in regional.items():
            for h in r.get("highlights", []):
                hh = dict(h)
                hh["region"] = region_name
                flat_new.append(hh)
        diff_store = DiffStore(state_dir / "differentiation.jsonl")
        added = diff_curator.curate(
            flat_new, diff_store, date.today().isoformat(),
            model=editor_model, use_llm=bool(use_llm and new_items))
        log.info("Differenzierung: %d neue Move(s) aufgenommen (Speicher: %d)",
                 len(added), len(diff_store))
    except Exception as exc:  # noqa: BLE001
        log.error("Differenzierungs-Kurator uebersprungen: %s", exc)

    # ------------------------------------------------- Ideen-Radar (Agent)
    # Schreibt pro Differenzierungs-Hebel eine kompakte "Vorbild -> Idee"-Zeile
    # aus der aktuellen Marktlage. Failsafe: Seed-Fallback, bricht nie ab.
    try:
        digest = "; ".join(
            f"{(i.operator or i.source_name)}: {i.title}"
            for i in new_items[:80] if i.title)
        idea_radar.refresh(
            state_dir / "idea_radar.json", digest,
            model=editor_model, use_llm=bool(use_llm and new_items))
    except Exception as exc:  # noqa: BLE001
        log.error("Ideen-Radar uebersprungen: %s", exc)

    # -------------------------------------------------------------- report
    today = date.today()
    total_sources = sum(len(op.crawled_sources) for op in cfg.operators) \
        + len(cfg.news_sources)
    stats = {
        "sources_total": total_sources,
        "sources_ok": n_ok,
        "sources_empty": n_empty,
        "sources_failed": n_fail,
        "collected": len(items),
        "new": len(new_items),
        "operators": len(cfg.operators),
        "regions": len(cfg.region_names) - 1,
    }

    # ------------------------------------------------------- run log (transparency)
    duration = time.monotonic() - t0
    kind_counts: dict[str, int] = defaultdict(int)
    for r in source_results:
        kind_counts[r["kind"]] += 1
    run_log = {
        "started_at": started_at.isoformat(),
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "duration_seconds": round(duration, 1),
        "used_llm": bool(use_llm and new_items),
        "editor_used": editor_used,
        "models": {
            "analyst": analyst_model if (use_llm and new_items) else None,
            "editor": editor_model if editor_used else None,
        },
        "phases": phases,
        "source_summary": {
            "total": len(source_results),
            "ok": n_ok, "empty": n_empty, "failed": n_fail,
            "by_kind": dict(kind_counts),
        },
        "sources": sorted(
            source_results,
            key=lambda r: ({"fail": 0, "ok": 1, "empty": 2}.get(r["status"], 3),
                           -r.get("count", 0))),
        "analysts": analyst_telemetry,
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
        "competitors": competitor_profiles,
        "run": run_log,
    }
    json_path = reports_dir / f"{today.isoformat()}.json"
    json_path.write_text(
        json.dumps(report_json, ensure_ascii=False, indent=1), encoding="utf-8")
    log.info("Report written: %s (+ .json), run took %.1fs", report_path, duration)

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
