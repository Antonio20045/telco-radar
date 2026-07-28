"""Redaktion fuer den woechentlichen Promo-Uebersicht-Bericht (Deutschland).

Fasst die aktuell aktiven Tarif- und Kampagnenangebote deutscher Telcos aus
der kuratierten Promo-DB (data/state/promo_db.json) zu einem kurzen,
verstaendlichen Ueberblick zusammen - Bloomberg-Stil wie der Hauptbericht,
aber bewusst kein Preis-Ticker: der Bericht ordnet Marktbewegung ein statt
jede Zahl zu wiederholen, und verweist fuer den aktuellen Stand IMMER auf die
Original-Aktionsseite statt einen Preis als dauerhaft gueltig zu behaupten
(Stale-Preis-Risiko, siehe claude/promo-uebersicht-konzept.md Risiko d).
"""
from __future__ import annotations

import json
import logging
import re

from .llm import complete

log = logging.getLogger(__name__)


class PromoBriefingError(RuntimeError):
    """Raised when the promo editor returns unusable Markdown."""


PROMO_EDITOR_SYSTEM = """\
Du bist Redakteur fuer einen deutschsprachigen woechentlichen Ueberblick ueber
aktuelle Tarif- und Kampagnenaktionen deutscher Mobilfunkanbieter -
Netzbetreiber UND ihre Discount-/Zweitmarken (Festnetz, Kabel und Glasfaser
werden hier bewusst nicht beobachtet).

Die Leser sind Vodafone-Manager ohne technischen Hintergrund. Ordne ein, was
gerade im deutschen Markt an Rabatt-, Bundle- und Wechsleraktionen laeuft -
gruppiere nach Themen oder Mustern (z. B. "Rabattschlacht bei den
Discountern", "Datenvolumen-Boni", "Wechslerpraemien"), nicht nach einzelnen
SKUs oder Anbietern der Reihe nach.

Nenne KEINE exakten Preise oder Rabattbetraege als dauerhaft gueltig - jede
Aktion aendert sich schnell. Beschreibe die Mechanik ("bietet befristet
zusaetzliches Datenvolumen", "senkt den Einstiegspreis fuer Neukunden",
"zahlt eine Wechslerpraemie") und verweise fuer die aktuelle Zahl auf die
Quelle. Erfinde nichts, was nicht in den gelieferten Daten steht.

Ordne kurz und neutral ein, warum eine Entwicklung fuer den deutschen Markt
bemerkenswert ist (z. B. weil mehrere Anbieter gleichzeitig nachziehen, oder
weil ein Discounter besonders aggressiv wird). Das ist Marktbeobachtung,
keine Handlungsempfehlung: keine Formulierungen wie "Vodafone sollte",
"Vodafone koennte" oder "Empfehlung".

Antworte ausschliesslich mit sauberem Markdown, ohne H1 und ohne Vorwort.
Verwende exakt diese H2-Ueberschriften:

## Was diese Woche auffaellt
3 bis 5 zusammenhaengende Absaetze. Beginne sofort mit den Anbietern und
Aktionen aus den Daten, gruppiert nach Themen/Mustern. Nenne Anbieter beim
Namen und verknuepfe jede konkrete Aussage mit der passenden Quelle.

## Quellenbasis
Liste die verwendeten Aktionen als [Anbieter – Kurzbezeichnung](URL), mit
Stand-Datum.

Regeln:
- Jede Aussage ueber einen Anbieter braucht einen Link auf eine exakte URL
  aus den gelieferten Daten.
- Keine erfundenen Preise, Rabattbetraege oder Enddaten.
- Keine Handlungsempfehlung fuer Vodafone ("Vodafone sollte/koennte").
- Manche Eintraege tragen ein Feld "wichtigkeit" (0-100). Nutze es nur als
  Hinweis darauf, womit du anfaengst - nenne die Zahl NIE im Text.
- Maximal etwa 900 Woerter.
"""

_REQUIRED_HEADINGS = ("## was diese woche auffaellt", "## quellenbasis")
_FORBIDDEN_PHRASES = ("vodafone sollte", "vodafone könnte", "vodafone koennte",
                      "vodafone muss", "empfehlung:")


def _heading_key(line: str) -> str:
    return (line.strip().lower().replace("ä", "ae").replace("ö", "oe")
            .replace("ü", "ue").replace("ß", "ss"))


