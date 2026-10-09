"""Redaktion, Veröffentlichen und Bericht: was nach den Stufen eines Laufs bleibt."""

from __future__ import annotations

import json
import logging
from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

from .analyze import editor, llm, redaktion_kontinuitaet
from .analyze.takt import Takt, protokoll
from .config import Config
from .dedupe import ReportedTopics
from .models import Item
from .report import bilder as report_bilder
from .report import geraete_bewegung
from .report.ausfall import Ausfall
from .report.html import render_site
from .uebersetzung import stufe as uebersetzung_stufe

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Bericht:
    """Der geschriebene Bericht: Pfade und das Berichts-JSON, das weiter wächst."""

    report_path: Path
    json_path: Path
    report_json: dict


def bericht_schreiben(
    root: Path,
    heute: date,
    inhalt: tuple[dict, str, list[dict]],
    stats: dict,
    run_log: dict,
    mit_llm: bool,
    neue: int,
) -> Bericht:
    """Übernimmt bei Redaktionsausfall den letzten Stand, schreibt Markdown und JSON."""
    regional, body, competitor_profiles = inhalt
    reports_dir = root / "data" / "reports"
    stats["bewertete"] = redaktion_kontinuitaet.bewertete_meldungen(
        {"regions": regional}
    )
    grund = (
        "es gab keine neuen Meldungen zu bewerten"
        if not neue
        else redaktion_kontinuitaet.ausfallgrund(
            llm.LlmSitzung.aktive().tote_modelle, llm.llm_available()
        )
    )
    regional, body, competitor_profiles, redaktion_ausfall = (
        redaktion_kontinuitaet.uebernehmen(
            regional, body, competitor_profiles, reports_dir, heute.isoformat(), grund
        )
    )

    report_md = editor.report_header(heute, stats) + body
    report_path = reports_dir / f"{heute.isoformat()}.md"
    report_path.write_text(report_md, encoding="utf-8")

    report_json = {
        "date": heute.isoformat(),
        "generated_with_llm": mit_llm,
        "stats": stats,
        "briefing_md": body,
        "regions": regional,
        "competitors": competitor_profiles,
        "run": run_log,
    }
    if redaktion_ausfall:
        report_json["redaktion_ausfall"] = redaktion_ausfall
    report_json["geraete_bewegung"] = geraete_bewegung.fuer_bericht(
        root, heute, reports_dir
    )
    json_path = reports_dir / f"{heute.isoformat()}.json"
    bericht = Bericht(report_path, json_path, report_json)
    _json_schreiben(bericht)
    log.info(
        "Report written: %s (+ .json), run took %.1fs",
        report_path,
        run_log["duration_seconds"],
    )
    return bericht


def themen_merken(
    topics_store: ReportedTopics, covered: list[str], editor_used: bool, heute: date
) -> None:
    """Merkt berichtete Themen, aber nur, wenn die Redaktion sie geschrieben hat."""
    if covered and editor_used:
        topics_store.add(covered, heute.isoformat())
    elif covered:
        log.warning(
            "%d Themen stammen aus dem Notfall-Digest, nicht aus der "
            "Redaktion - sie werden NICHT als berichtet gemerkt",
            len(covered),
        )


def nachlauf(
    bericht: Bericht,
    berichtet: tuple[list[dict], dict[str, Item]],
    cfg: Config,
    root: Path,
    stufe: tuple[str, datetime, float],
    takt: Takt,
) -> list[Ausfall]:
    """Übersetzung, Kosten, Seite und Versand; liefert nicht gebaute Seitenteile."""
    run_log = bericht.report_json["run"]
    _uebersetzen(berichtet, cfg, root, stufe, takt, run_log)

    run_log["kosten"] = llm.kosten_stand()
    bericht.report_json["run"] = run_log
    _protokolliere_kosten(run_log["kosten"])
    _json_schreiben(bericht)

    reports_dir = root / "data" / "reports"
    takt.abgesichert(
        lambda: report_bilder.raeume_auf(root, reports_dir),
        protokoll("Bilder-Aufraeumen fehlgeschlagen: %s", None),
    )
    ausfaelle = render_site(root / "site", reports_dir, cfg)

    def _versand() -> None:
        from .versand import versende

        run_log["versand"] = versende(
            root, bericht.report_json, cfg.settings, jetzt=stufe[1]
        )
        _json_schreiben(bericht)

    takt.abgesichert(_versand, protokoll("Versand uebersprungen: %s", None))
    return ausfaelle


