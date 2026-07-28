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

from .analyze import promo_editor, promo_ranker
from .analyze.promo_analyst import extract_promos
from .analyze.promo_store import PromoDB, SnapshotStore
from .collect.promo_snapshot import capture_hero_image, content_hash, fetch_snapshot
from .promo_config import load_promo_config
from .promo_images import image_path

log = logging.getLogger(__name__)

# Screenshot capture launches a full Chromium instance per brand and is
# noticeably heavier than the text-only fetch above (real images/fonts/CSS
# loaded) - a lower, separate concurrency cap keeps peak memory bounded on
# the Actions runner regardless of what max_workers the text-fetch pass uses.
_IMAGE_WORKERS = 3


def _fetch_one(src, http_cfg: dict) -> dict:
    """Runs in a worker thread: fetch + hash only, no shared state touched -
    keeps this safe to parallelise like collect/__init__.py's collect_all."""
    rec = {"brand": src.name, "url": src.url, "tier": src.tier, "kind": src.kind}
    try:
        snap = fetch_snapshot(src.url, src.kind, http_cfg)
        rec["text"] = snap["text"]
        rec["links"] = snap.get("links") or []
        rec["hash"] = content_hash(snap["text"], rec["links"])
        rec["image_url"] = snap.get("image_url")
    except Exception as exc:  # noqa: BLE001
        rec["status"] = "fail"
        rec["error"] = f"{type(exc).__name__}: {str(exc)[:140]}"
    return rec


def _resolve_item_url(item_url: str | None, brand_url: str) -> str:
    """The LLM-selected deep link if extract_promos() found one, else the
    brand's configured overview URL - exactly the pre-deep-links behaviour
    in the fallback case, never worse (see
    claude/promo-tiefenlinks-konzept.md Anforderung 2)."""
    return (item_url or "").strip() or brand_url


def run_promo_stage(root: Path, http_cfg: dict, use_llm: bool, model: str,
                    language: str = "Deutsch", max_workers: int = 4,
                    settings: dict | None = None,
                    score_model: str | None = None) -> dict:
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

    # Brands whose hero screenshot should be (re-)captured this run: either
    # the page actually changed (the screenshot is likely stale too), or no
    # cached screenshot exists yet at all (first rollout / a past capture
    # failure). A page that failed to fetch is skipped here too - if plain
    # HTTP/JS-render couldn't reach it, a fresh screenshot attempt this same
    # run is unlikely to fare better and would just spend time other brands
    # could use; it gets picked up automatically once the source recovers.
    image_candidates: list[tuple[str, str]] = []

    results: list[dict] = []
    for rec in fetched:
        if rec.get("status") == "fail":
            log.warning("Promo-Snapshot fehlgeschlagen (%s): %s",
                       rec["brand"], rec.get("error"))
            results.append(rec)
            continue
        src_name, text, h = rec["brand"], rec.pop("text"), rec.pop("hash")
        links = rec.pop("links", [])
        image_url = rec.get("image_url")
        changed = snap_store.changed(src_name, h)
        if changed or not image_path(root, src_name).exists():
            image_candidates.append((src_name, rec["url"]))
        try:
            if not changed:
                rec["status"] = "unveraendert"
                results.append(rec)
                continue
            snap_store.update(src_name, h, today)
            if use_llm and text.strip():
                items = extract_promos(src_name, text, model, links=links)
                for it in items:
                    it["tier"] = rec["tier"]
                    it["url"] = _resolve_item_url(it.get("url"), rec["url"])
                    it["image_url"] = image_url
                n_new, matched_ids = db.upsert(items, today)
                db.mark_stale(src_name, matched_ids, today)
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

    # Wichtigkeits-Score: laeuft ueber ALLE nicht-ausgelaufenen Eintraege der
    # DB, nicht nur ueber die dieses Mal neu extrahierten - ein Angebot, das
    # seit drei Wochen unveraendert laeuft, ist deshalb ja nicht unwichtig.
    # Die teuren LLM-Achsen werden trotzdem nur einmal je Angebotstext
    # angefragt und danach eingefroren (siehe promo_ranker.needs_judgement),
    # der Dauerbetrieb kostet also nur die paar wirklich neuen Angebote.
    # Failsafe wie ueberall hier: ein Fehler laesst die Scores unveraendert,
    # bricht aber weder diesen Zweig noch den Gesamtlauf ab.
    score_summary: dict = {}
    try:
        score_summary = promo_ranker.score_all(
            list(db.entries.values()), promo_cfg.sources, today,
            model=score_model or model, use_llm=use_llm, settings=settings,
            max_workers=max_workers)
        log.info("Promo-Bewertung: %d Angebote bewertet, %d neu beurteilt, "
                 "%d ohne Urteil, %d Highlights (Schwelle %d/%d)",
                 score_summary.get("scored", 0), score_summary.get("judged_new", 0),
                 score_summary.get("judged_failed", 0),
                 score_summary.get("highlights", 0),
                 score_summary.get("enter", 0), score_summary.get("exit", 0))
    except Exception as exc:  # noqa: BLE001
        log.warning("Promo-Bewertung uebersprungen: %s", str(exc)[:160])

    db.save(today)

    # Hero screenshots: a second, independent pass after the text/LLM work
    # above (own Chromium launches, own lower concurrency cap - see
    # _IMAGE_WORKERS) so a slow or failing screenshot can never affect the
    # text/diff/LLM path this run's core value depends on. Failure per brand
    # is caught individually; the card simply keeps last run's image (or the
    # colour+initials fallback if there never was one) - never fatal.
    images_captured = images_failed = 0
    if image_candidates:
        image_dir = state_dir / "promo_images"
        image_dir.mkdir(parents=True, exist_ok=True)

        def _capture_one(brand: str, url: str) -> bool:
            data = capture_hero_image(url, http_cfg)
            if not data:
                return False
            try:
                image_path(root, brand).write_bytes(data)
                return True
            except OSError as exc:
                log.warning("Promo-Hero-Bild konnte nicht gespeichert werden (%s): %s",
                           brand, exc)
                return False

        with ThreadPoolExecutor(max_workers=_IMAGE_WORKERS) as pool:
            futures = {pool.submit(_capture_one, brand, url): brand
                      for brand, url in image_candidates}
            for fut in as_completed(futures):
                if fut.result():
                    images_captured += 1
                else:
                    images_failed += 1
        log.info("Promo-Hero-Bilder: %d von %d Kandidaten erfasst (%d fehlgeschlagen)",
                 images_captured, len(image_candidates), images_failed)

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
    return {"mode": mode, "sources": results, "db_size": len(db), "active": active,
            "images_captured": images_captured, "images_failed": images_failed,
            "score": score_summary}
