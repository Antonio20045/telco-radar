"""Editor agent: synthesizes regional analyses into one global market report.

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
from .llm import complete, llm_available

log = logging.getLogger(__name__)


class EditorialBriefingError(RuntimeError):
    """Raised when the editor output is not a publishable weekly briefing."""

EDITOR_SYSTEM = """\
You are the chief editor of "Telco Radar", a weekly global
competitive-intelligence briefing. The point of this briefing is simple:
show what telecommunications companies around the world did this week and
which patterns become visible across regions and operators.

You receive the assessments of your regional analyst team (JSON) plus a list
of topics ALREADY covered in previous editions.

Write the briefing in {language} as clean Markdown (no top-level H1; start
with H2 sections). Your readers are managers WITHOUT a technical or AI
background: write plainly, spell out abbreviations on first use, and explain
the concrete customer offer or project. This is market observation, not a
recommendation memo. Direct, factual sentences.
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
Source as [Quelle](url).

## <one H2 section per region that has highlights, using the region name>
2-3 sentence regional summary, then the remaining items compact
(1-2 sentences each, always with [Quelle](url)).

## Muster der Woche
2-4 cross-regional patterns in this week's data (e.g. "mehrere Betreiber
buendeln KI-Assistenten in Consumer-Tarife"). Reference the supporting
operators by name.

Rules:
- NEVER re-report a topic from the "already covered" list unless there is a
  genuinely NEW development - then frame it explicitly as "Update zu ...".
- No invented facts, no padding. If a region has nothing relevant, omit it.
- Every factual claim that has a source must carry its [Quelle](url).
- Do not write recommendations, action items or "Fuer Vodafone" sections.
- Keep the whole briefing under ~1900 words.

After the Markdown, output the line ===TOPICS=== followed by a JSON array of
short topic strings (operator + subject) for every item you covered, so the
system can remember them and never repeat them.
"""


# The editor sees EVERY assessed item by default (0 = no limit). A weekly
# briefing that silently skips half the week is not a briefing, and there is
# no second chance: the seen-store marks every new item as known, so whatever
# the editor never sees never comes back.
#
# The cost is input length. Measured against a real analyst run: ~750
# characters per assessed item, so a 362-item week is roughly 265 KB or ~68k
# tokens of editor input. That needs a model with a large context window -
# claude-sonnet-5 (200k) handles it, the deepseek-v4-flash configured for the
# free NVIDIA endpoint does not. If a provider forces a smaller prompt, set
# editor_max_highlights in settings.yaml; the selection below then keeps the
# strongest per region, round-robin, so one busy region cannot crowd out the
# rest - but that is a fallback, not the intended mode.
EDITOR_HIGHLIGHT_BUDGET = 0


def _select_for_editor(clean: dict[str, dict], budget: int) -> tuple[dict, int]:
    """budget <= 0 means: hand over everything, unchanged."""
    """Keep the strongest highlights per region, round-robin across regions.

    Round-robin rather than one global ranking: a single busy region would
    otherwise fill the whole budget and the briefing would lose its point,
    which is showing what happened ACROSS regions.
    """
    ranked = {
        rn: sorted(r.get("highlights") or [],
                   key=lambda h: (h.get("relevance") or 0), reverse=True)
        for rn, r in clean.items()
    }
    total = sum(len(v) for v in ranked.values())
    if budget <= 0 or total <= budget:
        return clean, 0

    kept: dict[str, list] = {rn: [] for rn in ranked}
    picked = 0
    for rank in range(max((len(v) for v in ranked.values()), default=0)):
        for rn, hs in ranked.items():
            if rank < len(hs) and picked < budget:
                kept[rn].append(hs[rank])
                picked += 1
        if picked >= budget:
            break
    out = {rn: {**r, "highlights": kept.get(rn, [])} for rn, r in clean.items()}
    return out, total - picked


def synthesize(regional: dict[str, dict], already_covered: list[str],
               model: str, language: str = "Deutsch",
               highlight_budget: int = EDITOR_HIGHLIGHT_BUDGET) -> tuple[str, list[str]]:
    """Run the editor. Returns (markdown_report, covered_topics)."""
    # strip internal telemetry before handing the analyses to the editor
    clean = {
        rn: {k: v for k, v in r.items() if not k.startswith("_")}
        for rn, r in regional.items()
    }
    clean, omitted = _select_for_editor(clean, highlight_budget)
    if omitted:
        log.info("Editor gets %d highlights, %d weaker ones omitted "
                 "(all remain in the report JSON)", highlight_budget, omitted)
    payload = {
        "regional_analyses": clean,
        "already_covered_topics": already_covered[-300:],
    }
    if omitted:
        payload["note"] = (
            f"{omitted} further assessed items were left out of this payload "
            "because they scored lower on relevance. They are published in the "
            "report data, so do not claim this is everything that happened."
        )
    user = json.dumps(payload, ensure_ascii=False)
    n_highlights = sum(len(r.get("highlights") or []) for r in clean.values())
    # Printed on every run: with no cap the editor prompt grows with the week,
    # and this is the number that decides whether the configured model can
    # still take it (~4 characters per token).
    log.info("Editor prompt: %d highlights, %.0f KB (~%dk tokens), model=%s",
             n_highlights, len(user) / 1024, len(user) // 4000, model)
    system = EDITOR_SYSTEM.format(language=language)
    try:
        return _ein_versuch(system, user, model)
    except EditorialBriefingError as exc:
        # Der Wochenbericht ist das Herzstueck der Seite. Ihn beim ersten
        # Formfehler wegzuwerfen und stattdessen den Roh-Digest zu
        # veroeffentlichen, ist die teuerste moegliche Reaktion - der Inhalt
        # war ja da, nur die Gliederung stimmte nicht. Also einmal gezielt
        # nachfassen, mit den Ueberschriften woertlich im Auftrag.
        log.warning("Editor-Ausgabe abgelehnt (%s) - ein Korrekturversuch", exc)
        return _ein_versuch(system + NACHFASSEN, user, model)


# Wird nur an den zweiten Versuch angehaengt.
NACHFASSEN = """

