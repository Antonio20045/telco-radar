"""Per-competitor deep-dive analysis for the "Wettbewerber" tab.

For each focus competitor we pull a fresh, dedicated news feed (independent of
the weekly delta, so the tab is always substantial) and let the model write a
concise German profile: what they are doing now + what it means for Vodafone.
"""
from __future__ import annotations

import json
import logging

from ..config import Source, bing_news_rss
from .llm import complete, extract_json

log = logging.getLogger(__name__)

COMPETITOR_SYSTEM = """\
You are a senior competitive-intelligence analyst at Vodafone Group. You get a
JSON list of recent news items about the competitor "{name}". Write a concise,
factual profile in {language} for a Vodafone manager WITHOUT technical
background: what this competitor is doing RIGHT NOW (products, pricing, network,
partnerships, strategy), with concrete numbers/dates when given, and what it
means for Vodafone.

Respond with ONLY valid JSON, no markdown:
{{
  "summary": "<3-5 sentences in {language}: what {name} is currently doing and where it is heading>",
  "themes": ["<3-6 short theme tags they are active in, e.g. '5G-Ausbau', 'KI-Tarife', 'Preisoffensive'>"],
  "moves": [
    {{
      "title": "<original headline, verbatim>",
      "url": "<original url, verbatim>",
      "category": "<Produktlaunch | Tarif/Pricing | Kampagne | Partnerschaft | Netz/Technologie | Regulierung | M&A | Finanzen | Sonstiges>",
      "note": "<1 sentence in {language}: what it is and the angle for Vodafone>"
    }}
  ],
  "vodafone_implication": "<2-3 sentences in {language}: what Vodafone should watch or do because of this competitor>"
}}

Rules:
- 4-8 of the most notable, DISTINCT moves in "moves" (drop stock-price notices,
  duplicates, pure listicles).
- Only use items from the input list. Never invent items, urls, or numbers.
- Keep it specific: names, prices, dates, network/tariff details when present.
"""


def _payload(items) -> str:
    rows = []
    for it in items:
        rows.append({
            "title": it.title,
            "source": it.source_name,
            "date": it.published.date().isoformat() if it.published else None,
            "url": it.url,
            "snippet": it.summary[:240],
        })
    return json.dumps(rows, ensure_ascii=False)


def analyze_competitor(name: str, query: str, model: str, http_cfg: dict,
                       language: str = "Deutsch", max_items: int = 12) -> dict:
    """Fetch fresh news for one competitor and return a structured profile."""
    from ..collect.rss import collect_rss
    src = Source(type="rss", url=bing_news_rss(query), name=name,
                 kind="news_search", label="Wettbewerber-Suche")
    try:
        items = collect_rss(src, "focus", name, "competitor", http_cfg)
    except Exception as exc:  # noqa: BLE001
        log.warning("Competitor fetch failed for %s: %s", name, exc)
        items = []
    # de-dupe by url, keep the freshest
    seen, uniq = set(), []
    for it in sorted(items, key=lambda i: (i.published is not None,
                                           i.published or 0), reverse=True):
        if it.url in seen:
            continue
        seen.add(it.url)
        uniq.append(it)
    uniq = uniq[:max_items]

    result = {"name": name, "n_items": len(uniq), "moves": [], "summary": "",
              "themes": [], "vodafone_implication": ""}
    if not uniq:
        return result
    user = f'Recent news items about "{name}":\n' + _payload(uniq)
    try:
        raw = complete(COMPETITOR_SYSTEM.format(name=name, language=language),
                       user, model=model, max_tokens=4000)
        parsed = extract_json(raw)
        result["summary"] = str(parsed.get("summary", ""))
        result["themes"] = [str(t) for t in (parsed.get("themes") or [])][:6]
        result["vodafone_implication"] = str(parsed.get("vodafone_implication", ""))
        moves = []
        for m in (parsed.get("moves") or [])[:8]:
            moves.append({
                "title": str(m.get("title", "")),
                "url": str(m.get("url", "")),
                "category": str(m.get("category", "Sonstiges")),
                "note": str(m.get("note", "")),
            })
        result["moves"] = moves
    except (ValueError, RuntimeError, KeyError) as exc:
        log.error("Competitor analysis failed for %s: %s", name, exc)
    log.info("Competitor %-20s: %d items -> %d moves", name, len(uniq),
             len(result["moves"]))
    return result


def analyze_all(focus: list[dict], model: str, http_cfg: dict,
                language: str = "Deutsch") -> list[dict]:
    out = []
    for c in focus:
        name = c.get("name")
        query = c.get("query") or f'"{name}"'
        if not name:
            continue
        out.append(analyze_competitor(name, query, model, http_cfg, language))
    return out
