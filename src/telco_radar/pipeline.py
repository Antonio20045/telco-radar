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
from itertools import zip_longest
from datetime import date, datetime, timezone
from pathlib import Path

from .analyze import editor
from .analyze.agents import analyze_region
from .analyze import competitors as competitor_mod
from .analyze import diff_curator
from .analyze import category_sweep
from .analyze import differentiation_editor
from .analyze.diff_curator import DiffStore
from .analyze import llm
from .analyze.llm import llm_available, active_backend
from .collect import collect_all, tag_news_regions
from .config import load_config
from .dedupe import ReportedTopics, SeenStore, filter_fresh
from .models import Item
from .report.html import render_site

log = logging.getLogger("telco_radar")

LANGUAGES = {"de": "Deutsch", "en": "English"}

# Anbieter, die das OpenAI-Chat-Protokoll sprechen, mit ihren
# Konfigurationsschluesseln: (Basis-URL, Analyst-Modell, Editor-Modell).
# Sie teilen sich EINEN Schluessel (LLM_API_KEY) - es kann also immer nur
# einer davon aktiv sein, was genau richtig ist: sonst muesste man im Secret
# raten, zu welchem Endpunkt der hinterlegte Schluessel gehoert.
OPENAI_KOMPATIBEL = {
    "openai": ("llm_api_base", "openai_analyst_model", "openai_editor_model"),
    "deepseek": ("deepseek_api_base", "deepseek_analyst_model",
                 "deepseek_editor_model"),
}

ANBIETER = ("auto", "anthropic", "bedrock", *OPENAI_KOMPATIBEL)


def _waehle_anbieter(settings: dict) -> str:
    """Legt den LLM-Anbieter fest und liefert seinen Namen.

    "auto" behaelt die alte Reihenfolge (Bedrock > OpenAI-kompatibel >
    Anthropic) und nimmt damit, welcher Schluessel gerade da ist. Genau das
    ist das Problem, das llm_provider loest: solange der NVIDIA-Schluessel im
    Repo liegt, gewinnt er, und Anthropic kaeme nie zum Zug.

    Bei einer expliziten Wahl werden die Schluessel der unterlegenen Anbieter
    aus der Prozessumgebung entfernt. Das ist noetig, weil llm.py seinen
    Backend allein aus der Umgebung ableitet - sonst wuerde hier der eine
    Anbieter die Modell-IDs bestimmen, waehrend dort der andere aufgerufen
    wird. Nur die Kopie dieses Prozesses ist betroffen.
    """
    wanted = str(settings.get("llm_provider", "auto") or "auto").lower()
    if wanted not in ANBIETER:
        log.warning("Unbekannter llm_provider %r - benutze auto", wanted)
        wanted = "auto"

    has_bedrock = bool(os.environ.get("AWS_BEARER_TOKEN_BEDROCK"))
    has_key = bool(os.environ.get("LLM_API_KEY"))

    if wanted == "auto":
        if has_bedrock:
            return "bedrock"
        return "openai" if (has_key and settings.get("llm_api_base")) else "anthropic"

    base_url = ""
    if wanted in OPENAI_KOMPATIBEL:
        base_url = str(settings.get(OPENAI_KOMPATIBEL[wanted][0]) or "")

    # Ein gewaehlter Anbieter ohne seinen Schluessel laesst jede Stufe
    # scheitern - das einmal deutlich sagen, statt es jeden Aufruf einzeln
    # herausfinden zu lassen.
    fehlt = ((wanted == "bedrock" and not has_bedrock)
             or (wanted in OPENAI_KOMPATIBEL and not (has_key and base_url))
             or (wanted == "anthropic" and not os.environ.get("ANTHROPIC_API_KEY")))
    if fehlt:
        log.warning("llm_provider=%s, aber Schluessel oder Basis-URL fehlen - "
                    "der Lauf faellt auf den Notfall-Digest zurueck", wanted)

    if wanted != "bedrock":
        os.environ.pop("AWS_BEARER_TOKEN_BEDROCK", None)
    if wanted not in OPENAI_KOMPATIBEL:
        os.environ.pop("LLM_API_KEY", None)
    elif base_url:
        # Muss HIER passieren, nicht erst beim Setzen der Modell-IDs: llm.py
        # erkennt den OpenAI-Zweig nur an LLM_API_KEY *und* LLM_API_BASE.
        # Fehlt die Basis-URL, waehlt es still einen anderen Anbieter - die
        # Wahl waere getroffen und nicht umgesetzt. Kein setdefault: beim
        # Wechsel von NVIDIA auf DeepSeek stuende sonst eine von aussen
        # gesetzte alte URL gegen den konfigurierten Anbieter.
        os.environ["LLM_API_BASE"] = base_url
    if wanted != "anthropic":
        # Auch den Anthropic-Schluessel entfernen. llm.py behandelt ihn sonst
        # als letzte Rueckfallebene: bei einem Tippfehler in der DeepSeek-URL
        # liefe der ganze Lauf still ueber Anthropic - also genau ueber den
        # teuren Anbieter, von dem hier gerade weggeschaltet wurde. Die
        # Warnung oben verspricht den Notfall-Digest; das hier haelt sie ein.
        os.environ.pop("ANTHROPIC_API_KEY", None)
    return wanted


