"""Redaktion fuer den globalen Differenzierungsbericht.

Der Bericht beschreibt konkrete Angebote und Projekte von Telkos jenseits von
Netzausbau, Tarifen und Preisen. Er ist keine Vodafone-Empfehlung und spricht
nicht ueber interne Entscheidungen, sondern ordnet beobachtete Beispiele
neutral und quellengebunden ein.
"""
from __future__ import annotations

import json
import logging
import re

from .llm import complete

log = logging.getLogger(__name__)


class DifferentiationBriefingError(RuntimeError):
    """Raised when the differentiation editor returns unusable Markdown."""


DIFFERENTIATION_EDITOR_SYSTEM = """\
Du bist der Spezial-Redakteur fuer einen deutschsprachigen globalen
Differenzierungsbericht ueber Telekommunikationsunternehmen.

Der Bericht beantwortet eine einfache Frage: Welche konkreten Angebote,
Programme und Projekte nutzen Telkos weltweit, um sich jenseits von
Netzausbau, 5G, Tarifen und Preisen abzuheben? Interessant sind zum Beispiel
Premium-KI als Kundenvorteil, Garantien und Service-Versprechen,
Geraeteprogramme, Streaming, Betrugsschutz, Cloud, Fintech, Super-Apps,
Loyalty-Programme, Smart Home und Health-Angebote.

Die Leser wollen globale Marktbeobachtung. Schreibe deshalb nicht ueber eine
interne Vodafone-Strategie und gib keinerlei Empfehlungen, Handlungstipps
oder naechste Schritte fuer Vodafone. Verwende auch keine Formulierungen wie
„Vodafone sollte“, „Vodafone koennte“, „Fuer Vodafone“ oder „Empfehlung“.

Nutze ausschliesslich die gelieferten, belegten Eintraege. Erfinde keine
Zahlen, Zeitpunkte, Partnerschaften oder Wirkungen. Wenn ein Datum fehlt,
lasse es weg. Erklaere Fachbegriffe kurz, wenn sie fuer das Verstaendnis
noetig sind. Schreibe anschaulich: „bietet Kunden“, „buendelt“, „integriert“,
„garantiert“, „schuetzt“ und „macht ... zum Bestandteil des Angebots“.
Verwende nicht den abstrakten Begriff „Sammlung“ und nenne keine Anzahl von
Moves, Eintraegen, Kategorien oder Quellen als Selbstzweck.

Antworte ausschliesslich mit sauberem Markdown, ohne H1 und ohne Vorwort.
Verwende exakt diese H2-Ueberschriften:

## Konkrete Entwicklungen
Schreibe einen direkten Bericht aus 4 bis 6 zusammenhaengenden Absaetzen.
Beginne sofort mit konkreten Betreibern, Angeboten und Projekten aus den Daten.
Erklaere nicht, was „Differenzierung“ bedeutet, und schreibe keine allgemeine
Einleitung ueber Marktverschiebungen oder Kundenerlebnisse. Jeder Absatz soll
mehrere Artikel aus einem Themenfeld zusammenfassen: Was bietet welcher
Betreiber konkret an, in welcher Region und mit welchem Partner oder Dienst?
Nenne die Betreiber beim Namen und verknuepfe jede konkrete Aussage direkt mit
der passenden Quelle. Die Absaetze duerfen mit einem kurzen fettgedruckten
Themenwort beginnen, sollen aber keine H3-Ueberschriften pro Betreiber und
keine Bullet-Liste sein.

## Quellenbasis
Liste die wichtigsten verwendeten Beispiele als
[Betreiber – Kurzbezeichnung](URL), mit Region und, falls vorhanden, Datum.

Regeln:
- Jede konkrete Aussage ueber einen Betreiber muss einen Link auf eine
  exakte URL aus den gelieferten Daten tragen.
- Keine Vodafone-Empfehlungen, keine Handlungsaufforderungen, kein
  „Fuer Vodafone“, kein „Vodafone sollte“ und kein „Vodafone koennte“.
- Der Bericht soll die gelieferten Artikel konkret zusammenfassen, nicht das
  Thema erklaeren und keine abstrakten Muster ableiten.
- Keine H3-Ueberschriften und keine Aufzaehlung von Einzelartikeln im Bericht.
- Bulletpoints sind nur in der Quellenbasis erlaubt.
- Maximal etwa 1.200 Woerter.
"""


_REQUIRED_HEADINGS = (
    "## konkrete entwicklungen",
    "## quellenbasis",
)
_FORBIDDEN_EDITORIAL_PHRASES = (
    "fuer vodafone", "für vodafone", "vodafone sollte", "vodafone könnte",
    "vodafone koennte", "vodafone muss", "empfehlung", "handlungsaufforderung",
)


def _heading_key(line: str) -> str:
    return (line.strip().lower().replace("ä", "ae").replace("ö", "oe")
            .replace("ü", "ue").replace("ß", "ss"))


