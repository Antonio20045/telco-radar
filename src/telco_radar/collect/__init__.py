"""Collectors: fetch items from RSS feeds and HTML newsroom pages."""
from __future__ import annotations

import logging
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from ..config import Config, Source, Operator
from ..models import Item
from .http import configure_throttle, deadline
from .rss import collect_rss
from .json_api import collect_json
from .newsroom import collect_newsroom
from .newsroom_js import collect_newsroom_js

log = logging.getLogger(__name__)


# Harte Frist je Quelle. Im Lauf #75 brauchte EINE tote Quelle (KT, mit
# timeout_seconds: 30 und der vollen Retry-Leiter) 302,6 s - und die gesamte
# Sammelphase dauerte 303,7 s. Bei 1000 Quellen hilft keine Parallelitaet
# gegen den langsamsten Einzelfall, also bekommt jede Quelle einen Deckel.
# 75 s lassen einer wirklich langsamen Quelle zwei volle Versuche mit 30 s.
_QUELLEN_FRIST = 75.0


# Gleichzeitige Headless-Browser. Anders als ein HTTP-Abruf ist ein
# newsroom_js-Abruf NICHT reine Wartezeit: jeder startet einen Chromium und
# rendert eine Seite, und der GitHub-Runner hat zwei Kerne. Im Diagnoselauf
# #74 (05.08.2026) fiel bei 64 Workern Viettel mit "Page.goto: Timeout 16000ms
# exceeded" aus, das bei 8 Workern durchlief - die Seite war nicht langsamer,
# der Rechner war voll. Die Zahl der Worker darf also steigen, die Zahl
# gleichzeitiger Renderings nicht.
_JS_GLEICHZEITIG = threading.BoundedSemaphore(4)


def _collect_source(source: Source, region: str, operator: str | None,
                    origin: str, http_cfg: dict) -> list[Item]:
    """Dispatch a source to the right collector based on its kind."""
    with deadline(_QUELLEN_FRIST):
        return _dispatch(source, region, operator, origin, http_cfg)


def _dispatch(source: Source, region: str, operator: str | None,
              origin: str, http_cfg: dict) -> list[Item]:
    if source.kind in ("rss", "trade_press"):
        items = collect_rss(source, region, operator, origin, http_cfg)
    elif source.kind == "json_api":
        items = collect_json(source, region, operator, origin, http_cfg)
    elif source.kind == "newsroom_js":
        with _JS_GLEICHZEITIG:
            items = collect_newsroom_js(source, region, operator, origin, http_cfg)
    else:
        items = collect_newsroom(source, region, operator, origin, http_cfg)
    if source.exclude_url_pattern:
        # e.g. Verizon mirrors 7 of every 25 releases in Spanish under
        # /about/news/es/ - a different URL, so the seen-store treats it as a
        # separate story and the same news enters the report twice.
        drop = re.compile(source.exclude_url_pattern)
        items = [i for i in items if not drop.search(i.url)]
    # Zentral statt in jedem Collector: die Trefferquote je KANAL braucht die
    # Quellen-URL, und ein Betreiber mit Newsroom plus Investor Relations
    # traegt in beiden denselben source_name.
    for item in items:
        item.source_url = source.url
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


