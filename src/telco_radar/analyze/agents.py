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

{TEXTFELD}

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
      "headline": "<HEADLINE in {language}, max 9 words, no trailing period: what happened, active voice, concrete. Like a newspaper front page, NOT a summary sentence>",
      "summary": "<1-2 sentences in {language}: what exactly happened - names, prices, numbers, dates when given>",
      "why_it_matters": "<1-2 sentences in {language}: the Vodafone angle. Frame it as what Vodafone could DO or learn, e.g. 'Vorlage fuer ein eigenes ...', 'Preisdruck, den Vodafone kontern muss ...', 'zeigt, dass ...'. Never generic.>",
      {CTM_FELDER}
    }}
  ]
}}

Scoring guide (be strict - most PR is noise):
- 5: a competitor move Vodafone should react to or copy quickly (aggressive new
     tariff, disruptive consumer product, FMC/eSIM/roaming/AI-in-tariff launch,
     major partnership that shifts the market). Requires EITHER a major
     operator/market-mover as sender OR direct relevance for the German/
     European consumer market - a niche or regional player with no market
     followership is capped at 3, even if its own move sounds aggressive.
- 4: clearly relevant strategic development worth a manager's attention.
- 3: worth monitoring, not urgent.
- 2: minor / contextual.
- Drop everything below 2 (sponsorships, HR moves, ESG boilerplate, generic
  PR fluff, pure finance calendar notices) - do NOT put them in "highlights".

Rules:
- Only include items with relevance >= 2 in "highlights".
- Judge relevance from a Vodafone Group perspective (consumer + B2B).
- A global device or market-share story (e.g. "best-selling phone worldwide")
  is "Produktlaunch", never "Sonstiges" - it is about a specific product.
- When two items are otherwise comparable in scope, consumer-facing relevance
  (tariff, device, network quality a customer feels) outweighs vendor PR,
  AGM notices and infrastructure-financing announcements.
- Never invent items or URLs. Use only what is in the input list.
- Keep it factual and specific. Prefer a concrete number over an adjective.
"""


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

{TEXTFELD}

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
      "headline": "<HEADLINE in {language}, max 9 words, no trailing period: what happened, active voice, concrete. Like a newspaper front page, NOT a summary sentence>",
      "summary": "<1-2 sentences in {language}: what exactly was announced - names, numbers, dates when given>",
      "why_it_matters": "<1-2 sentences in {language}: the concrete consequence for a network operator - e.g. 'ermoeglicht ...', 'verschiebt die Kosten fuer ...', 'Kunden werden ... erwarten', 'schraenkt ... ein'. Never generic.>",
      {CTM_FELDER}
    }}
  ]
}}

Scoring guide (be strict - most of this is product marketing):
- 5: changes what an operator can sell or must plan for right now (a device
     feature every carrier will have to support, a binding regulatory
     decision, a network-capability launch, direct-to-cell satellite going
     commercial). Requires EITHER a major supplier/standard-setter as sender
     OR direct relevance for the German/European consumer market - a niche
     vendor with no market followership is capped at 3.
- 4: clearly relevant technology or policy development for operator planning.
- 3: worth monitoring, not urgent.
- 2: minor / contextual.
- Drop everything below 2 (developer-tooling minutiae, benchmark posts,
  conference sponsorships, hiring news, generic model-release hype with no
  operator angle) - do NOT put them in "highlights".

Rules:
- Only include items with relevance >= 2 in "highlights".
- A global device or market-share story (e.g. "best-selling phone worldwide")
  is "Produktlaunch", never "Sonstiges" - it is about a specific product.
- When two items are otherwise comparable in scope, consumer-facing relevance
  (device, network quality a customer feels) outweighs vendor PR, AGM notices
  and infrastructure-financing announcements.
- Never invent items or URLs. Use only what is in the input list.
- Keep it factual and specific. Prefer a concrete number over an adjective.
"""


