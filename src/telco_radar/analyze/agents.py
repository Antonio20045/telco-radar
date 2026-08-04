"""Regional analyst agents.

One agent call per region: gets only the NEW items of its region and returns
a structured assessment (relevance for Vodafone, category, why it matters).
Keeping the intelligence in the delta layer and the judgment in small,
focused agent calls is what makes this cheap and reliable.
"""
from __future__ import annotations

import json
import logging
import time
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

# Token-Budget je Analysten-Aufruf.
#
# Am Laufprotokoll von #71 gemessen und NICHT geraten: von 30 Stapeln
# scheiterten 22, und zwar alle mit derselben Meldung - "Expecting value:
# line 1 column 1 (char 0)". Das ist json.loads("") : der Anbieter hat
# geantwortet, aber NICHTS geschickt. Im ganzen Lauf gab es keinen einzigen
# 429 und keinen 503; die Vermutung, hier stosse man an ein Rate-Limit, war
# falsch.
#
# Die Ursache ist dieselbe, die den Editor 2026 auf 32000 Token gebracht hat:
# deepseek-v4-flash ist ein Reasoning-Modell, und sein Nachdenken zaehlt gegen
# max_tokens. Reicht das Budget nur fuer das Nachdenken, kommt eine voellig
# leere Antwort zurueck - ohne Fehler, ohne finish_reason=length, ohne
# Hinweis. Mit der Fachpresse sind die Anrisse laenger geworden, damit die
# Eingabe groesser und das Nachdenken teurer: 8000 Token reichten nicht mehr.
#
# Kosten spielen dabei keine Rolle: abgerechnet werden ERZEUGTE Token, nicht
# das Budget. Ein Stapel erzeugt real ~1500.
ANALYST_MAX_TOKENS = 24000

# Pause vor dem Nachlauf gescheiterter Stapel. Lang genug, dass die
# Anbieter-Warteschlange sich leert, kurz genug, dass sie im Job-Timeout
# nicht auffaellt.
NACHLAUF_PAUSE = 30.0


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


