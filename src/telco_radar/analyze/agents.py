"""Regional analyst agents.

One agent call per region: gets only the NEW items of its region and returns
a structured assessment (relevance for Vodafone, category, why it matters).
Keeping the intelligence in the delta layer and the judgment in small,
focused agent calls is what makes this cheap and reliable.
"""
from __future__ import annotations

import json
import logging

from ..models import Item
from .llm import complete, extract_json

log = logging.getLogger(__name__)

ANALYST_SYSTEM = """\
You are a senior competitive-intelligence analyst inside Vodafone Group's
strategy team. Vodafone is a global telecommunications operator (mobile,
broadband, fixed-mobile convergence, B2B/IoT) active in Europe and Africa.
Your job is to watch what competitors worldwide are doing and turn it into
concrete input for Vodafone's own product, pricing and campaign decisions.

The reader is a Vodafone manager WITHOUT a technical or AI background. Write
in {language}, spell out abbreviations on first use, no jargon, no filler.

You receive a JSON list of NEW items (press releases / trade-press articles)
for the region "{region}". Assess each item from a "so what for Vodafone"
angle. For each real signal decide: what happened, and what Vodafone could
actually DO with this insight (copy it, defend against it, watch it, learn
from it).

Respond with ONLY valid JSON, no markdown, matching this schema:
{{
  "region_summary": "<2-3 sentences in {language}: what is happening in this region this week and the direction it points>",
  "highlights": [
    {{
      "title": "<original title, kept verbatim>",
      "operator": "<the operator / company the news is about>",
      "url": "<original url, verbatim>",
      "category": "<one of: Produktlaunch | Tarif/Pricing | Kampagne | Partnerschaft | Netz/Technologie | Regulierung | M&A | Finanzen | Sonstiges>",
      "relevance": <1-5, 5 = Vodafone should react now / copy / watch closely>,
      "summary": "<1-2 sentences in {language}: what exactly happened - names, prices, numbers, dates when given>",
      "why_it_matters": "<1-2 sentences in {language}: the Vodafone angle. Frame it as what Vodafone could DO or learn, e.g. 'Vorlage fuer ein eigenes ...', 'Preisdruck, den Vodafone kontern muss ...', 'zeigt, dass ...'. Never generic.>"
    }}
  ]
}}

Scoring guide (be strict - most PR is noise):
- 5: a competitor move Vodafone should react to or copy quickly (aggressive new
     tariff, disruptive consumer product, FMC/eSIM/roaming/AI-in-tariff launch,
     major partnership that shifts the market).
- 4: clearly relevant strategic development worth a manager's attention.
- 3: worth monitoring, not urgent.
- 2: minor / contextual.
- Drop everything below 2 (sponsorships, HR moves, ESG boilerplate, generic
  PR fluff, pure finance calendar notices) - do NOT put them in "highlights".

Rules:
- Only include items with relevance >= 2 in "highlights".
- Judge relevance from a Vodafone Group perspective (consumer + B2B).
- Never invent items or URLs. Use only what is in the input list.
- Keep it factual and specific. Prefer a concrete number over an adjective.
"""


BATCH_SIZE = 15  # items per LLM call - keeps JSON output well below token limit


def _items_payload(items: list[Item]) -> str:
    rows = []
    for item in items:
        rows.append({
            "title": item.title,
            "operator": item.operator or "",
            "source": item.source_name,
            "date": item.published.date().isoformat() if item.published else None,
            "url": item.url,
            "snippet": item.summary[:300],
        })
    return json.dumps(rows, ensure_ascii=False)


def analyze_region(region_name: str, items: list[Item], model: str,
                   language: str = "Deutsch", max_items: int = 45) -> dict:
    """Run one regional analyst (in batches). Returns the merged assessment.

    Items are processed in batches of BATCH_SIZE so the JSON response never
    hits the output-token limit. A failing batch is skipped, not fatal.
    Also returns lightweight per-batch telemetry for the run log.
    """
    system = ANALYST_SYSTEM.format(region=region_name, language=language)
    capped = items[:max_items]
    batches = [capped[i:i + BATCH_SIZE] for i in range(0, len(capped), BATCH_SIZE)]

    highlights: list[dict] = []
    summaries: list[str] = []
    batches_ok = 0
    for n, batch in enumerate(batches, 1):
        user = (
            f"NEW items for region {region_name} "
            f"(batch {n}/{len(batches)}, {len(batch)} items):\n"
            + _items_payload(batch)
        )
        try:
            raw = complete(system, user, model=model, max_tokens=8000)
            result = extract_json(raw)
        except (ValueError, RuntimeError, KeyError) as exc:
            log.error("Analyst %s batch %d/%d failed: %s - skipping batch",
                      region_name, n, len(batches), exc)
            continue
        batches_ok += 1
        highlights.extend(result.get("highlights") or [])
        if result.get("region_summary"):
            summaries.append(str(result["region_summary"]))

    log.info("Analyst %-25s: %d items in %d batch(es) -> %d highlights",
             region_name, len(capped), len(batches), len(highlights))
    return {
        "region_summary": " ".join(summaries),
        "highlights": highlights,
        "_telemetry": {
            "items_in": len(capped),
            "batches": len(batches),
            "batches_ok": batches_ok,
            "highlights": len(highlights),
            "model": model,
        },
    }
