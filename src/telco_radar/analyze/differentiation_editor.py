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

## Das Wichtigste
Ein klarer Einstieg mit 2 bis 4 kurzen Absaetzen. Verdichte die auffaelligsten
Entwicklungen im aktuellen Beobachtungszeitraum und verlinke jede konkrete
Aussage ueber einen Betreiber direkt mit der passenden Quelle.

## Beispiele aus dem Markt
Waehle 6 bis 10 besonders anschauliche Beispiele aus unterschiedlichen
Themenfeldern und Regionen. Nutze pro Beispiel eine H3-Ueberschrift mit
Betreiber und Thema, dann 1 bis 3 Saetze: Was wurde konkret angeboten,
gestartet oder integriert und warum ist es ein interessantes Beispiel fuer
Differenzierung? Jede faktische Aussage bekommt einen passenden Quellenlink.

## Welche Muster dahinter liegen
Beschreibe 3 bis 5 neutrale, globale Muster, die sich aus den Beispielen
ergeben. Zum Beispiel: Premium-Dienste werden Teil des Tariferlebnisses,
Schutz wird zum Markenversprechen, oder die Telko-App wird zum Zugang zu
mehreren Alltagsdiensten. Belege die Muster mit konkreten Beispielen und
Quellenlinks. Keine Bewertung und keine Empfehlung.

## Quellenbasis
Liste die wichtigsten verwendeten Beispiele als
[Betreiber – Kurzbezeichnung](URL), mit Region und, falls vorhanden, Datum.

Regeln:
- Jede konkrete Aussage ueber einen Betreiber muss einen Link auf eine
  exakte URL aus den gelieferten Daten tragen.
- Keine Vodafone-Empfehlungen, keine Handlungsaufforderungen, kein
  „Fuer Vodafone“, kein „Vodafone sollte“ und kein „Vodafone koennte“.
- Nicht nur Links aufzählen: Die Beispiele muessen in einem lesbaren Bericht
  erklaert und miteinander in Beziehung gesetzt werden.
- Maximal etwa 1.200 Woerter.
"""


_REQUIRED_HEADINGS = (
    "## das wichtigste",
    "## beispiele aus dem markt",
    "## welche muster dahinter liegen",
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
    """Build a neutral, source-linked report without an LLM."""
    entries = [e for e in entries if e.get("url") and e.get("what")]
    by_theme: dict[str, list[dict]] = {}
    for entry in entries:
        by_theme.setdefault(entry.get("theme") or "_", []).append(entry)
    ordered = sorted(entries, key=lambda e: (e.get("last_verified") or "",
                                             e.get("first_seen") or ""),
                     reverse=True)
    # One representative per theme keeps the fallback varied instead of
    # repeating the same category four times at the top.
    representatives: list[dict] = []
    seen_themes: set[str] = set()
    for entry in ordered:
        theme = entry.get("theme") or "_"
        if theme not in seen_themes:
            representatives.append(entry)
            seen_themes.add(theme)

    lines = ["## Das Wichtigste", ""]
    if representatives:
        first = representatives[0]
        lines.append(
            f"Der aktuelle Überblick zeigt, wie unterschiedlich Telkos ihr "
            f"Leistungsversprechen erweitern. Ein anschauliches Beispiel: "
            f"{first.get('what', '').rstrip('.')} {_source_link(first)}.")
        if len(representatives) > 1:
            second = representatives[1]
            lines.append(
                f"Daneben steht ein anderer Ansatz: {second.get('what', '').rstrip('.')} "
                f"{_source_link(second)}.")
        lines.append(
            "Gemeinsam ist diesen Beispielen, dass die Differenzierung an einem "
            "konkreten Kundenerlebnis sichtbar wird – als Dienst, Programm, "
            "Versprechen oder Zugang zu einem weiteren Ökosystem.")
    else:
        lines.append("Der aktuelle Beobachtungszeitraum enthält noch kein belegtes Beispiel.")

    lines += ["", "## Beispiele aus dem Markt", ""]
    for entry in representatives[:10]:
        theme = theme_labels.get(entry.get("theme"), entry.get("theme") or "Differenzierung")
        operator = entry.get("operator") or "Betreiber"
        lines.append(f"### {operator}: {theme}")
        lines.append(
            f"{entry.get('what', '').rstrip('.')} {_source_link(entry)}"
            f"{_date_suffix(entry)}.")
        lines.append("")

    lines += ["## Welche Muster dahinter liegen", ""]
    group_defs = (
        ("Dienste werden Teil des Tariferlebnisses", ("ki", "entertainment", "cloud", "gaming")),
        ("Vertrauen und Schutz werden als Leistung sichtbar", ("garantie", "security", "health")),
        ("Das Gerät bleibt über Programme und Zubehör im Ökosystem", ("geraete",)),
        ("Die Telko-App öffnet den Zugang zu weiteren Alltagsdiensten", ("fintech", "superapp", "smarthome", "loyalty")),
    )
    added_pattern = False
    for label, keys in group_defs:
        sample = next((e for e in ordered if e.get("theme") in keys), None)
        if not sample:
            continue
        themes = ", ".join(theme_labels.get(k, k) for k in keys
                            if k in by_theme)
        lines.append(
            f"- **{label}:** Sichtbar in {themes}. Beispiel: "
            f"{sample.get('what', '').rstrip('.')} {_source_link(sample)}.")
        added_pattern = True
    if not added_pattern:
        lines.append("- Weitere Muster werden sichtbar, sobald neue Beispiele bestätigt sind.")

    lines += ["", "## Quellenbasis", ""]
    for entry in ordered[:12]:
        lines.append(f"- {_source_link(entry)}{_date_suffix(entry)}")
    if not ordered:
        lines.append("- Noch keine belegte Quelle vorhanden.")
    return "\n".join(lines).strip() + "\n"
