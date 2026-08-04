"""Regional analyst agents.

One agent call per region: gets only the NEW items of its region and returns
a structured assessment (relevance for Vodafone, category, why it matters).
Keeping the intelligence in the delta layer and the judgment in small,
focused agent calls is what makes this cheap and reliable.
"""
from __future__ import annotations

import json
import logging
from concurrent.futures import ThreadPoolExecutor

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


# Themenfelder (config/tech_sources.yaml) sind KEINE Wettbewerber. Nvidia,
# Qualcomm, die GSMA oder Ofcom mit dem Regionalprompt zu bewerten liefert
# systematisch falsche Antworten: das Modell versucht dann, einen Chiphersteller
# als Konkurrenten von Vodafone einzuordnen ("Preisdruck, den Vodafone kontern
# muss"), obwohl die richtige Frage lautet, was ein Zulieferer-, Geraete- oder
# Regulierungsschritt fuer den Netzbetrieb, das Endkundenangebot und die
# Kostenseite bedeutet. Deshalb ein eigener Prompt mit eigenem Bewertungsmassstab.
TECH_ANALYST_SYSTEM = """\
You are a senior technology analyst inside Vodafone Group's strategy team.
Vodafone is a global telecommunications operator (mobile, broadband,
fixed-mobile convergence, B2B/IoT) active in Europe and Africa.

The items below are NOT from competing operators. They are official
announcements from the theme area "{region}" - suppliers, device and chip
makers, AI providers, satellite operators, regulators or industry bodies.
These companies shape the market Vodafone operates in: they decide what the
network can do, what a handset supports, what a service costs and what the
law allows.

The reader is a Vodafone manager WITHOUT a technical or AI background. Write
in {language}, spell out abbreviations on first use, no jargon, no filler.

Assess each item by what it changes for a network OPERATOR: new capability in
the network, a new device/chip feature customers will ask for, a cost or
supply shift, a new distribution or partnership channel, a rule that
constrains or enables an offer. Never frame these companies as Vodafone's
competitors.

Respond with ONLY valid JSON, no markdown, matching this schema:
{{
  "region_summary": "<2-3 sentences in {language}: what is happening in this theme area this week and where it points>",
  "highlights": [
    {{
      "title": "<original title, kept verbatim>",
      "operator": "<the company / authority the news is about>",
      "url": "<original url, verbatim>",
      "category": "<one of: Produktlaunch | Tarif/Pricing | Kampagne | Partnerschaft | Netz/Technologie | Regulierung | M&A | Finanzen | Sonstiges>",
      "relevance": <1-5, 5 = changes what Vodafone can offer or must plan for now>,
      "summary": "<1-2 sentences in {language}: what exactly was announced - names, numbers, dates when given>",
      "why_it_matters": "<1-2 sentences in {language}: the concrete consequence for a network operator - e.g. 'ermoeglicht ...', 'verschiebt die Kosten fuer ...', 'Kunden werden ... erwarten', 'schraenkt ... ein'. Never generic.>"
    }}
  ]
}}

Scoring guide (be strict - most of this is product marketing):
- 5: changes what an operator can sell or must plan for right now (a device
     feature every carrier will have to support, a binding regulatory
     decision, a network-capability launch, direct-to-cell satellite going
     commercial).
- 4: clearly relevant technology or policy development for operator planning.
- 3: worth monitoring, not urgent.
- 2: minor / contextual.
- Drop everything below 2 (developer-tooling minutiae, benchmark posts,
  conference sponsorships, hiring news, generic model-release hype with no
  operator angle) - do NOT put them in "highlights".

Rules:
- Only include items with relevance >= 2 in "highlights".
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
                   language: str = "Deutsch", max_items: int | None = None,
                   is_theme: bool = False, batch_workers: int = 1) -> dict:
    """Run one regional analyst (in batches). Returns the merged assessment.

    Items are processed in batches of BATCH_SIZE so the JSON response never
    hits the output-token limit. A failing batch is skipped, not fatal.
    Also returns lightweight per-batch telemetry for the run log.

    max_items=None means "no cap", which is the point: the seen-store marks
    every new item as known regardless of whether an analyst ever read it, so
    anything dropped here is dropped for good, not deferred to the next run.

    is_theme=True schaltet auf TECH_ANALYST_SYSTEM um - fuer die Themenfelder
    aus config/tech_sources.yaml, deren Absender keine Wettbewerber sind.

    batch_workers > 1 laesst die Stapel EINER Region ueberlappen. Das ist der
    Hebel gegen die Laufzeit, seit der Quellen-Ausbau die Zahl der Meldungen
    vervielfacht: die Stapel sind voneinander unabhaengig, jeder ist reine
    Wartezeit auf den Anbieter, und der Lauf vom 31.07.2026 brauchte mit 220
    neuen Meldungen bereits 49 von 50 zulaessigen Minuten. Eine Kappung waere
    die falsche Antwort - der Seen-Store merkt sich jede neue Meldung als
    erledigt, egal ob ein Analyst sie gelesen hat.
    """
    vorlage = TECH_ANALYST_SYSTEM if is_theme else ANALYST_SYSTEM
    system = vorlage.format(region=region_name, language=language)
    capped = items if not max_items else items[:max_items]
    batches = [capped[i:i + BATCH_SIZE] for i in range(0, len(capped), BATCH_SIZE)]

    def _ein_stapel(n: int, batch: list[Item]) -> dict | None:
        user = (
            f"NEW items for region {region_name} "
            f"(batch {n}/{len(batches)}, {len(batch)} items):\n"
            + _items_payload(batch)
        )
        try:
            raw = complete(system, user, model=model, max_tokens=8000)
            return extract_json(raw)
        except (ValueError, RuntimeError, KeyError) as exc:
            log.error("Analyst %s batch %d/%d failed: %s - skipping batch",
                      region_name, n, len(batches), exc)
            return None

    if batch_workers > 1 and len(batches) > 1:
        with ThreadPoolExecutor(max_workers=batch_workers) as pool:
            # Reihenfolge erhalten: der Bericht sortiert zwar nach Relevanz,
            # aber ein Lauf soll bei gleicher Eingabe dieselbe Ausgabe liefern.
            ergebnisse = list(pool.map(
                lambda p: _ein_stapel(p[0], p[1]),
                [(n, b) for n, b in enumerate(batches, 1)]))
    else:
        ergebnisse = [_ein_stapel(n, b) for n, b in enumerate(batches, 1)]

    highlights: list[dict] = []
    summaries: list[str] = []
    batches_ok = 0
    for result in ergebnisse:
        if result is None:
            continue
        batches_ok += 1
        highlights.extend(result.get("highlights") or [])
        if result.get("region_summary"):
            summaries.append(str(result["region_summary"]))

    log.info("Analyst %-25s: %d items in %d batch(es, %d parallel) -> %d highlights",
             region_name, len(capped), len(batches), batch_workers, len(highlights))
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