def _without_links(markdown: str) -> str:
    return re.sub(r"\[[^\]]*\]\([^)]*\)", "", markdown).lower()


def validate_briefing(markdown: str) -> None:
    """Reject an answer with the wrong structure, missing source links, or
    prescriptive Vodafone advice."""
    headings = {_heading_key(l) for l in markdown.splitlines()
                if l.strip().startswith("## ")}
    missing = set(_REQUIRED_HEADINGS) - headings
    if missing:
        raise PromoBriefingError(
            "Promo-Bericht unvollstaendig: " + ", ".join(sorted(missing)))
    if "[" not in markdown or "](" not in markdown:
        raise PromoBriefingError("Promo-Bericht enthaelt keine Quellenlinks")
    plain = _without_links(markdown)
    if any(p in plain for p in _FORBIDDEN_PHRASES):
        raise PromoBriefingError(
            "Promo-Bericht enthaelt eine Handlungsempfehlung")


def _payload(entries: list[dict]) -> str:
    rows = []
    for e in entries:
        row = {
            "anbieter": e.get("brand") or "",
            "titel": e.get("headline") or "",
            "beschreibung": e.get("description") or "",
            "gueltig_bis": e.get("valid_until") or "",
            "quelle": e.get("url") or "",
            "seit": e.get("first_seen") or "",
            "geprueft": e.get("last_verified") or "",
        }
        # Wichtigkeits-Score aus analyze/promo_ranker.py, sofern schon
        # bewertet. Nur ein Hinweis fuer die Gewichtung im Text - der Editor
        # soll die Zahl selbst NICHT nennen (die Rangfolge steht sichtbar
        # oben auf der Seite, im Fliesstext waere sie nur Ballast).
        if e.get("score") is not None:
            row["wichtigkeit"] = e["score"]
        rows.append(row)
    return json.dumps(rows, ensure_ascii=False)


def synthesize(entries: list[dict], model: str, language: str = "Deutsch") -> str:
    """Run the dedicated promo editor and validate its Markdown."""
    active = [e for e in entries if e.get("status") == "aktiv"]
    if not active:
        return build_digest(entries)
    # Wichtigste zuerst in den Prompt: bei ~70 aktiven Aktionen und begrenztem
    # Kontext entscheidet die Reihenfolge mit darueber, worueber der Text
    # ueberhaupt schreibt. Unbewertete Eintraege bleiben hinten, statt sie zu
    # verwerfen - sie sind nicht unwichtig, nur noch nicht beurteilt.
    active = sorted(active, key=lambda e: (e.get("score") is not None,
                                           e.get("score") or 0), reverse=True)
    raw = complete(
        PROMO_EDITOR_SYSTEM + f"\nBerichtssprache: {language}.",
        _payload(active), model=model, max_tokens=3200)
    markdown = raw.strip()
    validate_briefing(markdown)
    return markdown


def _source_link(e: dict) -> str:
    brand = e.get("brand") or "Anbieter"
    label = e.get("headline") or "Angebot"
    return f"[{brand} – {label}]({e.get('url') or ''})"


def build_digest(entries: list[dict]) -> str:
    """Build a concrete summary without an LLM (rule-based fallback)."""
    active = [e for e in entries if e.get("url") and e.get("headline")
              and e.get("status") == "aktiv"]
    ordered = sorted(
        active, key=lambda e: (e.get("last_verified") or "", e.get("first_seen") or ""),
        reverse=True)

    lines = ["## Was diese Woche auffaellt", ""]
    if not ordered:
        lines.append(
            "Im aktuellen Beobachtungszeitraum liegt keine belegte aktive "
            "Aktion vor.")
    else:
        by_brand: dict[str, list[dict]] = {}
        for e in ordered:
            by_brand.setdefault(e["brand"], []).append(e)
        for brand, items in by_brand.items():
            bits = "; ".join(f"{i['headline']} {_source_link(i)}" for i in items[:4])
            lines.extend([f"**{brand}** {bits}.", ""])

    lines += ["## Quellenbasis", ""]
    for e in ordered[:20]:
        suffix = f" · gueltig bis {e['valid_until']}" if e.get("valid_until") else ""
        lines.append(f"- {_source_link(e)}{suffix}")
    if not ordered:
        lines.append("- Noch keine belegte aktive Aktion vorhanden.")
    return "\n".join(lines).strip() + "\n"
