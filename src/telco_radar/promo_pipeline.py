"""Promo-Uebersicht Pipeline-Stufe: Snapshot-Diff -> LLM-Extraktion -> DB ->
Bericht.

Ein eigener, in sich geschlossener Zweig neben dem Haupt-Collect/Analyze-
Ablauf in pipeline.py: andere Quellenart (Endkunden-Aktionsseiten statt
Presse-Newsrooms), anderer Collector (Snapshot-Diff statt RSS/Newsroom),
eigener persistenter State (data/state/promo_snapshots.json,
data/state/promo_db.json). Failsafe wie die Differenzierungs-Zweige: ein
Fehler hier bricht den Gesamtlauf nie ab (siehe pipeline.py, wo dieser Aufruf
in try/except steht).
"""
from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
from pathlib import Path

from .analyze import promo_editor
from .analyze.promo_analyst import extract_promos
from .analyze.promo_store import PromoDB, SnapshotStore, entry_id
from .collect.promo_snapshot import content_hash, fetch_snapshot
from .promo_config import load_promo_config

log = logging.getLogger(__name__)


def _fetch_one(src, http_cfg: dict) -> dict:
    """Runs in a worker thread: fetch + hash only, no shared state touched -
    keeps this safe to parallelise like collect/__init__.py's collect_all."""
    rec = {"brand": src.name, "url": src.url, "tier": src.tier, "kind": src.kind}
    try:
        text = fetch_snapshot(src.url, src.kind, http_cfg)
        rec["text"] = text
        rec["hash"] = content_hash(text)
    except Exception as exc:  # noqa: BLE001
        rec["status"] = "fail"
        rec["error"] = f"{type(exc).__name__}: {str(exc)[:140]}"
    return rec


def run_promo_stage(root: Path, http_cfg: dict, use_llm: bool, model: str,
                    language: str = "Deutsch", max_workers: int = 4) -> dict:
    """Fuehrt den Promo-Uebersicht-Zweig aus. Gibt einen Status-Dict fuer das
    Protokoll zurueck. Wirft nur bei fatalen Konfigurationsfehlern - einzelne
    Quellenfehler werden pro Quelle abgefangen und geloggt.

    Der Seitenabruf laeuft nebenlaeufig (I/O-lastig, ~17 Quellen, mehrere
    davon per Playwright) - gleiches Muster wie collect_all(). Diff-Check,
    LLM-Extraktion und DB-Update laufen danach sequentiell, weil sie den
    gemeinsamen State (SnapshotStore/PromoDB) mutieren."""
    today = date.today().isoformat()
    state_dir = root / "data" / "state"
    reports_dir = root / "data" / "reports" / "promo"
    reports_dir.mkdir(parents=True, exist_ok=True)

    promo_cfg = load_promo_config(root)
    snap_store = SnapshotStore(state_dir / "promo_snapshots.json")
    db = PromoDB(state_dir / "promo_db.json")

    sources = promo_cfg.crawled_sources
    fetched: list[dict] = []
    with ThreadPoolExecutor(max_workers=max(1, max_workers)) as pool:
        futures = {pool.submit(_fetch_one, src, http_cfg): src for src in sources}
        for fut in as_completed(futures):
            fetched.append(fut.result())
    fetched.sort(key=lambda r: r["brand"])  # deterministisches Protokoll

    results: list[dict] = []
    for rec in fetched:
        if rec.get("status") == "fail":
            log.warning("Promo-Snapshot fehlgeschlagen (%s): %s",
                       rec["brand"], rec.get("error"))
            results.append(rec)
            continue
        src_name, text, h = rec["brand"], rec.pop("text"), rec.pop("hash")
        try:
            if not snap_store.changed(src_name, h):
                rec["status"] = "unveraendert"
                results.append(rec)
                continue
            snap_store.update(src_name, h, today)
            if use_llm and text.strip():
                items = extract_promos(src_name, text, model)
                for it in items:
                    it["tier"] = rec["tier"]
                    it["url"] = rec["url"]
                n_new = db.upsert(items, today)
                checked_ids = {entry_id(src_name, it["headline"]) for it in items}
                db.mark_stale(src_name, checked_ids, today)
                rec["status"] = "ok"
                rec["new_items"] = n_new
                rec["extracted"] = len(items)
            else:
                rec["status"] = "changed_no_llm"
        except Exception as exc:  # noqa: BLE001
            rec["status"] = "fail"
            rec["error"] = f"{type(exc).__name__}: {str(exc)[:140]}"
            log.warning("Promo-Verarbeitung fehlgeschlagen (%s): %s",
                       src_name, rec["error"])
        results.append(rec)

    snap_store.save()
    db.save(today)

    entries = list(db.entries.values())
    try:
        if use_llm and entries:
            body = promo_editor.synthesize(entries, model=model, language=language)
            mode = "KI-Redaktion"
        else:
            body = promo_editor.build_digest(entries)
            mode = "Regelbericht"
    except Exception as exc:  # noqa: BLE001
        log.warning("Promo-Redaktion fehlgeschlagen (%s) - verwende Regelbericht",
                   str(exc)[:160])
        body = promo_editor.build_digest(entries)
        mode = "Regelbericht (Fallback)"

    (reports_dir / f"{today}.md").write_text(body, encoding="utf-8")
    active = sum(1 for e in entries if e.get("status") == "aktiv")
    log.info("Promo-Uebersicht: %s (%d aktive Aktionen, %d Quellen konfiguriert)",
             mode, active, len(promo_cfg.sources))
    return {"mode": mode, "sources": results, "db_size": len(db), "active": active}