CTM_FELDER = """\
"ctm_bezug": <0, 1 oder 2 - wie unmittelbar diese Meldung ein deutsches
        Endkunden-Portfolio (Tarife, Optionen, Geraete, Logistik) beruehrt:
        2 = uebertragbare Endkundenmechanik aus einem vergleichbaren Markt
            (Westeuropa, Nordamerika): ein Tarif, ein Bundle, eine Aktion,
            eine Option, die man hier nachbauen koennte
        1 = Kontext: Branche, Technik, Regulierung mit mittelbarer Wirkung
        0 = Hintergrund: Infrastruktur, Geschaeftskunden, Kapitalmarkt,
            Personalien - ohne Endkundenbezug>,
      "ctm_satz": "<NUR wenn ctm_bezug 2 ist: EIN Satz in {language}, hoechstens
        25 Woerter, der sagt, was das FUER DAS EIGENE PORTFOLIO heisst.
        Er muss eine Konsequenz oder eine offene Frage enthalten, niemals
        die Meldung wiederholen.
        FALSCH: 'Das zeigt den Trend zu Bundles.'
        RICHTIG: 'Erste 5G-Flat unter 35 Euro in einem Nachbarmarkt - drueckt
        die Preisuntergrenze fuer unsere Unlimited-Stufe.'
        Keine Zahl, die nicht in der Quelle steht. Bei Unsicherheit genau
        eines dieser Woerter benutzen: moeglich / wahrscheinlich / sehr
        wahrscheinlich. Sonst leer lassen.>\""""

TEXTFELD = """\
The "text" field carries the article text as far as it was available - often
the full body, sometimes only a teaser, and for some sources it is EMPTY
because the source publishes headlines only. It may end mid-sentence; that is
a length limit, not the end of the article. Judge from it, and take your
names, prices, numbers and dates from it - but never invent what is not
there. If "text" is empty, work from the headline alone, say only what the
headline actually says, and score conservatively.

Your own "summary" stays 1-2 sentences no matter how long "text" is. If you
put a number in "summary" or in any other field, it must be a number you
actually read - a later automatic check compares your fields against each
other and silently drops what it cannot verify."""

BATCH_SIZE = 24

ANALYST_MAX_TOKENS = 26000

ANALYST_TEXT_ZEICHEN = 2500


def analyst_text(item: Item) -> str:
    """Der laengste Text, der ohne einen zusaetzlichen Abruf zu haben ist.

    Bewusst KEIN Artikelabruf: diese Funktion laeuft ueber jede neue Meldung
    eines Laufs (am 14.08.2026 waren das 944), und 944 zusaetzliche HTTP-
    Abrufe vor der Analyse waeren eine zweite Sammelphase. Der Abruf hat
    seinen Ort in der Uebersetzungsstufe, die ihn fuer eine Handvoll
    Meldungen mit Frist und Deckel macht.
    """
    volltext = (item.volltext or "").strip()
    teaser = (item.summary or "").strip()
    text = volltext if len(volltext) > len(teaser) else teaser
    return text[:ANALYST_TEXT_ZEICHEN]


def _items_payload(items: list[Item]) -> str:
    rows = []
    for item in items:
        rows.append(
            {
                "title": item.title,
                "operator": item.operator or "",
                "source": item.source_name,
                "date": item.published.date().isoformat() if item.published else None,
                "url": item.url,
                "text": analyst_text(item),
            }
        )
    return json.dumps(rows, ensure_ascii=False)