def _without_links(markdown: str) -> str:
    """Remove Markdown links before checking editorial wording."""
    return re.sub(r"\[[^\]]*\]\([^)]*\)", "", markdown).lower()


def validate_briefing(markdown: str) -> None:
    """Reject an answer with the wrong structure or Vodafone advice."""
    headings = {_heading_key(line) for line in markdown.splitlines()
                if line.strip().startswith("## ")}
    missing = set(_REQUIRED_HEADINGS) - headings
    if missing:
        raise DifferentiationBriefingError(
            "Differenzierungsbericht unvollstaendig: " + ", ".join(sorted(missing)))
    if "[" not in markdown or "](" not in markdown:
        raise DifferentiationBriefingError(
            "Differenzierungsbericht enthaelt keine Quellenlinks")
    plain = _without_links(markdown)
    if any(phrase in plain for phrase in _FORBIDDEN_EDITORIAL_PHRASES):
        raise DifferentiationBriefingError(
            "Differenzierungsbericht enthaelt eine Vodafone-Empfehlung")


def _payload(entries: list[dict], theme_labels: dict[str, str]) -> str:
    rows = []
    for e in entries:
        rows.append({
            "thema": theme_labels.get(e.get("theme"), e.get("theme") or ""),
            "betreiber": e.get("operator") or "",
            "region": e.get("region") or "",
            "konkretes_beispiel": e.get("what") or "",
            "quelle": e.get("url") or "",
            "quellendom": e.get("source") or "",
            "datum": e.get("date") or "",
            "zuletzt_geprueft": e.get("last_verified") or "",
        })
    return json.dumps(rows, ensure_ascii=False)


def synthesize(entries: list[dict], theme_labels: dict[str, str], model: str,
               language: str = "Deutsch") -> str:
    """Run the dedicated market-observation editor and validate its Markdown."""
    if not entries:
        return build_digest(entries, theme_labels)
    raw = complete(
        DIFFERENTIATION_EDITOR_SYSTEM + f"\nBerichtssprache: {language}.",
        _payload(entries, theme_labels), model=model, max_tokens=4200)
    markdown = raw.strip()
    validate_briefing(markdown)
    return markdown


def _source_link(entry: dict) -> str:
    operator = entry.get("operator") or entry.get("source") or "Betreiber"
    url = entry.get("url") or ""
    label = entry.get("source") or "Quelle"
    return f"[{operator} – {label}]({url})"


def _date_suffix(entry: dict) -> str:
    date = entry.get("date")
    region = entry.get("region")
    bits = [str(x) for x in (region, date) if x]
    return " · " + " · ".join(bits) if bits else ""


def build_digest(entries: list[dict], theme_labels: dict[str, str]) -> str:
    """Build a concrete article summary without an LLM."""
    entries = [e for e in entries if e.get("url") and e.get("what")]
    ordered = sorted(entries, key=lambda e: (e.get("last_verified") or "",
                                             e.get("first_seen") or ""),
                     reverse=True)

    def move_sentence(entry: dict) -> str:
        operator = entry.get("operator") or "Der Betreiber"
        what = re.sub(r"^\s*" + re.escape(operator)
                      + r"(?:\s*\([^)]*\))?\s*:?\s*", "",
                      str(entry.get("what") or ""), flags=re.IGNORECASE)
        if not what:
            what = str(entry.get("what") or "")
        if what[:1].islower():
            text = f"{operator} {what}"
        else:
            text = f"{operator}: {what}"
        return f"{text.rstrip('.')} {_source_link(entry)}"

    def paragraph(lead: str, items: list[dict]) -> str:
        if not items:
            return ""
        return f"**{lead}** " + "; ".join(move_sentence(e) for e in items) + "."

    groups = (
        ("KI und digitale Dienste", ("ki",)),
        ("Streaming, Cloud und Gaming", ("entertainment", "cloud", "gaming")),
        ("Garantien, Schutz und Gesundheit", ("garantie", "security", "health")),
        ("Geräteprogramme, Vorteile und Smart Home", ("geraete", "loyalty", "smarthome")),
        ("Fintech und Super-Apps", ("fintech", "superapp")),
    )
    lines = ["## Konkrete Entwicklungen", ""]
    used = set()
    for lead, themes in groups:
        items = [e for e in ordered if e.get("theme") in themes]
        used.update(id(e) for e in items)
        text = paragraph(lead, items)
        if text:
            lines.extend([text, ""])
    remaining = [e for e in ordered if id(e) not in used]
    if remaining:
        lines.extend([paragraph("Weitere konkrete Angebote", remaining), ""])
    if not ordered:
        lines.append("Im aktuellen Beobachtungszeitraum liegt noch kein belegtes Beispiel vor.")

    lines += ["## Quellenbasis", ""]
    for entry in ordered[:12]:
        lines.append(f"- {_source_link(entry)}{_date_suffix(entry)}")
    if not ordered:
        lines.append("- Noch keine belegte Quelle vorhanden.")
    return "\n".join(lines).strip() + "\n"