def analyze_bereiche(bereiche: list[tuple[str, list[Item], bool]], model: str,
                     language: str = "Deutsch", max_items: int | None = None,
                     workers: int = 12) -> dict[str, dict]:
    """Alle Bereiche in EINEM Stapel-Pool bewerten.

    Warum nicht je Bereich ein eigener Pool
    ---------------------------------------
    Bis Lauf #69 lief je Bereich ein eigener Pool, und die Bereiche selbst
    liefen zu dritt: hoechstens llm_max_workers x analyst_batch_workers
    Aufrufe gleichzeitig, aber nur, wenn sich die Arbeit gleichmaessig auf
    die Bereiche verteilt. Genau das tut sie nicht mehr. In Lauf #69 lagen
    793 von 984 neuen Meldungen im Bereich "Global" - jede Fachpresse-
    meldung, deren Titel keinen Betreiber der Watchlist nennt. Dieser eine
    Bereich hatte 53 Stapel, die zwoelf anderen zusammen 19. Waehrend Global
    seine 53 Stapel zu viert abarbeitete, lagen die uebrigen Worker still.

    Mit 70 Fachpressequellen ist das kein Ausreisser, sondern der Normalfall,
    und bei 1000 Quellen wird er ausgepraegter. Deshalb wandern jetzt ALLE
    Stapel aller Bereiche in einen Pool. Die Obergrenze gleichzeitiger
    Aufrufe bleibt dieselbe - sie wird nur tatsaechlich ausgenutzt.
    """
    system_je_bereich = {
        name: (TECH_ANALYST_SYSTEM if ist_thema else ANALYST_SYSTEM).format(
            region=name, language=language)
        for name, _items, ist_thema in bereiche
    }
    gekappt = {name: (items if not max_items else items[:max_items])
               for name, items, _t in bereiche}
    stapel: list[tuple[str, int, int, list[Item]]] = []
    for name, _items, _t in bereiche:
        eigene = gekappt[name]
        teile = [eigene[i:i + BATCH_SIZE]
                 for i in range(0, len(eigene), BATCH_SIZE)]
        for n, teil in enumerate(teile, 1):
            stapel.append((name, n, len(teile), teil))

    def _einer(auftrag) -> dict | None:
        name, n, gesamt, batch = auftrag
        return _ein_stapel(system_je_bereich[name], name, n, gesamt, batch,
                           model)

    log.info("Analyse: %d Stapel aus %d Bereichen, %d gleichzeitig",
             len(stapel), len(bereiche), workers)
    if stapel:
        with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
            ergebnisse = list(pool.map(_einer, stapel))
    else:
        ergebnisse = []

    # Zweiter Durchgang fuer die gescheiterten Stapel, deutlich entdrosselt.
    # Lauf #69 (04.08.2026, erster Lauf nach der Ausbauwelle) hat 42 von 72
    # Stapeln verloren - nicht an einem toten Endpunkt, sondern an Ueberlast
    # unter dem Burst: 984 neue Meldungen auf einmal. llm.py hatte da schon
    # fuenf Wiederholungen mit bis zu 45 s Backoff hinter sich, aber alle
    # INNERHALB des Bursts. Ein Nachlauf, wenn die Welle durch ist und nur
    # noch ein Bruchteil der Aufrufe gleichzeitig laeuft, trifft auf einen
    # freieren Anbieter.
    #
    # Der Nachlauf ist kein Ersatz fuer den Schutz ungelesener Meldungen: was
    # auch hier scheitert, bleibt ungelesen und kommt im naechsten Lauf
    # wieder. Er verkleinert nur den Schaden eines Bursts.
    offen = [(i, s) for i, (s, e) in enumerate(zip(stapel, ergebnisse))
             if e is None]
    if offen and len(offen) < len(stapel):
        nachlauf_workers = max(1, workers // 4)
        log.warning("%d von %d Stapeln gescheitert - Nachlauf mit %d "
                    "gleichzeitigen Aufrufen", len(offen), len(stapel),
                    nachlauf_workers)
        time.sleep(NACHLAUF_PAUSE)
        with ThreadPoolExecutor(max_workers=nachlauf_workers) as pool:
            zweite = list(pool.map(lambda p: _einer(p[1]), offen))
        gerettet = 0
        for (i, _s), ergebnis in zip(offen, zweite):
            if ergebnis is not None:
                ergebnisse[i] = ergebnis
                gerettet += 1
        log.warning("Nachlauf: %d von %d Stapeln gerettet", gerettet, len(offen))

    je_bereich: dict[str, list] = {name: [] for name, _i, _t in bereiche}
    for (name, _n, _gesamt, batch), ergebnis in zip(stapel, ergebnisse):
        je_bereich[name].append((ergebnis, batch))
    return {name: _zusammenfassen(name, gekappt[name], je_bereich[name],
                                  workers, model)
            for name, _items, _t in bereiche}


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

    def _einer(p):
        return _ein_stapel(system, region_name, p[0], len(batches), p[1], model)

    if batch_workers > 1 and len(batches) > 1:
        with ThreadPoolExecutor(max_workers=batch_workers) as pool:
            # Reihenfolge erhalten: der Bericht sortiert zwar nach Relevanz,
            # aber ein Lauf soll bei gleicher Eingabe dieselbe Ausgabe liefern.
            ergebnisse = list(pool.map(
                _einer, [(n, b) for n, b in enumerate(batches, 1)]))
    else:
        ergebnisse = [_einer((n, b)) for n, b in enumerate(batches, 1)]

    return _zusammenfassen(region_name, capped,
                           list(zip(ergebnisse, batches)), batch_workers, model)


def _ein_stapel(system: str, bereich: str, n: int, gesamt: int,
                batch: list[Item], model: str) -> dict | None:
    """Ein Analysten-Aufruf. Ein gescheiterter Stapel ist kein Laufabbruch."""
    user = (f"NEW items for region {bereich} "
            f"(batch {n}/{gesamt}, {len(batch)} items):\n"
            + _items_payload(batch))
    try:
        raw = complete(system, user, model=model, max_tokens=ANALYST_MAX_TOKENS)
        return extract_json(raw)
    except (ValueError, RuntimeError, KeyError) as exc:
        log.error("Analyst %s batch %d/%d failed: %s - skipping batch",
                  bereich, n, gesamt, exc)
        return None


def _zusammenfassen(bereich: str, gelesen: list[Item],
                    ergebnisse: list[tuple[dict | None, list[Item]]],
                    parallel: int, model: str) -> dict:
    """Die Stapel eines Bereichs zu einem Ergebnis verschmelzen."""
    highlights: list[dict] = []
    summaries: list[str] = []
    batches_ok = 0
    # Meldungen aus gescheiterten Stapeln. Sie hat kein Analyst gesehen und
    # sie duerfen deshalb NICHT in den Seen-Store - sonst gelten sie als
    # erledigt und werden nie wieder gesammelt. Der Schutz aus Lauf #64 wirkte
    # nur, wenn eine Region KOMPLETT ausfiel; im Lauf #67 (04.08.2026)
    # scheiterten 2 von 3 Stapeln des Themenfelds KI-Anbieter und 1 von 2 bei
    # Regulierung - rund 33 Meldungen wanderten ungelesen in den Store. In
    # Lauf #69 waren es 607 von 984, weil der Anbieter unter der Last der
    # ersten Ausbauwelle 42 von 72 Stapeln abwies: der Schutz hat sie
    # zurueckgehalten, und der naechste Lauf hat sie erneut vorgelegt.
    ungelesen: list[str] = []
    for result, batch in ergebnisse:
        if result is None:
            ungelesen.extend(i.id for i in batch)
            continue
        batches_ok += 1
        highlights.extend(result.get("highlights") or [])
        if result.get("region_summary"):
            summaries.append(str(result["region_summary"]))

    log.info("Analyst %-25s: %d items in %d batch(es, %d parallel) -> %d "
             "highlights, %d ungelesen",
             bereich, len(gelesen), len(ergebnisse), parallel,
             len(highlights), len(ungelesen))
    return {
        "region_summary": " ".join(summaries),
        "highlights": highlights,
        "_telemetry": {
            "items_in": len(gelesen),
            "batches": len(ergebnisse),
            "batches_ok": batches_ok,
            "highlights": len(highlights),
            "unread_items": len(ungelesen),
            "model": model,
        },
        "_ungelesen": ungelesen,
    }
