"""Collectors: fetch items from RSS feeds and HTML newsroom pages."""
from __future__ import annotations

import logging
import re
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urlsplit

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
    # Herkunft zentral stempeln statt in jedem Collector: die Trefferquote je
    # Quelle braucht den KANAL, und source_name traegt bei Betreibern nur den
    # Firmennamen. Hier steht der einzige Punkt, an dem jede gesammelte
    # Meldung garantiert vorbeikommt.
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


def _host(url: str) -> str:
    """Registrierbarer Host einer Quelle, klein geschrieben, ohne www."""
    try:
        netloc = urlsplit(url).netloc.lower()
    except ValueError:
        return url.lower()
    return netloc.split("@")[-1].split(":")[0].removeprefix("www.")


def sammelplan(jobs: list, host_parallel: int = 1,
               url_von=lambda job: job[0].url) -> list[list]:
    """Jobs in Gruppen schneiden, die parallel laufen duerfen.

    Eine Gruppe wird von genau einem Worker der Reihe nach abgearbeitet.
    Zwei Quellen desselben Hosts landen deshalb nie gleichzeitig im Netz -
    das ist der ganze Trick: statt Threads an einer Host-Sperre warten zu
    lassen (was bei 1000 Quellen den Pool blockiert, waehrend andere Hosts
    unangetastet bleiben), wird die Host-Serialitaet in den PLAN gelegt.

    `host_parallel` > 1 erlaubt mehrere gleichzeitige Verbindungen je Host,
    indem dessen Jobs auf entsprechend viele Gruppen verteilt werden.

    Die groessten Gruppen kommen zuerst (LPT-Scheduling): sonst startet der
    Host mit 20 Quellen zufaellig zuletzt und bestimmt allein die Laufzeit
    der ganzen Phase.

    `url_von` macht den Plan auch fuer andere Aufgaben nutzbar - der
    Abnahme-Check prueft bei 1000 Kandidaten mit denselben Regeln, statt
    eine zweite, ungetestete Drosselung danebenzustellen.
    """
    nach_host: dict[str, list] = defaultdict(list)
    for job in jobs:
        nach_host[_host(url_von(job))].append(job)
    gruppen: list[list] = []
    for host_jobs in nach_host.values():
        n = max(1, min(int(host_parallel), len(host_jobs)))
        for i in range(n):
            teil = host_jobs[i::n]
            if teil:
                gruppen.append(teil)
    gruppen.sort(key=len, reverse=True)
    return gruppen


def collect_all(cfg: Config, max_workers: int | None = None,
                ueberspringen: set[str] | None = None
                ) -> tuple[list[Item], list[dict]]:
    """Fetch every configured (crawlable) source concurrently.

    Returns (items, source_results). Each source_result is a dict describing
    what happened with that source (status/count/error/seconds) so the
    pipeline can build a transparent run log. A failing source never aborts
    the run.

    Parallelitaet MIT Host-Drosselung
    ---------------------------------
    Die Sammelphase ist reine Wartezeit auf fremde Server und skaliert
    deshalb fast linear mit der Parallelitaet: gemessen an Lauf #67 kostet
    eine Quelle 20 Sekunden mal Worker, 1000 Quellen bei den alten 8 Workern
    waeren also ~42 min gewesen - allein das sprengt das Job-Timeout, bevor
    eine einzige Meldung bewertet ist.

    Einfach den Pool zu vergroessern reicht aber nicht. Bei 1000 Quellen
    liegen zwangslaeufig mehrere auf derselben Domain (blog.google hat heute
    schon drei), und viele gleichzeitige Verbindungen zum selben Host
    provozieren 429/403 - ein Fehler, den der Collector als "Quelle tot"
    protokolliert, obwohl nur zu schnell gefragt wurde. Deshalb: global viel
    Parallelitaet, je Host hoechstens `collect_host_parallel` gleichzeitig
    und dazwischen `collect_host_delay_seconds` Abstand.

    `ueberspringen` enthaelt die URLs stillgelegter Quellen (Quarantaene).
    Sie werden nicht abgerufen, erscheinen aber mit Status "quarantaene" im
    Protokoll - eine still verschwundene Quelle waere schlimmer als eine
    tote.
    """
    http_cfg = cfg.settings.get("http", {})
    if max_workers is None:
        max_workers = int(cfg.settings.get("collect_max_workers", 4) or 4)
    host_parallel = int(cfg.settings.get("collect_host_parallel", 1) or 1)
    host_delay = float(cfg.settings.get("collect_host_delay_seconds", 0.0) or 0.0)
    ueberspringen = ueberspringen or set()
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

    def _protokoll(src: Source, region: str, operator: str | None,
                   origin: str) -> dict:
        return {
            "name": operator or src.name,
            "operator": operator,
            "region": region,
            "url": src.url,
            "kind": src.kind,
            "label": src.label or src.kind,
            "origin": origin,
        }

    results: list[dict] = []
    stillgelegt = [j for j in jobs if j[0].url in ueberspringen]
    for src, region, operator, origin in stillgelegt:
        rec = _protokoll(src, region, operator, origin)
        rec.update(status="quarantaene", count=0, seconds=0.0)
        results.append(rec)
    if stillgelegt:
        log.info("%d Quelle(n) stillgelegt (Quarantaene) - nicht abgefragt",
                 len(stillgelegt))
    jobs = [j for j in jobs if j[0].url not in ueberspringen]

    def _eine_gruppe(gruppe: list) -> list[tuple[dict, list[Item]]]:
        """Eine Host-Gruppe der Reihe nach abarbeiten."""
        ausgabe: list[tuple[dict, list[Item]]] = []
        for n, (src, region, operator, origin) in enumerate(gruppe):
            if n and host_delay:
                time.sleep(host_delay)
            rec = _protokoll(src, region, operator, origin)
            t0 = time.monotonic()
            try:
                got = _collect_source(src, region, operator, origin, http_cfg)
                rec["status"] = "ok" if got else "empty"
                rec["count"] = len(got)
                log.info("%-5s %-22s %-45s -> %d items",
                         rec["status"].upper(), (operator or src.name)[:22],
                         src.url[:45], len(got))
            except Exception as exc:  # noqa: BLE001 - resilience by design
                got = []
                rec["status"] = "fail"
                rec["count"] = 0
                rec["error"] = f"{type(exc).__name__}: {str(exc)[:140]}"
                log.warning("FAIL  %-22s %-45s -> %s",
                            (operator or src.name)[:22], src.url[:45],
                            rec["error"])
            # Sekunden je Quelle: die Zahl, an der sich Host-Drosselung und
            # Timeouts nachrechnen lassen, statt sie zu schaetzen.
            rec["seconds"] = round(time.monotonic() - t0, 2)
            ausgabe.append((rec, got))
        return ausgabe

    gruppen = sammelplan(jobs, host_parallel)
    log.info("Sammelplan: %d Quellen in %d Gruppen (max %d gleichzeitig, "
             "je Host %d parallel, %.1fs Abstand)",
             len(jobs), len(gruppen), max_workers, host_parallel, host_delay)

    items: list[Item] = []
    with ThreadPoolExecutor(max_workers=max(1, max_workers)) as pool:
        for fut in as_completed([pool.submit(_eine_gruppe, g) for g in gruppen]):
            for rec, got in fut.result():
                items.extend(got)
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