def collect_all(cfg: Config, max_workers: int | None = None,
                register=None) -> tuple[list[Item], list[dict]]:
    """Fetch every configured (crawlable) source concurrently.

    Returns (items, source_results). Each source_result is a dict describing
    what happened with that source (status/count/error) so the pipeline can
    build a transparent run log. A failing source never aborts the run.

    max_workers kommt aus settings.yaml (collect_max_workers). Mit dem
    Quellen-Ausbau ist das der Stellhebel gegen die Laufzeit: die Sammelphase
    ist reine Wartezeit auf fremde Server, also skaliert sie fast linear mit
    der Parallelitaet. Eine Kappung der Meldungen waere die falsche Antwort -
    was hier nicht gesammelt wird, sieht kein Analyst je.

    Der Worker-Pool allein reicht dafuer aber nicht: er sagt nur, wie viele
    Quellen gleichzeitig laufen, nicht wie viele davon denselben Server
    treffen. Die Begrenzung je Host macht deshalb collect/http.py (HostGate),
    hier konfiguriert aus settings.yaml. Erst beides zusammen erlaubt einen
    grossen Pool, ohne 429/403 zu ernten.
    """
    http_cfg = cfg.settings.get("http", {})
    if max_workers is None:
        max_workers = int(cfg.settings.get("collect_max_workers", 4) or 4)
    configure_throttle(
        int(cfg.settings.get("collect_host_max_parallel", 2) or 2),
        float(cfg.settings.get("collect_host_min_interval_seconds", 0.0) or 0.0),
    )
    jobs: list[tuple[Source, str, str | None, str]] = []

    for op in cfg.operators:
        for src in op.crawled_sources:
            jobs.append((src, op.region_key, op.name, "operator"))
    for src in cfg.news_sources:
        # Vorgabe-Region der Quelle, sonst "global". tag_news_regions
        # ueberschreibt das gleich wieder, sobald ein Betreibername in der
        # Ueberschrift steht - die Vorgabe greift also nur dort, wo bisher
        # ueberhaupt keine Zuordnung zustande kam.
        jobs.append((src, src.region or "global", None, "industry_news"))
    # Themenquellen laufen unter ihrem Themenschluessel als "Region" - so
    # bekommt jedes Themenfeld einen eigenen Analysten, ohne dass die
    # Regionslogik der Watchlist es fuer einen Betreiber haelt.
    for src in cfg.tech_sources:
        if src.crawlable:
            jobs.append((src, src.theme, src.name, "tech_watch"))

    # Stillgelegte Quellen ueberspringen. Das ist bei 1000 Quellen kein
    # Komfort, sondern Laufzeit: eine tote Quelle, die in jeden Timeout
    # laeuft, kostet mehr als eine lebende. Der Bewaehrungsabruf (siehe
    # quellen_register.py) holt sie regelmaessig zurueck in die Liste.
    uebersprungen: list[dict] = []
    if register is not None:
        aktiv = []
        for job in jobs:
            src = job[0]
            if register.wird_abgerufen(src.url):
                aktiv.append(job)
            else:
                e = register.eintrag(src.url)
                uebersprungen.append({
                    "name": job[2] or src.name, "operator": job[2],
                    "region": job[1], "url": src.url, "kind": src.kind,
                    "label": src.label or src.kind, "origin": job[3],
                    "status": "quarantaene", "count": 0, "seconds": 0.0,
                    "error": e.quarantaene_grund if e else "",
                })
        if uebersprungen:
            log.info("Quarantaene: %d von %d Quellen werden nicht abgerufen",
                     len(uebersprungen), len(jobs))
        jobs = aktiv

    def _timed(src, region, operator, origin):
        """Wanduhr je Quelle - ohne sie ist nicht zu sehen, WELCHE Quelle die
        Sammelphase aufhaelt, und genau das entscheidet bei 1000 Quellen.

        Liefert (items, sekunden, fehler); ein Fehler wird mitgegeben statt
        geworfen, damit die Dauer auch bei einer gescheiterten Quelle im
        Protokoll steht.
        """
        t0 = time.monotonic()
        try:
            got = _collect_source(src, region, operator, origin, http_cfg)
            return got, time.monotonic() - t0, None
        except Exception as exc:  # noqa: BLE001 - resilience by design
            return None, time.monotonic() - t0, exc

    items: list[Item] = []
    results: list[dict] = []
    t_start = time.monotonic()
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {
            pool.submit(_timed, src, region, operator, origin):
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
            got, dauer, exc = fut.result()
            rec["seconds"] = round(dauer, 2)
            if exc is not None:
                rec["status"] = "fail"
                rec["count"] = 0
                rec["error"] = f"{type(exc).__name__}: {str(exc)[:140]}"
                log.warning("FAIL  %-22s %-45s -> %s (%.1fs)",
                            (operator or src.name)[:22], src.url[:45],
                            rec["error"], dauer)
            else:
                items.extend(got)
                rec["status"] = "ok" if got else "empty"
                rec["count"] = len(got)
                log.info("%-5s %-22s %-45s -> %d items (%.1fs)",
                         rec["status"].upper(), (operator or src.name)[:22],
                         src.url[:45], len(got), dauer)
            results.append(rec)

    results.extend(uebersprungen)
    wanduhr = time.monotonic() - t_start
    arbeit = sum(r.get("seconds", 0.0) for r in results)
    log.info("Sammelphase: %d Quellen in %.1fs Wanduhr (%.1fs Arbeit, Faktor "
             "%.1f bei %d Workern, max. %d je Host)",
             len(results), wanduhr, arbeit,
             arbeit / wanduhr if wanduhr else 0.0, max_workers,
             int(cfg.settings.get("collect_host_max_parallel", 2) or 2))
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
