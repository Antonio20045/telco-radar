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


def _items_payload(items: list[Item], max_items: int) -> str:
    rows = []
    for item in items[:max_items]:
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
    """Run one regional analyst. Returns the parsed JSON assessment."""
    system = ANALYST_SYSTEM.format(region=region_name, language=language)
    user = (
        f"NEW items for region {region_name} "
        f"({min(len(items), max_items)} of {len(items)}):\n"
        + _items_payload(items, max_items)
    )
    raw = complete(system, user, model=model, max_tokens=4096)
    result = extract_json(raw)
    result.setdefault("highlights", [])
    result.setdefault("region_summary", "")
    log.info("Analyst %-25s: %d items in -> %d highlights",
             region_name, len(items), len(result["highlights"]))
    return result