def _json_schreiben(bericht: Bericht) -> None:
    bericht.json_path.write_text(
        json.dumps(bericht.report_json, ensure_ascii=False, indent=1), encoding="utf-8"
    )


def _uebersetzen(
    berichtet: tuple[list[dict], dict[str, Item]],
    cfg: Config,
    root: Path,
    stufe: tuple[str, datetime, float],
    takt: Takt,
    run_log: dict,
) -> None:
    alle_highlights, by_url = berichtet
    mechanik_model, jetzt, t0 = stufe
    _ueb_items = uebersetzung_stufe.berichtete_items(alle_highlights, by_url)
    if len(_ueb_items) < len(alle_highlights):
        log.info(
            "Uebersetzung: %d von %d berichteten Meldungen ohne "
            "zugehoeriges Item (Dubletten oder umgeschriebene Adresse)",
            len(alle_highlights) - len(_ueb_items),
            len(alle_highlights),
        )
    _ueb_budget = uebersetzung_stufe.budget(cfg.settings, takt.stoppuhr() - t0)
    if _ueb_budget is None:
        if cfg.settings.get("uebersetzung_enabled", True):
            log.warning(
                "Uebersetzung uebersprungen: zu wenig Jobzeit uebrig. "
                "Die Veroeffentlichung geht vor."
            )
        return
    if not llm.llm_available():
        log.info("Uebersetzung uebersprungen: kein Modellzugang.")
        return

    def _lauf() -> None:
        bilanz = uebersetzung_stufe.lauf(
            _ueb_items,
            root,
            cfg.settings,
            mechanik_model,
            frist_sekunden=_ueb_budget,
            heute=jetzt.date(),
        )
        log.info("%s", uebersetzung_stufe.protokollzeile(bilanz))
        run_log["uebersetzung"] = {
            k: (dict(v) if isinstance(v, Counter) else v) for k, v in bilanz.items()
        }

    def _ausfall(exc: Exception) -> None:
        log.error("Uebersetzung uebersprungen: %s: %s", type(exc).__name__, exc)

    takt.abgesichert(_lauf, _ausfall)


def _protokolliere_kosten(kosten: dict) -> None:
    modelle = kosten.get("modelle") or {}
    log.info(
        "Kosten: %.4f $ ueber %d Aufruf(e) in %d Modell(en)%s",
        kosten.get("summe_usd", 0.0),
        sum(m["aufrufe"] for m in modelle.values()),
        len(modelle),
        f" - ohne Preiszeile: {', '.join(kosten['ohne_preis'])}"
        if kosten.get("ohne_preis")
        else "",
    )
    for name, m in modelle.items():
        log.info(
            "Kosten %-32s %5d Aufrufe, %9d ein / %9d aus -> %s",
            name,
            m["aufrufe"],
            m["prompt_tokens"],
            m["completion_tokens"],
            "?" if m.get("usd") is None else f"{m['usd']:.4f} $",
        )
    if kosten.get("budget_ueberschritten"):
        log.warning(
            "Kosten: WARNSCHWELLE UEBERSCHRITTEN - %.4f $ gegen "
            "%.2f $ (llm_budget_usd). Der Lauf wurde nicht "
            "beschnitten; die Schwelle gehoert nachkalibriert oder "
            "der Umfang gesenkt.",
            kosten.get("summe_usd", 0.0),
            kosten["budget_usd"],
        )
