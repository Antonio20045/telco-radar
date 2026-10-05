"""Die Phase Bewerten & Schreiben: Analysten, Redaktion oder Roh-Digest ohne LLM."""

from __future__ import annotations

import logging
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field, replace

from ..config import Config, is_theme_key
from ..models import Item
from . import editor
from .agents import analyze_region
from .takt import Absicherung, Takt

log = logging.getLogger(__name__)


def redaktion_zweistufig(settings: dict, bewertete: int) -> bool:
    """Ob die Redaktion bei ``bewertete`` Meldungen zweistufig schreibt."""
    modus = str(settings.get("editor_modus", "auto") or "auto").lower()
    if modus == "zweistufig":
        return True
    if modus == "einstufig":
        return False
    if modus != "auto":
        log.warning("Unbekannter editor_modus %r - benutze auto", modus)
    schwelle = int(settings.get("editor_zweistufig_ab_meldungen", 120) or 120)
    return bewertete >= schwelle


@dataclass(frozen=True)
class Bewertung:
    """Ergebnis der Phase Bewerten: Bereiche, Briefing und was ungelesen blieb."""

    regional: dict[str, dict]
    body: str
    covered: list[str]
    editor_used: bool
    analyst_telemetry: list[dict] = field(default_factory=list)
    unanalysierte_regionen: set[str] = field(default_factory=set)
    ungelesene_meldungen: set[str] = field(default_factory=set)


def _roh_highlight(
    i: Item, operator: str, kategorie: str, relevanz: int | None, laenge: int
) -> dict:
    return {
        "title": i.title,
        "operator": operator,
        "url": i.url,
        "category": kategorie,
        "relevance": relevanz,
        "summary": i.summary[:laenge],
        "why_it_matters": "",
    }


def _analysten(
    cfg: Config,
    items_by_region: dict[str, list[Item]],
    modelle: tuple[str, str],
    language: str,
    max_items: int | None,
    abgesichert: Absicherung,
) -> Bewertung:
    analyst_model, ausweich = modelle
    regional: dict[str, dict] = {}
    bewertung = Bewertung(regional, "", [], False)
    batch_workers = int(cfg.settings.get("analyst_batch_workers", 1) or 1)

    def _analyze_one(region_key, region_items):
        region_name = cfg.bereich_names.get(region_key, region_key)

        def _lesen():
            res = analyze_region(
                region_name,
                region_items,
                model=analyst_model,
                language=language,
                max_items=max_items,
                is_theme=is_theme_key(region_key),
                batch_workers=batch_workers,
                ausweich=ausweich,
            )
            tel = dict(res.get("_telemetry", {}))
            tel["region"] = region_name
            if tel.get("batches") and not tel.get("batches_ok"):
                bewertung.unanalysierte_regionen.add(region_key)
            return region_name, res, tel

        def _roh(exc: Exception):
            log.error(
                "Analyst %s failed: %s - falling back to raw list", region_name, exc
            )
            bewertung.unanalysierte_regionen.add(region_key)
            fallback = {
                "region_summary": "",
                "highlights": [
                    _roh_highlight(i, i.operator or "", "Sonstiges", 2, 200)
                    for i in region_items[:10]
                ],
            }
            return region_name, fallback, None

        return abgesichert(_lesen, _roh)

    workers = max(1, int(cfg.settings.get("llm_max_workers", 4)))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futs = [pool.submit(_analyze_one, rk, ri) for rk, ri in items_by_region.items()]
        for fut in as_completed(futs):
            region_name, res, tel = fut.result()
            bewertung.ungelesene_meldungen.update(res.pop("_ungelesen", []) or [])
            regional[region_name] = res
            if tel is not None:
                bewertung.analyst_telemetry.append(tel)
    return bewertung


