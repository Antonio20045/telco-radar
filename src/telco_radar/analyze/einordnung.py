"""Die Phasen Einordnen für uns und Wettbewerber-Analyse, dazu Themen und Moves."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from ..config import Config
from ..models import Item
from . import competitors as competitor_mod
from . import ctm as ctm_mod
from . import diff_curator, faithfulness, highlight_topics
from .takt import Takt, protokoll

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Einordnung:
    """Ergebnis der Phase Einordnen für uns: CTM- und Belegbilanz."""

    ctm: dict
    beleg: dict


def einordnen(
    regional: dict[str, dict],
    cfg: Config,
    root: Path,
    mechanik_model: str,
    use_llm: bool,
    takt: Takt,
) -> Einordnung:
    """Phase Einordnen für uns: CTM-Linse und Belegprüfung der Folgerungssätze."""
    tctm = takt.stoppuhr()
    ctm_bilanz: dict = {}
    beleg_bilanz: dict = {}

    def _linse() -> None:
        fokus = ctm_mod.lade_fokus(root)
        for region_name, r in regional.items():
            for h in r.get("highlights", []):
                h.setdefault("region", region_name)
        alle = [h for r in regional.values() for h in r.get("highlights", [])]
        ctm_bilanz.update(ctm_mod.veredle(alle, fokus))
        beleg_bilanz.update(
            faithfulness.pruefe(
                alle,
                model=mechanik_model,
                use_llm=use_llm and bool(cfg.settings.get("ctm_belegpruefung", True)),
            )
        )
        log.info(
            "CTM-Linse: %d direkt / %d uebertragbar / %d Kontext / "
            "%d Hintergrund | Saetze: %d belegt, %d verworfen",
            ctm_bilanz.get("direkt", 0),
            ctm_bilanz.get("uebertragbar", 0),
            ctm_bilanz.get("kontext", 0),
            ctm_bilanz.get("hintergrund", 0),
            beleg_bilanz.get("belegt", 0),
            ctm_bilanz.get("saetze_verworfen", 0) + beleg_bilanz.get("verworfen", 0),
        )

    takt.abgesichert(_linse, protokoll("CTM-Linse uebersprungen: %s", None))
    takt.phase(
        "Einordnen für uns",
        takt.stoppuhr() - tctm,
        f"{ctm_bilanz.get('direkt', 0)} direkt handlungsrelevant, "
        f"{beleg_bilanz.get('belegt', 0)} belegte Folgerungssätze",
    )
    for r in regional.values():
        r.pop("_telemetry", None)
    return Einordnung(ctm_bilanz, beleg_bilanz)


def wettbewerber(
    cfg: Config,
    items: list[Item],
    model: str,
    language: str,
    takt: Takt,
) -> list[dict]:
    """Phase Wettbewerber-Analyse: ein Profil je Fokus-Wettbewerber."""
    tcomp = takt.stoppuhr()
    profile: list[dict] = takt.abgesichert(
        lambda: competitor_mod.analyze_all(
            cfg.focus_competitors,
            items,
            model,
            language,
            max_workers=int(cfg.settings.get("llm_max_workers", 4)),
        ),
        protokoll("Competitor deep-dive failed: %s", []),
    )
    takt.phase(
        "Wettbewerber-Analyse",
        takt.stoppuhr() - tcomp,
        f"{len(profile)} Profile "
        f"({sum(len(c.get('moves') or []) for c in profile)} Moves)",
    )
    return profile


def themen_und_moves(
    regional: dict[str, dict],
    cfg: Config,
    orte: tuple[Path, Path, str],
    modelle: tuple[str, str],
    use_llm: bool,
    takt: Takt,
) -> None:
    """Pflegt Highlight-Themen und nimmt neue Differenzierungs-Moves auf."""
    state_dir, reports_dir, today_iso = orte
    themen_model, mechanik_model = modelle
    alle_highlights = [h for r in regional.values() for h in r.get("highlights", [])]

    def _themen() -> None:
        themen_bilanz = highlight_topics.pflege_highlight_themen(
            alle_highlights,
            state_dir,
            today_iso,
            model=themen_model,
            use_llm=use_llm,
            reports_dir=reports_dir,
        )
        log.info(
            "Highlight-Themen: %d aktiv, %d Kandidat(en), neu: %s, beendet: %s",
            themen_bilanz["aktiv"],
            themen_bilanz["kandidaten"],
            ", ".join(themen_bilanz["neu"]) or "keins",
            ", ".join(themen_bilanz["beendet"]) or "keins",
        )

    def _moves() -> None:
        themen_namen = set(cfg.theme_names.values())
        flat_new = [
            {**h, "region": region_name}
            for region_name, r in regional.items()
            if region_name not in themen_namen
            for h in r.get("highlights", [])
        ]
        diff_store = diff_curator.DiffStore(state_dir / "differentiation.jsonl")
        added = diff_curator.curate(
            flat_new, diff_store, today_iso, model=mechanik_model, use_llm=use_llm
        )
        log.info(
            "Differenzierung: %d neue Move(s) aufgenommen (Speicher: %d)",
            len(added),
            len(diff_store),
        )

    takt.abgesichert(_themen, protokoll("Highlight-Themen uebersprungen: %s", None))
    takt.abgesichert(
        _moves, protokoll("Differenzierungs-Kurator uebersprungen: %s", None)
    )