WICHTIG - der vorherige Versuch wurde verworfen, weil die Gliederung nicht
stimmte. Die Ueberschriften muessen WOERTLICH und als H2 ("## ") vorkommen,
in genau dieser Schreibweise, ohne Nummerierung und ohne Zusaetze:

## Auf einen Blick
## Das Wichtigste
## Die wichtigsten Signale
## Muster der Woche

Beginne die Antwort unmittelbar mit "## Auf einen Blick" - kein Vorwort, kein
Titel, kein Code-Block darum.
"""

# Der Bericht selbst bleibt unter ~1900 Woertern, aber danach folgt noch die
# Themenliste mit einem Eintrag je behandelter Meldung. In einer Woche mit 147
# bewerteten Meldungen ist die allein mehrere tausend Token lang - mit den
# alten 5000 waere die Antwort mitten im Anhang abgerissen.
EDITOR_MAX_TOKENS = 8000


def _ein_versuch(system: str, user: str, model: str) -> tuple[str, list[str]]:
    raw = complete(system, user, model=model, max_tokens=EDITOR_MAX_TOKENS)

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
    # Ein Modell, das die Gliederung sonst richtig hat, packt die Antwort
    # gelegentlich in einen Markdown-Codeblock. Dann beginnt keine Zeile mit
    # "## " und der Bericht faellt aus formalen Gruenden durch.
    if markdown.startswith("```"):
        markdown = markdown.split("\n", 1)[-1]
        if markdown.rstrip().endswith("```"):
            markdown = markdown.rstrip()[:-3].rstrip()
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
    }
    missing = required - headings
    if missing or "## wochenueberblick" in headings:
        detail = ", ".join(sorted(missing)) or "Roh-Digest erkannt"
        # Was der Editor STATTDESSEN geliefert hat, gehoert in die Meldung.
        # Im Lauf vom 04.08.2026 fehlten alle vier Pflicht-Ueberschriften,
        # auch die erste - damit war aus dem Protokoll nicht zu erkennen, ob
        # das Modell andere Titel waehlte, die Antwort abgeschnitten wurde
        # oder etwas ganz anderes zurueckkam. Ohne diese Zeilen bleibt nur
        # Raten.
        gefunden = ", ".join(sorted(headings)[:8]) or "keine H2-Ueberschrift"
        anfang = " ".join(markdown[:300].split())
        raise EditorialBriefingError(
            f"Editor output is not a publishable weekly briefing ({detail}). "
            f"Gefunden: {gefunden}. Anfang: {anfang!r}"
        )
    lowered = markdown.lower().replace("ä", "ae").replace("ö", "oe").replace("ü", "ue")
    if any(phrase in lowered for phrase in
           ("empfehlungen fuer vodafone", "fuer vodafone:",
            "vodafone sollte", "vodafone koennte")):
        raise EditorialBriefingError("Editor output contains Vodafone recommendations.")


def build_digest(items_by_region: dict[str, list[Item]],
                 region_names: dict[str, str],
                 llm_was_available: bool = False,
                 include_note: bool = True) -> tuple[str, list[str]]:
    """No-LLM fallback: deterministic digest of all new items.

    `include_note` is False when the caller already explains upstream why the
    digest is raw - otherwise the page carries two notes that say the same
    thing in different words.
    """
    if llm_was_available:
        lines = ["## Wochenueberblick", ""]
    elif not include_note:
        lines = ["## Roh-Digest (ohne redaktionelle Verdichtung)", ""]
    elif llm_available():
        # A key IS configured - the provider just did not answer. Claiming a
        # missing key here put a false statement on the public report page.
        lines = [
            "## Roh-Digest (ohne redaktionelle Verdichtung)",
            "",
            "_Der Analyse-Dienst war in diesem Lauf nicht erreichbar. Dies ist "
            "die ungefilterte Liste aller NEUEN Meldungen mit ihren "
            "Originalquellen; die redaktionelle Verdichtung wird im naechsten "
            "Lauf erneut versucht._",
            "",
        ]
    else:
        lines = [
            "## Roh-Digest (ohne KI-Analyse)",
            "",
            "_Es ist kein Zugang zu einem Analyse-Modell konfiguriert - dies "
            "ist die ungefilterte Liste aller NEUEN Meldungen. Mit "
            "konfiguriertem Modell liefert Telco Radar analysierte Briefings "
            "mit Dringlichkeitsbewertung._",
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