def analyze_region(
    region_name: str,
    items: list[Item],
    model: str,
    language: str = "Deutsch",
    max_items: int | None = None,
    is_theme: bool = False,
    batch_workers: int = 1,
    ausweich: str = "",
) -> dict:
    """Run one regional analyst (in batches). Returns the merged assessment.

    Items are processed in batches of BATCH_SIZE so the JSON response never
    hits the output-token limit. A failing batch is skipped, not fatal.
    Also returns lightweight per-batch telemetry for the run log.

    max_items=None means "no cap", which is the point: the seen-store marks
    every new item as known regardless of whether an analyst ever read it, so
    anything dropped here is dropped for good, not deferred to the next run.

    is_theme=True schaltet auf TECH_ANALYST_SYSTEM um - fuer die Themenfelder
    aus config/tech_sources.yaml, deren Absender keine Wettbewerber sind.

    `ausweich` ist der Anker DIESER Stufe - das Modell, das einspringt, wenn
    das Primaermodell hart gescheitert ist (leeres Guthaben, toter Endpunkt).
    Er wird je AUFRUF mitgegeben statt in `llm._FALLBACKS` registriert, weil
    Analyst und Redaktion sich in jeder heutigen Anbieter-Konfiguration
    denselben Modellnamen teilen ("deepseek-v4-pro") und eine Registrierung
    am Namen deshalb nur EINEN Anker fuer beide kennt. Der Analyst macht die
    allermeisten Aufrufe und gehoert ins kleinste Modell; die Redaktion
    schreibt den Bericht und gehoert ins grosse. Ohne diesen Parameter erbt
    der Analyst den Redaktionsanker (siehe pipeline._registriere_anker).
    Leer heisst: die registrierte Kette gilt unveraendert.

    batch_workers > 1 laesst die Stapel EINER Region ueberlappen. Das ist der
    Hebel gegen die Laufzeit, seit der Quellen-Ausbau die Zahl der Meldungen
    vervielfacht: die Stapel sind voneinander unabhaengig, jeder ist reine
    Wartezeit auf den Anbieter, und der Lauf vom 31.07.2026 brauchte mit 220
    neuen Meldungen bereits 49 von 50 zulaessigen Minuten. Eine Kappung waere
    die falsche Antwort - der Seen-Store merkt sich jede neue Meldung als
    erledigt, egal ob ein Analyst sie gelesen hat.
    """
    vorlage = TECH_ANALYST_SYSTEM if is_theme else ANALYST_SYSTEM
    system = vorlage.format(
        region=region_name,
        language=language,
        CTM_FELDER=CTM_FELDER.format(language=language),
        TEXTFELD=TEXTFELD,
    )
    capped = items if not max_items else items[:max_items]
    batches = [capped[i : i + BATCH_SIZE] for i in range(0, len(capped), BATCH_SIZE)]

    def _ein_stapel(n: int, batch: list[Item]) -> dict | None:
        user = (
            f"NEW items for region {region_name} "
            f"(batch {n}/{len(batches)}, {len(batch)} items):\n" + _items_payload(batch)
        )
        try:
            raw = complete(
                system,
                user,
                model=model,
                max_tokens=ANALYST_MAX_TOKENS,
                ausweich=ausweich,
            )
            return extract_json(raw)
        except (ValueError, RuntimeError, KeyError) as exc:
            log.error(
                "Analyst %s batch %d/%d failed: %s - skipping batch",
                region_name,
                n,
                len(batches),
                exc,
            )
            return None

    if batch_workers > 1 and len(batches) > 1:
        with ThreadPoolExecutor(max_workers=batch_workers) as pool:
            ergebnisse = list(
                pool.map(
                    lambda p: _ein_stapel(p[0], p[1]),
                    [(n, b) for n, b in enumerate(batches, 1)],
                )
            )
    else:
        ergebnisse = [_ein_stapel(n, b) for n, b in enumerate(batches, 1)]

    highlights: list[dict] = []
    summaries: list[str] = []
    batches_ok = 0
    ungelesen: list[str] = []
    for result, batch in zip(ergebnisse, batches):
        if result is None:
            ungelesen.extend(i.id for i in batch)
            continue
        batches_ok += 1
        highlights.extend(result.get("highlights") or [])
        if result.get("region_summary"):
            summaries.append(str(result["region_summary"]))

    log.info(
        "Analyst %-25s: %d items in %d batch(es, %d parallel) -> %d "
        "highlights, %d ungelesen",
        region_name,
        len(capped),
        len(batches),
        batch_workers,
        len(highlights),
        len(ungelesen),
    )
    return {
        "region_summary": " ".join(summaries),
        "highlights": highlights,
        "_telemetry": {
            "items_in": len(capped),
            "batches": len(batches),
            "batches_ok": batches_ok,
            "highlights": len(highlights),
            "unread_items": len(ungelesen),
            "model": model,
        },
        "_ungelesen": ungelesen,
    }