def _redigieren(
    cfg: Config,
    analyse: Bewertung,
    items_by_region: dict[str, list[Item]],
    redaktion: tuple[list, str, str],
    abgesichert: Absicherung,
) -> Bewertung:
    recent, editor_model, language = redaktion
    regional = analyse.regional
    themen_mit_inhalt = [
        name
        for name in cfg.theme_names.values()
        if regional.get(name, {}).get("highlights")
    ]
    bewertete = sum(len(r.get("highlights") or []) for r in regional.values())

    def _schreiben() -> Bewertung:
        if redaktion_zweistufig(cfg.settings, bewertete):
            body, covered = editor.synthesize_zweistufig(
                regional,
                recent,
                model=editor_model,
                language=language,
                themenbereiche=themen_mit_inhalt,
                workers=int(cfg.settings.get("llm_max_workers", 4)),
            )
        else:
            body, covered = editor.synthesize(
                regional,
                recent,
                model=editor_model,
                language=language,
                highlight_budget=int(cfg.settings.get("editor_max_highlights", 0) or 0),
                themenbereiche=themen_mit_inhalt,
            )
        return replace(analyse, body=body, covered=covered, editor_used=True)

    def _ausfall(exc: Exception) -> Bewertung:
        if cfg.settings.get("publish_requires_editorial_briefing", True):
            raise RuntimeError(
                "Editorial synthesis failed; refusing to publish a raw "
                "source digest. The previous briefing remains live."
            ) from exc
        log.warning(
            "Editorial synthesis failed (%s); publishing a labelled "
            "source-linked fallback digest",
            str(exc)[:180],
        )
        fallback, covered = editor.build_digest(
            items_by_region,
            cfg.bereich_names,
            llm_was_available=False,
            include_note=False,
        )
        body = (
            "## Redaktions-Fallback\n\n"
            "> Die aktuelle Quellenliste konnte wegen einer vorübergehenden "
            "Störung des Analyse-Dienstes nicht redaktionell verdichtet "
            "werden. Die Links und Meldungen stammen trotzdem aus diesem "
            "Lauf; die automatische Redaktion wird im nächsten Lauf erneut "
            "versucht.\n\n" + fallback
        )
        return replace(analyse, body=body, covered=covered)

    return abgesichert(_schreiben, _ausfall)


def _roh_digest(
    cfg: Config,
    items_by_region: dict[str, list[Item]],
    max_items: int | None,
    use_llm: bool,
    first_run: bool,
) -> Bewertung:
    regional = {
        cfg.bereich_names.get(rk, rk): {
            "region_summary": "",
            "highlights": [
                _roh_highlight(i, i.operator or i.source_name, "Unbewertet", None, 220)
                for i in (ri if not max_items else ri[:max_items])
            ],
        }
        for rk, ri in items_by_region.items()
    }
    body, covered = editor.build_digest(
        items_by_region, cfg.bereich_names, llm_was_available=use_llm
    )
    if first_run:
        body = (
            "> **Erster Lauf (Baseline):** Alle Quellen wurden initial "
            "eingelesen. Ab dem naechsten Lauf erscheinen nur noch "
            "wirklich neue Meldungen.\n\n" + body
        )
    return Bewertung(regional, body, covered, False)


def bewerten(
    cfg: Config,
    items_by_region: dict[str, list[Item]],
    neu: tuple[list[Item], bool],
    llm_modus: tuple[bool, bool],
    modelle: tuple[str, str, str],
    language: str,
    recent: Callable[[], list],
    takt: Takt,
) -> Bewertung:
    """Phase Bewerten & Schreiben: Analysten und Redaktion oder Roh-Digest ohne LLM."""
    use_llm, abgeschaltet = llm_modus
    new_items, first_run = neu
    analyst_model, editor_model, ausweich = modelle
    max_items = int(cfg.settings.get("max_items_per_region", 0) or 0) or None
    ta = takt.stoppuhr()
    if use_llm and new_items:
        analyse = _analysten(
            cfg,
            items_by_region,
            (analyst_model, ausweich),
            language,
            max_items,
            takt.abgesichert,
        )
        bewertung = _redigieren(
            cfg,
            analyse,
            items_by_region,
            (recent(), editor_model, language),
            takt.abgesichert,
        )
    else:
        if (
            new_items
            and not abgeschaltet
            and cfg.settings.get("publish_requires_editorial_briefing", True)
        ):
            raise RuntimeError(
                "No editorial model is available; refusing to publish a raw "
                "source digest. The previous briefing remains live."
            )
        if use_llm and not new_items:
            log.info("No new items - writing empty briefing")
        bewertung = _roh_digest(
            cfg, items_by_region, max_items, bool(use_llm), first_run
        )
    takt.phase(
        "Bewerten & Schreiben",
        takt.stoppuhr() - ta,
        f"{sum(len(r.get('highlights') or []) for r in bewertung.regional.values())} "
        f"bewertete Meldungen"
        if use_llm
        else "ohne KI (Roh-Digest)",
    )
    return bewertung