def _sort_key(item: Item):
    """Freshest first; undated items last."""
    pub = item.published
    if pub is None:
        return (0, "")
    return (1, pub.isoformat())


def _interleave_by_source(items: list[Item]) -> list[Item]:
    """Order a region's items so every operator gets a slot before any
    operator gets a second one.

    The analyst reads at most `max_items_per_region` items, so the order here
    decides what is even looked at. Straight recency ordering let one
    high-volume feed take the whole budget: in the 2026-07-31 run 220 new
    items produced only 70 analysed ones, and the operator newsrooms - the
    entire point of the watchlist - lost every slot to the trade press.
    Round-robin over the sources keeps the breadth; within a source the
    freshest item still comes first.
    """
    buckets: dict[str, list[Item]] = defaultdict(list)
    for item in sorted(items, key=_sort_key, reverse=True):
        buckets[item.operator or item.source_name].append(item)
    # Operators with a dated newest item go first, so a source that publishes
    # undated pages cannot outrank one with a verifiable fresh release.
    order = sorted(buckets.values(), key=lambda b: _sort_key(b[0]), reverse=True)
    out: list[Item] = []
    for round_items in zip_longest(*order):
        out.extend(i for i in round_items if i is not None)
    return out


def run(root: Path, use_llm: bool | None = None,
        lookback_days: int | None = None) -> Path:
    """Execute one full radar run. Returns the path of the written report."""
    t0 = time.monotonic()
    started_at = datetime.now(timezone.utc)
    cfg = load_config(root)
    lookback = lookback_days or cfg.lookback_days
    language = LANGUAGES.get(cfg.settings.get("report_language", "de"), "Deutsch")
    fallback_model = cfg.settings.get("model", "claude-sonnet-5")
    anbieter = _waehle_anbieter(cfg.settings)
    use_bedrock = anbieter == "bedrock"
    use_openai = anbieter in OPENAI_KOMPATIBEL
    if use_bedrock:
        # Which Claude models a Bedrock account may call is per-account and
        # changes without notice (agreements, quotas, AWS Sales). Instead of
        # pinning one id, register the configured preference chain and let the
        # run settle on the best model that actually answers.
        chain_head = llm.set_model_chain(cfg.settings.get("bedrock_model_chain") or [])
        analyst_model = (cfg.settings.get("bedrock_analyst_model")
                         or chain_head or fallback_model)
        editor_model = (cfg.settings.get("bedrock_editor_model")
                        or chain_head or fallback_model)
    elif use_openai:
        # Die Basis-URL hat _waehle_anbieter bereits gesetzt; hier nur noch
        # die Modelle des gewaehlten Endpunkts.
        _, analyst_key, editor_key = OPENAI_KOMPATIBEL[anbieter]
        analyst_model = cfg.settings.get(analyst_key) or fallback_model
        editor_model = cfg.settings.get(editor_key) or fallback_model
    else:
        analyst_model = cfg.settings.get("analyst_model", fallback_model)
        editor_model = cfg.settings.get("editor_model", fallback_model)
    # The editor model is the big one and the first to lose its slot when the
    # provider is oversubscribed: the connection is accepted and no token ever
    # arrives. Four stages run on it, so without a stand-in one provider outage
    # burns 4x the retry budget and the job timeout kills the run before it can
    # publish anything. Register the (smaller, still-served) analyst model as
    # the stand-in - used only after the editor model has failed hard once.
    if cfg.settings.get("editor_model_fallback", True) and analyst_model:
        llm.set_fallback(editor_model, analyst_model)
    log.info("LLM backend: %s | analyst=%s editor=%s (Ausweichmodell: %s)",
             active_backend(), analyst_model, editor_model,
             analyst_model if analyst_model != editor_model else "keins")
    # 0 (oder fehlend) heisst: keine Kappung - jede neue Meldung wird bewertet.
    max_items = int(cfg.settings.get("max_items_per_region", 0) or 0) or None

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
    for region_key, region_items in items_by_region.items():
        items_by_region[region_key] = _interleave_by_source(region_items)

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
    # Regionen, deren Analyse vollstaendig ausgefallen ist. Ihre Meldungen
    # duerfen NICHT in den Seen-Store: dort gelten sie sonst als erledigt und
    # tauchen nie wieder auf, obwohl sie kein Analyst je gelesen hat.
    unanalysierte_regionen: set[str] = set()
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
                if tel.get("batches") and not tel.get("batches_ok"):
                    # Jeder Stapel gescheitert - die Meldungen sind ungelesen.
                    unanalysierte_regionen.add(region_key)
                return region_name, res, tel
            except Exception as exc:  # noqa: BLE001
                log.error("Analyst %s failed: %s - falling back to raw list",
                          region_name, exc)
                unanalysierte_regionen.add(region_key)
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
                language=language,
                highlight_budget=int(
                    cfg.settings.get("editor_max_highlights", 0) or 0))
            editor_used = True
        except Exception as exc:  # noqa: BLE001
            if cfg.settings.get("publish_requires_editorial_briefing", True):
                raise RuntimeError(
                    "Editorial synthesis failed; refusing to publish a raw "
                    "source digest. The previous briefing remains live."
                ) from exc
            log.warning(
                "Editorial synthesis failed (%s); publishing a labelled "
                "source-linked fallback digest", str(exc)[:180])
            fallback, covered = editor.build_digest(
                items_by_region, cfg.region_names, llm_was_available=False,
                include_note=False)  # the Redaktions-Fallback note below says it
            body = (
                "## Redaktions-Fallback\n\n"
                "> Die aktuelle Quellenliste konnte wegen einer vorübergehenden "
                "Störung des Analyse-Dienstes nicht redaktionell verdichtet "
                "werden. Die Links und Meldungen stammen trotzdem aus diesem "
                "Lauf; die automatische Redaktion wird im nächsten Lauf erneut "
                "versucht.\n\n" + fallback
            )
            editor_used = False
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
                    for i in (region_items if not max_items
                              else region_items[:max_items])
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

    # ------------------------------------- Dynamischer Kategorie-Sweep (Web)
    # Zweite Datenquelle fuer die Differenzierungs-Seite: durchsucht je Lauf
    # rotierend aktiv das Web (Brave Search) nach echten Differenzierungs-Moves
    # der Wettbewerber und pflegt sie mit Quelle + Datum in die versionierte DB
    # (data/state/differentiation_db.json). Failsafe: bricht nie ab.
    try:
        category_sweep.run_sweep(
            state_dir, os.environ.get("BRAVE_API_KEY", ""),
            editor_model, bool(use_llm), date.today().isocalendar()[1])
    except Exception as exc:  # noqa: BLE001
        log.error("Kategorie-Sweep uebersprungen: %s", exc)

    # ---------------------------------------------- Promo-Uebersicht (DE)
    # Eigener zweiter Anwendungsfall neben Marktrecherche: Tarif-/Kampagnen-
    # aktionen aller Telcos in Deutschland, per Snapshot-Diff der jeweils
    # eigenen Aktionsseite gesammelt statt per Presse-RSS (siehe
    # promo_pipeline.py + config/promo_sources.yaml). Failsafe: bricht den
    # Gesamtlauf nie ab; per settings.yaml (promo_enabled) abschaltbar.
    promo_result: dict = {}
    if cfg.settings.get("promo_enabled", True):
        try:
            from .promo_pipeline import run_promo_stage
            promo_result = run_promo_stage(
                root, cfg.settings.get("http", {}), bool(use_llm),
                editor_model, language=language, settings=cfg.settings,
                score_model=analyst_model or editor_model)
            log.info("Promo-Uebersicht: %s (%d aktive Aktionen)",
                     promo_result.get("mode"), promo_result.get("active", 0))
        except Exception as exc:  # noqa: BLE001
            log.error("Promo-Uebersicht uebersprungen: %s", exc)

    # ----------------------------------------- Differenzierungsbericht-Agent
    # Der Bericht arbeitet auf der aktualisierten, versionierten DB. Er ist
    # deshalb ein eigener Editorial-Schritt und nicht nur eine Umformatierung
    # der darunterstehenden Move-Liste. Ohne LLM bleibt die Seite mit einem
    # quellengebundenen Regelbericht nutzbar.
    today = date.today()
    diff_report_dir = reports_dir / "differenzierung"
    diff_report_dir.mkdir(parents=True, exist_ok=True)
    diff_db = category_sweep.DiffDB(state_dir / "differentiation_db.json")
    diff_entries = list(diff_db.entries.values())
    theme_labels = category_sweep.THEME_LABEL
    try:
        if use_llm and diff_entries:
            diff_body = differentiation_editor.synthesize(
                diff_entries, theme_labels, model=editor_model, language=language)
            diff_mode = "KI-Redaktion"
        else:
            diff_body = differentiation_editor.build_digest(diff_entries, theme_labels)
            diff_mode = "Regelbericht"
    except Exception as exc:  # noqa: BLE001
        log.warning("Differenzierungsbericht-Agent fehlgeschlagen (%s) – "
                    "verwende Regelbericht", str(exc)[:160])
        diff_body = differentiation_editor.build_digest(diff_entries, theme_labels)
        diff_mode = "Regelbericht (Fallback)"
    diff_report_path = diff_report_dir / f"{today.isoformat()}.md"
    diff_report_path.write_text(diff_body, encoding="utf-8")
    log.info("Differenzierungsbericht: %s (%d Moves)", diff_mode, len(diff_entries))

    # -------------------------------------------------------------- report
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
            # Models the provider stopped serving mid-run. Visible in
            # protokoll.html so a degraded run is recognisable as such instead
            # of looking like a thin news week.
            "unavailable": sorted(llm.dead_models()) or None,
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
    # Der Seen-Store ist ein Einbahnschild: was hier hineingeht, gilt als
    # erledigt und wird nie wieder gesammelt. Meldungen einer Region, deren
    # Analyse komplett gescheitert ist, gehoeren deshalb NICHT hinein - sie
    # waeren sonst still verloren. Lauf #64 (04.08.2026) hat genau das getan:
    # das Anthropic-Guthaben war leer, jeder Analysten-Stapel scheiterte mit
    # HTTP 400, und trotzdem wanderten 223 ungelesene Meldungen in den Store.
    # Beim naechsten Lauf mit Guthaben waeren sie nicht mehr aufgetaucht.
    zu_merken = [i for i in new_items if i.region not in unanalysierte_regionen]
    uebersprungen = len(new_items) - len(zu_merken)
    if uebersprungen:
        log.warning("%d Meldungen aus %d Region(en) ohne Analyse NICHT als "
                    "gesehen markiert - der naechste Lauf holt sie erneut",
                    uebersprungen, len(unanalysierte_regionen))
    seen.add(zu_merken)
    # Dieselbe Logik fuer das Themengedaechtnis: Themen aus einem Notfall-
    # Digest als "schon berichtet" abzulegen wuerde die Redaktion daran
    # hindern, sie spaeter richtig zu behandeln.
    if covered and editor_used:
        topics_store.add(covered, today.isoformat())
    elif covered:
        log.warning("%d Themen stammen aus dem Notfall-Digest, nicht aus der "
                    "Redaktion - sie werden NICHT als berichtet gemerkt",
                    len(covered))

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
