"""Per-competitor deep-dive for the "Wettbewerber" tab.

Built from the SAME clean trade-press items the pipeline already collected
(matched to the competitor by name/alias), not a keyword news search. Every
item is a real telco article with a direct publisher link.
"""
from __future__ import annotations

import json
import logging
import re

from .llm import complete, extract_json

log = logging.getLogger(__name__)

COMPETITOR_SYSTEM = """\
You are a senior competitive-intelligence analyst at Vodafone Group. You get a
JSON list of recent telecom trade-press articles that mention "{name}". Write a
concise, factual profile in {language} for a Vodafone manager: what {name} is
doing RIGHT NOW (products, pricing, network, partnerships, strategy), with
concrete numbers/dates when given, and what it means for Vodafone.

Respond with ONLY valid JSON, no markdown:
{{
  "summary": "<3-5 sentences in {language}: what {name} is currently doing and where it is heading>",
  "themes": ["<3-6 short theme tags, e.g. '5G-Ausbau', 'KI-Tarife', 'Preisoffensive'>"],
  "moves": [
    {{"title": "<original headline verbatim>", "url": "<original url verbatim>",
      "category": "<Produktlaunch | Tarif/Pricing | Kampagne | Partnerschaft | Netz/Technologie | Regulierung | M&A | Finanzen | Sonstiges>",
      "note": "<1 sentence in {language}: what it is and the angle for Vodafone>"}}
  ],
  "vodafone_implication": "<2-3 sentences in {language}: what Vodafone should watch or do>"
}}

Rules:
- 4-8 of the most notable, DISTINCT moves (drop stock notices, duplicates).
- Only use items from the input list. Never invent items, urls, or numbers.
- If the input is thin, keep the profile short but accurate - do not pad.
"""


def _matcher(terms):
    pats = []
    for t in terms:
        t = (t or "").strip()
        if len(t) < 2:
            continue
        pats.append(re.compile(r"(?<!\w)" + re.escape(t.lower()) + r"(?!\w)"))
    return pats


def _payload(items):
    rows = []
    for it in items:
        rows.append({"title": it.title, "source": it.source_name,
                     "date": it.published.date().isoformat() if it.published else None,
                     "url": it.url, "snippet": it.summary[:240]})
    return json.dumps(rows, ensure_ascii=False)


def analyze_competitor(name, terms, items, model, language="Deutsch",
                       max_items=16):
    pats = _matcher([name] + list(terms or []))
    matched, seen = [], set()
    for it in items:
        hay = (it.title + " " + (it.summary or "")).lower()
        if any(p.search(hay) for p in pats) and it.url not in seen:
            seen.add(it.url)
            matched.append(it)
    matched.sort(key=lambda i: (i.published is not None, i.published or 0),
                 reverse=True)
    matched = matched[:max_items]

    result = {"name": name, "n_items": len(matched), "moves": [],
              "summary": "", "themes": [], "vodafone_implication": ""}
    if not matched:
        return result
    user = f'Recent telecom trade-press articles mentioning "{name}":\n' + _payload(matched)
    try:
        parsed = extract_json(complete(
            COMPETITOR_SYSTEM.format(name=name, language=language), user,
            model=model, max_tokens=3500))
        result["summary"] = str(parsed.get("summary", ""))
        result["themes"] = [str(t) for t in (parsed.get("themes") or [])][:6]
        result["vodafone_implication"] = str(parsed.get("vodafone_implication", ""))
        for m in (parsed.get("moves") or [])[:8]:
            result["moves"].append({
                "title": str(m.get("title", "")), "url": str(m.get("url", "")),
                "category": str(m.get("category", "Sonstiges")),
                "note": str(m.get("note", ""))})
    except (ValueError, RuntimeError, KeyError) as exc:
        log.error("Competitor analysis failed for %s: %s", name, exc)
    log.info("Competitor %-20s: %d matched items -> %d moves", name,
             len(matched), len(result["moves"]))
    return result


def analyze_all(focus, items, model, language="Deutsch"):
    out = []
    for c in focus:
        name = c.get("name")
        if not name:
            continue
        out.append(analyze_competitor(name, c.get("aliases") or [], items,
                                      model, language))
    return out
