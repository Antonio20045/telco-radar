"""Editor agent: synthesizes regional analyses into one executive report.

Gets the list of previously reported topics as "do not repeat" memory.
If no LLM is available, build_digest() produces a deterministic raw digest
so the pipeline always delivers something useful.
"""
from __future__ import annotations

import json
import logging
from collections import defaultdict
from datetime import date

from ..models import Item
from .llm import complete

log = logging.getLogger(__name__)


class EditorialBriefingError(RuntimeError):
    """Raised when the editor output is not a publishable weekly briefing."""

EDITOR_SYSTEM = """\
You are the chief editor of "Telco Radar", Vodafone Group's weekly global
competitive-intelligence briefing. Vodafone is a telecommunications operator
(mobile, broadband, fixed-mobile convergence, B2B/IoT) in Europe and Africa.
The point of this briefing is simple: see what competitors around the world
did this week, and decide what Vodafone should learn or copy from it.

You receive the assessments of your regional analyst team (JSON) plus a list
of topics ALREADY covered in previous editions.

Write the briefing in {language} as clean Markdown (no top-level H1; start
with H2 sections). Your readers are Vodafone managers WITHOUT a technical or
AI background: write plainly, spell out abbreviations on first use, and always
make clear why something matters for Vodafone. Direct, factual sentences.
No filler, no marketing phrases, no "in der heutigen schnelllebigen Welt".

Structure exactly:

## Auf einen Blick
Exactly 3 bullet points, one sentence each: the three things a manager with
30 seconds must take away this week.

## Das Wichtigste
4-6 sentences: the most important competitor developments worldwide this week
and the overall picture they form. Name operators and concrete moves.

## Die wichtigsten Signale
The 6-10 most relevant items across all regions (relevance 5 first, then 4).
Per item:
**Operator - Titel** (Kategorie, Dringlichkeit X/5)
2-3 sentences of detail (what happened, with numbers/prices/dates when given).
"Fuer Vodafone:" one sentence on what Vodafone could do or learn from it.
Source as [Quelle](url).

## <one H2 section per region that has highlights, using the region name>
2-3 sentence regional summary, then the remaining items compact
(1-2 sentences each, always with [Quelle](url)).

## Muster der Woche
2-4 cross-regional patterns in this week's data (e.g. "mehrere Betreiber
buendeln KI-Assistenten in Consumer-Tarife"). Reference the supporting
operators by name.

## Empfehlungen fuer Vodafone
3-6 concrete, prioritized recommendations that follow from THIS week's
signals. Number them. Per recommendation: one sentence what to do, one
sentence why now and which competitor move triggers it.

Rules:
- NEVER re-report a topic from the "already covered" list unless there is a
  genuinely NEW development - then frame it explicitly as "Update zu ...".
- No invented facts, no padding. If a region has nothing relevant, omit it.
- Every factual claim that has a source must carry its [Quelle](url).
- Keep the whole briefing under ~1900 words.

After the Markdown, output the line ===TOPICS=== followed by a JSON array of
short topic strings (operator + subject) for every item you covered, so the
system can remember them and never repeat them.
"""


def synthesize(regional: dict[str, dict], already_covered: list[str],
               model: str, language: str = "Deutsch") -> tuple[str, list[str]]:
    """Run the editor. Returns (markdown_report, covered_topics)."""
    # strip internal telemetry before handing the analyses to the editor
    clean = {
        rn: {k: v for k, v in r.items() if not k.startswith("_")}
        for rn, r in regional.items()
    }
    user = json.dumps(
        {
            "regional_analyses": clean,
            "already_covered_topics": already_covered[-300:],
        },
        ensure_ascii=False,
    )
    raw = complete(EDITOR_SYSTEM.format(language=language), user,
                   model=model, max_tokens=5000)

    topics: list[str] = []
    markdown = raw
    if "===TOPICS===" in raw:
        markdown, _, tail = raw.partition("===TOPICS===")
        try:
            parsed = json.loads(tail.strip().strip("`"))
            if isinstance(parsed, list):
                topics = [str(t) for t in parsed]
        except json.JSONDecodeError:
            log.warning("Editor topic list unparseable - continuing without")
    markdown = markdown.strip()
    validate_editorial_briefing(markdown)
    return markdown, topics


def validate_editorial_briefing(markdown: str) -> None:
    """Reject a raw source list before it can replace the public report.

    A technical outage at the free model provider must leave the last good
    briefing online, not turn the homepage into a list of collected links.
    """
    headings = {
        line.strip().lower()
        .replace("ä", "ae").replace("ö", "oe").replace("ü", "ue")
        for line in markdown.splitlines()
        if line.strip().startswith("## ")
    }
    required = {
        "## auf einen blick",
        "## das wichtigste",
        "## die wichtigsten signale",
        "## muster der woche",
        "## empfehlungen fuer vodafone",
    }
    missing = required - headings
    if missing or "## wochenueberblick" in headings:
        detail = ", ".join(sorted(missing)) or "Roh-Digest erkannt"
        raise EditorialBriefingError(
            f"Editor output is not a publishable weekly briefing ({detail})."
        )


def build_digest(items_by_region: dict[str, list[Item]],
                 region_names: dict[str, str],
                 llm_was_available: bool = False) -> tuple[str, list[str]]:
    """No-LLM fallback: deterministic digest of all new items."""
    if llm_was_available:
        lines = ["## Wochenueberblick", ""]
    else:
        lines = [
            "## Roh-Digest (ohne KI-Analyse)",
            "",
            "_`ANTHROPIC_API_KEY` ist nicht gesetzt - dies ist die ungefilterte "
            "Liste aller NEUEN Meldungen. Mit API-Key liefert Telco Radar "
            "analysierte Briefings mit Dringlichkeitsbewertung und "
            "Handlungsempfehlungen._",
            "",
        ]
    topics: list[str] = []
    for region_key in sorted(items_by_region,
                             key=lambda k: -len(items_by_region[k])):
        items = items_by_region[region_key]
        if not items:
            continue
        lines.append(f"### {region_names.get(region_key, region_key)} "
                     f"({len(items)} neu)")
        lines.append("")
        by_op: dict[str, list[Item]] = defaultdict(list)
        for item in items:
            by_op[item.operator or item.source_name].append(item)
        for op in sorted(by_op):
            for item in by_op[op][:10]:
                dt = f" ({item.published.date().isoformat()})" if item.published else ""
                lines.append(f"- **{op}**: [{item.title}]({item.url}){dt}")
                topics.append(f"{op}: {item.title[:120]}")
            if len(by_op[op]) > 10:
                lines.append(f"  - _... und {len(by_op[op]) - 10} weitere_")
        lines.append("")
    if not topics:
        lines.append("_Keine neuen Meldungen in diesem Zeitraum._")
    return "\n".join(lines), topics


def report_header(report_date: date, stats: dict) -> str:
    return (
        f"# Telco Radar - {report_date.isoformat()}\n\n"
        f"_Quellen abgefragt: {stats.get('sources_ok', 0)} ok / "
        f"{stats.get('sources_failed', 0)} fehlgeschlagen · "
        f"Meldungen gesammelt: {stats.get('collected', 0)} · "
        f"davon neu: {stats.get('new', 0)}_\n\n"
    )
