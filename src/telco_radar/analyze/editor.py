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

EDITOR_SYSTEM = """\
You are the chief editor of "Telco Radar", Vodafone's weekly global
competitive-intelligence briefing. You receive the assessments of your
regional analyst team (JSON) plus a list of topics that were ALREADY covered
in previous editions.

Write the briefing in {language} as clean Markdown (no top-level H1; start
with H2 sections). Your readers are managers WITHOUT technical or AI
background - write clearly, spell out abbreviations on first use, and always
say why something matters. Structure:

## Für Eilige
Exactly 3 bullet points, one sentence each: what someone with 30 seconds
must know this week.

## Executive Summary
4-6 sentences: the most important developments worldwide this week and the
picture they add up to.

## Top-Signale
The 6-10 most relevant items across all regions (relevance 4-5 first) as a
list. Per item: **Operator – Titel** (Kategorie, Relevanz X/5), then 2-3
sentences of detail (what exactly happened, numbers/prices/dates if given),
one line "Warum relevant:", and the source link as [Quelle](url).

## <one section per region that has highlights>
2-3 sentences regional summary, then its remaining items in a compact format
(1-2 sentences each, always with [Quelle](url)).

## Trends & Muster
2-4 cross-regional patterns you see in this week's data (e.g. "several
operators bundle AI assistants into consumer tariffs"). Reference the
supporting items by operator name.

## Handlungsempfehlungen für Vodafone
3-6 concrete, prioritized recommendations derived from this week's signals.
Number them. Per recommendation: one sentence what to do, one sentence why now.

Rules:
- NEVER re-report a topic from the "already covered" list unless there is a
  genuinely NEW development - then explicitly frame the update as new
  ("Update zu ...").
- No invented facts, no filler. If a region has nothing relevant, omit it.
- Keep the whole briefing under ~1800 words.

After the Markdown, output the line ===TOPICS=== followed by a JSON array of
short topic strings (operator + subject) for every item you covered, so the
system can remember them.
"""


def synthesize(regional: dict[str, dict], already_covered: list[str],
               model: str, language: str = "Deutsch") -> tuple[str, list[str]]:
    """Run the editor. Returns (markdown_report, covered_topics)."""
    user = json.dumps(
        {
            "regional_analyses": regional,
            "already_covered_topics": already_covered[-300:],
        },
        ensure_ascii=False,
    )
    raw = complete(EDITOR_SYSTEM.format(language=language), user,
                   model=model, max_tokens=20000)

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
    return markdown.strip(), topics


def build_digest(items_by_region: dict[str, list[Item]],
                 region_names: dict[str, str],
                 llm_was_available: bool = False) -> tuple[str, list[str]]:
    """No-LLM fallback: deterministic digest of all new items."""
    if llm_was_available:
        lines = ["## Wochenüberblick", ""]
    else:
        lines = [
            "## Roh-Digest (ohne KI-Analyse)",
            "",
            "_`ANTHROPIC_API_KEY` ist nicht gesetzt - dies ist die ungefilterte "
            "Liste aller NEUEN Items. Mit API-Key liefert Telco Radar analysierte "
            "Briefings mit Relevanzbewertung und Handlungsempfehlungen._",
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
        lines.append("_Keine neuen Items in diesem Zeitraum._")
    return "\n".join(lines), topics


def report_header(report_date: date, stats: dict) -> str:
    return (
        f"# Telco Radar - {report_date.isoformat()}\n\n"
        f"_Quellen abgefragt: {stats.get('sources_ok', 0)} ok / "
        f"{stats.get('sources_failed', 0)} fehlgeschlagen · "
        f"Items gesammelt: {stats.get('collected', 0)} · "
        f"davon neu: {stats.get('new', 0)}_\n\n"
    )
