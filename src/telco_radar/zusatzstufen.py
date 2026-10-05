"""Die Stufen nach der Bewertung: Kategorie-Sweep, Promo, Geräte, Differenzierung."""

from __future__ import annotations

import logging
import os
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from .analyze import category_sweep, differentiation_editor
from .analyze.begriffe import THEME_LABEL
from .analyze.diff_curator import DiffStore
from .analyze.diff_db import DiffDB
from .analyze.takt import Takt, protokoll
from .config import Config
from .report import diff_bilder, differenzierung_view

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Zusatz:
    """Bilanzen der Zusatzstufen für die Kennzahlen des Berichts."""

    promo: dict
    geraete: dict


def ausfuehren(
    cfg: Config,
    root: Path,
    heute: date,
    sprache: tuple[str, str, str],
    use_llm: bool,
    geraete_frist: Callable[[], float | None],
    takt: Takt,
) -> Zusatz:
    """Kategorie-Sweep, Promo-Übersicht, Geräteradar und Differenzierungsbericht."""
    editor_model, mechanik_model, language = sprache
    state_dir = root / "data" / "state"
    takt.abgesichert(
        lambda: category_sweep.run_sweep(
            state_dir,
            os.environ.get("BRAVE_API_KEY", ""),
            mechanik_model,
            use_llm,
            heute.isocalendar()[1],
            heute.isoformat(),
        ),
        protokoll("Kategorie-Sweep uebersprungen: %s", None),
    )
    promo = _promo(cfg, root, heute, sprache, use_llm, takt)
    geraete = _geraete(cfg, root, heute, geraete_frist(), takt)
    _differenzierung(root, heute, (editor_model, language), use_llm, takt)
    return Zusatz(promo, geraete)


def _promo(
    cfg: Config,
    root: Path,
    heute: date,
    sprache: tuple[str, str, str],
    use_llm: bool,
    takt: Takt,
) -> dict:
    if not cfg.settings.get("promo_enabled", True):
        return {}
    editor_model, mechanik_model, language = sprache

    def _lauf() -> dict:
        from .promo_pipeline import run_promo_stage

        ergebnis = run_promo_stage(
            root,
            cfg.settings.get("http", {}),
            use_llm,
            editor_model,
            language=language,
            settings=cfg.settings,
            score_model=mechanik_model,
            extract_model=mechanik_model,
            heute=heute,
        )
        log.info(
            "Promo-Uebersicht: %s (%d aktive Aktionen)",
            ergebnis.get("mode"),
            ergebnis.get("active", 0),
        )
        return ergebnis

    return takt.abgesichert(_lauf, protokoll("Promo-Uebersicht uebersprungen: %s", {}))


def _geraete(
    cfg: Config, root: Path, heute: date, budget: float | None, takt: Takt
) -> dict:
    if budget is None:
        if cfg.settings.get("geraete_enabled", False):
            log.warning(
                "Geraeteradar uebersprungen: zu wenig Jobzeit uebrig. "
                "Der naechtliche Lauf holt es nach - die "
                "Veroeffentlichung geht vor."
            )
        return {}

    def _lauf() -> dict:
        from .geraete_pipeline import run_geraete_stage

        return run_geraete_stage(
            root, cfg.settings.get("http", {}), heute.isoformat(), frist_sekunden=budget
        )

    return takt.abgesichert(_lauf, protokoll("Geraeteradar uebersprungen: %s", {}))


def _differenzierung(
    root: Path, heute: date, sprache: tuple[str, str], use_llm: bool, takt: Takt
) -> None:
    state_dir = root / "data" / "state"
    reports_dir = root / "data" / "reports"
    diff_report_dir = reports_dir / "differenzierung"
    diff_report_dir.mkdir(parents=True, exist_ok=True)
    diff_db = DiffDB(state_dir / "differentiation_db.json")
    diff_entries = list(diff_db.entries.values())
    diff_body, diff_mode = takt.abgesichert(
        lambda: _diff_bericht(diff_entries, sprache, use_llm),
        _regelbericht_nach(diff_entries),
    )
    diff_report_path = diff_report_dir / f"{heute.isoformat()}.md"
    diff_report_path.write_text(diff_body, encoding="utf-8")
    log.info("Differenzierungsbericht: %s (%d Moves)", diff_mode, len(diff_entries))

    def _bilder() -> None:
        diff_store_fuer_bilder = DiffStore(state_dir / "differentiation.jsonl")
        diff_bestand = differenzierung_view.merge(
            diff_entries, diff_store_fuer_bilder.entries()
        )
        bilanz = diff_bilder.beschaffe(
            diff_bestand, root, reports_dir, heute.isoformat()
        )
        log.info(
            "Differenzierungs-Bilder: %d von %d Beispielen",
            bilanz.get("mit_bild", 0),
            bilanz.get("bestand", 0),
        )

    takt.abgesichert(
        _bilder, protokoll("Differenzierungs-Bilder uebersprungen: %s", None)
    )


def _diff_bericht(
    diff_entries: list, sprache: tuple[str, str], use_llm: bool
) -> tuple[str, str]:
    editor_model, language = sprache
    if use_llm and diff_entries:
        diff_body = differentiation_editor.synthesize(
            diff_entries, THEME_LABEL, model=editor_model, language=language
        )
        return diff_body, "KI-Redaktion"
    return differentiation_editor.build_digest(
        diff_entries, THEME_LABEL
    ), "Regelbericht"


def _regelbericht_nach(diff_entries: list) -> Callable[[Exception], tuple[str, str]]:
    def _ausfall(exc: Exception) -> tuple[str, str]:
        log.warning(
            "Differenzierungsbericht-Agent fehlgeschlagen (%s) – verwende Regelbericht",
            str(exc)[:160],
        )
        diff_body = differentiation_editor.build_digest(diff_entries, THEME_LABEL)
        return diff_body, "Regelbericht (Fallback)"

    return _ausfall
