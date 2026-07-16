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
You are a senior competitive-intelligence analyst working for Vodafone Group.
You monitor telecom operators worldwide and assess news for its relevance to
Vodafone's product, pricing and campaign strategy.

You receive a JSON list of NEW items (press releases / trade-press articles)
for the region "{region}". For each item decide whether it is a real signal.

Respond with ONLY valid JSON, no markdown, matching this schema:
{{
  "region_summary": "<2-3 sentence summary of what is happening in this region, in {language}>",
  "highlights": [
    {{
      "title": "<original title>",
      "operator": "<operator or company involved>",
      "url": "<original url>",
      "category": "<one of: Produktlaunch | Tarif/Pricing | Kampagne | Partnerschaft | Netz/Technologie | Regulierung | M&A | Finanzen | Sonstiges>",
      "relevance": <1-5, 5 = Vodafone should react / copy / watch closely>,
      "summary": "<1-2 sentences: what happened, in {language}>",
      "why_it_matters": "<1-2 sentences: why this matters for Vodafone, in {language}>"
    }}
  ]
}}

Rules:
- Include only items with relevance >= 2 in "highlights" (drop pure noise:
  sponsorships, HR announcements, generic PR fluff).
- Judge relevance from a Vodafone Group perspective: new consumer/business
  products, tariff structures, eSIM/roaming/FMC innovations, campaigns worth
  copying, disruptive pricing, AI-powered services.
- Never invent items. Only use what is in the input list.
- Keep summaries factual and specific (names, prices, dates when given).
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
                   language: str = "Deutsch", max_items: int = 40) -> dict:
    """Run one regional analyst (in batches). Returns the merged assessment.

    Items are processed in batches of BATCH_SIZE so the JSON response never
    hits the output-token limit. A failing batch is skipped, not fatal.
    """
    system = ANALYST_SYSTEM.format(region=region_name, language=language)
    capped = items[:max_items]
    batches = [capped[i:i + BATCH_SIZE] for i in range(0, len(capped), BATCH_SIZE)]

    highlights: list[dict] = []
    summaries: list[str] = []
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
        highlights.extend(result.get("highlights") or [])
        if result.get("region_summary"):
            summaries.append(str(result["region_summary"]))

    log.info("Analyst %-25s: %d items in %d batch(es) -> %d highlights",
             region_name, len(capped), len(batches), len(highlights))
    return {"region_summary": " ".join(summaries), "highlights": highlights}
