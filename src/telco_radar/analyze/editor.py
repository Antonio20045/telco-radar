"""Editor agent: synthesizes regional analyses into one global market report.

Gets the list of previously reported topics as "do not repeat" memory.
If no LLM is available, build_digest() produces a deterministic raw digest
so the pipeline always delivers something useful.
"""
from __future__ import annotations

import json
import logging
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import date

from ..models import Item
from .llm import complete, llm_available

log = logging.getLogger(__name__)


class EditorialBriefingError(RuntimeError):
    """Raised when the editor output is not a publishable weekly briefing.

    `grund` benennt maschinenlesbar, WAS nicht stimmte ("gliederung" oder
    "empfehlungen"). Der Korrekturversuch braucht das: einem Bericht, der an
    den Vodafone-Empfehlungen scheitert, die Ueberschriften zu diktieren,
    laesst ihn ein zweites Mal am selben Punkt scheitern - genau das ist im
    Test vom 04.08.2026 passiert.
    """

    def __init__(self, message: str, grund: str = "gliederung"):
        super().__init__(message)
        self.grund = grund

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

{themenabschnitt}
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

# Eigener Abschnitt fuer die Themenfelder (config/tech_sources.yaml). Ohne ihn
# verteilt der Editor Nvidia-, Qualcomm- und Ofcom-Meldungen auf die
# Regionsabschnitte, wo sie zwischen den Betreibermeldungen untergehen und den
# Bericht zur Linkliste machen - genau das, was der Auftrag verhindern will.
# Der Abschnitt kommt NUR in den Prompt, wenn dieser Lauf auch Themenmeldungen
# hat; sonst wuerde eine Pflicht-Ueberschrift verlangt, zu der es nichts zu
# schreiben gibt. Deshalb haengen Prompt und Pflichtpruefung am selben Schalter
# (siehe validate_editorial_briefing).
THEMEN_ABSCHNITT = """
## Technologie, Geräte & Regulierung
The theme sections below ("{themen}") are NOT operators - they are suppliers,
device and chip makers, AI providers, satellite operators and regulators.
Give them ONE joint section of 4-8 sentences: what changed in the operators'
supply chain, in the devices their customers buy and in the rules they work
under, and what those changes have in common. Name the companies and the
concrete announcement, always with [Quelle](url). Do NOT list every item -
pick what actually moves a network operator. Never present these companies as
Vodafone's competitors.
"""

# Ueberschrift dieses Abschnitts, normalisiert wie in
# validate_editorial_briefing (klein, Umlaute aufgeloest).
THEMEN_UEBERSCHRIFT = "## technologie, geraete & regulierung"


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
               highlight_budget: int = EDITOR_HIGHLIGHT_BUDGET,
               themenbereiche: list[str] | None = None) -> tuple[str, list[str]]:
    """Run the editor. Returns (markdown_report, covered_topics).

    `themenbereiche` sind die Anzeigenamen der Themenfelder, die in DIESEM
    Lauf bewertete Meldungen haben (z. B. ["KI & Modelle", "Netzausruester"]).
    Ist die Liste leer, verhaelt sich der Editor exakt wie vorher.
    """
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
    themen = [t for t in (themenbereiche or []) if t]
    system = EDITOR_SYSTEM.format(
        language=language,
        themenabschnitt=(THEMEN_ABSCHNITT.format(themen='", "'.join(themen))
                         if themen else ""))
    pflicht = frozenset({THEMEN_UEBERSCHRIFT}) if themen else frozenset()
    try:
        return _ein_versuch(system, user, model, pflicht)
    except EditorialBriefingError as exc:
        # Der Wochenbericht ist das Herzstueck der Seite. Ihn beim ersten
        # Formfehler wegzuwerfen und stattdessen den Roh-Digest zu
        # veroeffentlichen, ist die teuerste moegliche Reaktion - der Inhalt
        # war ja da, nur die Gliederung stimmte nicht. Also einmal gezielt
        # nachfassen, mit den Ueberschriften woertlich im Auftrag.
        log.warning("Editor-Ausgabe abgelehnt (%s) - ein Korrekturversuch", exc)
        nachfassen = NACHFASSEN[exc.grund]
        if exc.grund == "gliederung" and themen:
            nachfassen += "## Technologie, Geräte & Regulierung\n"
        return _ein_versuch(system + nachfassen, user, model, pflicht)


# Wird nur an den zweiten Versuch angehaengt, passend zum Ablehnungsgrund.
NACHFASSEN = {
    "gliederung": """

WICHTIG - der vorherige Versuch wurde verworfen, weil die Gliederung nicht
stimmte. Die Ueberschriften muessen WOERTLICH und als H2 ("## ") vorkommen,
in genau dieser Schreibweise, ohne Nummerierung und ohne Zusaetze:

## Auf einen Blick
## Das Wichtigste
## Die wichtigsten Signale
## Muster der Woche

Beginne die Antwort unmittelbar mit "## Auf einen Blick" - kein Vorwort, kein
Titel, kein Code-Block darum.
""",
    "empfehlungen": """

WICHTIG - der vorherige Versuch wurde verworfen, weil er Vodafone Ratschlaege
gegeben hat. Dieser Bericht ist reine Marktbeobachtung fuer ein Publikum, das
selbst entscheidet. Verboten sind deshalb:
  - jeder Abschnitt oder Satz, der sagt, was Vodafone tun sollte oder koennte
  - Formulierungen wie "Empfehlungen fuer Vodafone", "Fuer Vodafone:",
    "Vodafone sollte", "Vodafone koennte"
  - Handlungsempfehlungen, Massnahmen, To-dos, "Implikationen fuer uns"

Vodafone darf vorkommen - aber nur als beobachteter Marktteilnehmer, genau
wie jeder andere Betreiber ("Vodafone hat X angekuendigt"). Schreibe, WAS
passiert ist, nicht, was jemand daraus machen soll.
""",
}

# Am echten Editor-Prompt aus Lauf #65 gemessen (155 Meldungen, 34k Token
# Eingabe), gegen deepseek-v4-pro:
#   8000  erster Versuch voellig leer, zweiter Versuch bricht vor dem letzten
#         Abschnitt ab ("## Muster der Woche" fehlte).
# Drei Posten teilen sich dieses Budget, und die ersten beiden werden bei
# einer Aufgabe dieser Groesse leicht unterschaetzt:
#   1. das Nachdenken des Modells - bei Reasoning-Modellen (DeepSeek V4,
#      Claude mit adaptive thinking) zaehlt es gegen max_tokens. Reicht das
#      Budget nur dafuer, kommt eine voellig LEERE Antwort zurueck, ohne
#      Fehler. Genau so sahen die Fehlschlaege in den Laeufen #63 und #65 aus.
#   2. die Themenliste hinter ===TOPICS===, ein Eintrag je behandelter
#      Meldung - bei 155 Meldungen allein mehrere tausend Token.
#   3. der Bericht selbst, unter ~1900 Woertern also ~3000 Token.
# 32000 gibt allen dreien Luft. Kosten spielen dabei keine Rolle: abgerechnet
# werden erzeugte Token, nicht das Budget.
EDITOR_MAX_TOKENS = 32000


def _ein_versuch(system: str, user: str, model: str,
                 zusatz_pflicht: frozenset[str] = frozenset()) -> tuple[str, list[str]]:
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
    validate_editorial_briefing(markdown, zusatz_pflicht)
    return markdown, topics


def validate_editorial_briefing(
        markdown: str,
        zusatz_pflicht: frozenset[str] = frozenset()) -> None:
    """Reject a raw source list before it can replace the public report.

    A technical outage at the free model provider must leave the last good
    briefing online, not turn the homepage into a list of collected links.

    `zusatz_pflicht` enthaelt Ueberschriften, die NUR in bestimmten Laeufen
    Pflicht sind - aktuell der Themenabschnitt, der genau dann verlangt wird,
    wenn synthesize() ihn auch in den Prompt geschrieben hat. Prompt und
    Pruefung haengen deshalb am selben Schalter; wer den einen aendert, aendert
    den anderen mit.
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
    } | set(zusatz_pflicht)
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
    for phrase in ("empfehlungen fuer vodafone", "fuer vodafone:",
                   "vodafone sollte", "vodafone koennte"):
        pos = lowered.find(phrase)
        if pos < 0:
            continue
        # Die Fundstelle mitgeben: ohne sie ist nicht zu unterscheiden, ob das
        # Modell wirklich einen Empfehlungsteil geschrieben hat oder ob eine
        # harmlose Formulierung die Regel ausloest.
        stelle = " ".join(markdown[max(0, pos - 80):pos + 120].split())
        raise EditorialBriefingError(
            f"Editor output contains Vodafone recommendations "
            f"({phrase!r}). Stelle: ...{stelle}...", grund="empfehlungen")


# =========================================================================== #
# Zweistufige Redaktion
#
# Warum (AUFTRAG_SKALIERUNG_1000.md 3.2): heute bekommt der Editor in EINEM
# Aufruf alle bewerteten Meldungen. Bei 1000 Quellen waeren das hochgerechnet
# ~650 Meldungen, ~477 KB, ~122k Token. Das passt formal in das Kontextfenster
# der konfigurierten Modelle und ist trotzdem der falsche Weg:
#   * ein Modell, das 650 Meldungen zu 1900 Woertern verdichten soll, schreibt
#     Brei - es kann nicht mehr abwaegen, sondern nur noch aufzaehlen;
#   * ein einziger fehlgeschlagener Aufruf kostet den ganzen Wochenbericht;
#   * die Latenz eines 120k-Token-Calls ist nach oben offen.
#
# Deshalb zwei Stufen:
#   1. Bereichsredakteure - einer je Region und je Themenfeld, parallel. Jeder
#      sieht NUR seinen Bereich, schreibt dessen fertigen Abschnitt und eine
#      Kurzfassung von 3-5 Saetzen.
#   2. Chefredaktion - bekommt NUR die Kurzfassungen und die staerksten
#      Meldungen je Bereich, nie die Rohliste. Schreibt "Auf einen Blick",
#      "Das Wichtigste", "Die wichtigsten Signale" und "Muster der Woche".
#
# Damit haengt die Eingabelaenge der Chefredaktion an der Zahl der BEREICHE,
# nicht an der Zahl der Meldungen. Die Bereichsabschnitte werden unter den
# Chefteil montiert, nicht neu geschrieben.
# =========================================================================== #

BEREICH_SYSTEM = """\
You are the section editor for "{bereich}" in the weekly "Telco Radar"
briefing. You receive the assessments of your analyst team for THIS AREA ONLY
(JSON) plus a list of topics already covered in previous editions.

Write in {language} as clean Markdown. Your readers are managers WITHOUT a
technical or AI background: write plainly, spell out abbreviations on first
use, explain the concrete customer offer or project. This is market
observation, not a recommendation memo. Direct, factual sentences, no filler.

Output EXACTLY this, nothing before and nothing after:

{ueberschrift} {bereich}
A 2-3 sentence summary of what happened in this area this week and where it
points. Then the individual items, strongest first, 1-2 sentences each, always
with [Quelle](url). Do not list every item - leave out what a manager would
skip. Aim for {woerter} words in total.

===KURZFASSUNG===
3-5 sentences for the chief editor: the essence of this area this week. No
markdown, no links, no bullet points - flowing text. This is what the chief
editor uses to see the whole week at once, so name the operators and the
concrete moves, not "several developments".

===TOPICS===
A JSON array of short topic strings (operator + subject) for every item you
covered.

Rules:
- NEVER re-report a topic from the "already covered" list unless there is a
  genuinely NEW development - then frame it explicitly as "Update zu ...".
- No invented facts, no invented URLs. Use only what is in the input.
- Every factual claim that has a source carries its [Quelle](url).
- Do not write recommendations, action items or "Fuer Vodafone" sections.
"""

CHEF_SYSTEM = """\
You are the chief editor of "Telco Radar", a weekly global
competitive-intelligence briefing. The point of this briefing is simple: show
what telecommunications companies around the world did this week and which
patterns become visible across regions and operators.

Your section editors have already written their area sections. You receive
their SUMMARIES and their strongest items - not the raw list. Your job is the
overall picture, not a repetition of their work: the area sections are mounted
below your part unchanged.

Write in {language} as clean Markdown (no top-level H1). Your readers are
managers WITHOUT a technical or AI background. Direct, factual sentences.
No filler, no marketing phrases.

Structure exactly, and nothing else:

## Auf einen Blick
Exactly 3 bullet points, one sentence each: the three things a manager with
30 seconds must take away this week.

## Das Wichtigste
4-6 sentences: the most important competitor developments worldwide this week
and the overall picture they form. Name operators and concrete moves.

## Die wichtigsten Signale
The 6-10 most relevant items across ALL areas (relevance 5 first, then 4).
Per item:
**Operator - Titel** (Kategorie, Dringlichkeit X/5)
2-3 sentences of detail (what happened, with numbers/prices/dates when given).
Source as [Quelle](url).

## Muster der Woche
2-4 cross-area patterns in this week's data (e.g. "mehrere Betreiber buendeln
KI-Assistenten in Consumer-Tarife"). Reference the supporting operators by
name. A pattern must be visible in at least two areas - otherwise it is a
single event and belongs in "Die wichtigsten Signale".

Rules:
- Write ONLY these four sections. Do NOT repeat the area sections and do NOT
  write your own regional sections - they already exist below your part.
- NEVER re-report a topic from the "already covered" list unless there is a
  genuinely NEW development - then frame it explicitly as "Update zu ...".
- No invented facts, no invented URLs. Use only what is in the input.
- Do not write recommendations, action items or "Fuer Vodafone" sections.
- Keep your part under ~900 words.

After the Markdown, output the line ===TOPICS=== followed by a JSON array of
short topic strings for every item you covered.
"""

# Ueberschrift, unter der ALLE Themenfelder gemeinsam stehen. Der Auftrag will
# einen Abschnitt, nicht sechs verstreute - und validate_editorial_briefing
# verlangt genau diese Zeile, wenn es in diesem Lauf Themenmeldungen gibt.
THEMEN_H2 = "## Technologie, Geräte & Regulierung"

# Ein Bereichsabschnitt ist kurz; die Chefredaktion laeuft ueber _ein_versuch()
# und teilt sich das grosse Budget (EDITOR_MAX_TOKENS) mit dem einstufigen
# Editor - dieselbe Aufgabe, dieselbe Denk- und Themenlistenlast.
BEREICH_MAX_TOKENS = 16000

# Wie viele Meldungen eines Bereichs die Chefredaktion zu sehen bekommt. Der
# ganze Sinn der zweiten Stufe ist, dass ihre Eingabe an der Zahl der BEREICHE
# haengt und nicht an der Zahl der Meldungen - eine Obergrenze je Bereich ist
# deshalb keine Kappung des Berichts, sondern der Mechanismus selbst. Die
# uebrigen Meldungen stehen vollstaendig im Bereichsabschnitt und im JSON.
CHEF_MELDUNGEN_JE_BEREICH = 5


def _staerkste(highlights: list[dict], anzahl: int) -> list[dict]:
    """Die relevantesten Meldungen eines Bereichs, knapp fuer die Chefredaktion."""
    sortiert = sorted(highlights, key=lambda h: (h.get("relevance") or 0),
                      reverse=True)
    return [{
        "title": h.get("title", ""),
        "operator": h.get("operator", ""),
        "url": h.get("url", ""),
        "category": h.get("category", ""),
        "relevance": h.get("relevance"),
        "summary": h.get("summary", ""),
    } for h in sortiert[:anzahl]]


def _teile_antwort(raw: str) -> tuple[str, str, list[str]]:
    """(Abschnitt, Kurzfassung, Topics) aus der Antwort eines Bereichsredakteurs."""
    rest = raw.strip()
    if rest.startswith("```"):
        rest = rest.split("\n", 1)[-1]
        if rest.rstrip().endswith("```"):
            rest = rest.rstrip()[:-3].rstrip()

    topics: list[str] = []
    if "===TOPICS===" in rest:
        rest, _, tail = rest.partition("===TOPICS===")
        try:
            parsed = json.loads(tail.strip().strip("`"))
            if isinstance(parsed, list):
                topics = [str(t) for t in parsed]
        except json.JSONDecodeError:
            log.warning("Themenliste eines Bereichsredakteurs unlesbar")

    kurz = ""
    if "===KURZFASSUNG===" in rest:
        rest, _, kurz = rest.partition("===KURZFASSUNG===")
    return rest.strip(), " ".join(kurz.split()), topics


def _notfall_abschnitt(bereich: str, highlights: list[dict],
                       ueberschrift: str) -> str:
    """Regelbasierter Abschnitt, wenn ein Bereichsredakteur ausfaellt.

    Ein Bereich darf nicht deshalb aus dem Bericht verschwinden, weil EIN
    Aufruf gescheitert ist - die Meldungen sind bewertet, die Quellen stehen
    fest, und der Seen-Store merkt sie sich ohnehin als erledigt. Lieber eine
    nuechterne Liste als ein Loch im Wochenbericht.
    """
    zeilen = [f"{ueberschrift} {bereich}", "",
              "_Dieser Abschnitt konnte in diesem Lauf nicht redaktionell "
              "verdichtet werden; die Meldungen stehen unveraendert mit ihren "
              "Originalquellen._", ""]
    for h in sorted(highlights, key=lambda x: (x.get("relevance") or 0),
                    reverse=True):
        titel = h.get("title", "").strip()
        url = h.get("url", "")
        betreiber = h.get("operator", "")
        text = h.get("summary", "").strip()
        kopf = f"- **{betreiber}**: {titel}" if betreiber else f"- {titel}"
        zeilen.append(f"{kopf} — {text} [Quelle]({url})" if url
                      else f"{kopf} — {text}")
    zeilen.append("")
    return "\n".join(zeilen)


def _ein_bereich(bereich: str, daten: dict, already_covered: list[str],
                 model: str, language: str, ist_thema: bool) -> dict:
    """Einen Bereichsredakteur laufen lassen. Faellt nie hart aus."""
    highlights = daten.get("highlights") or []
    # Themenfelder stehen als H3 unter der gemeinsamen H2; Regionen sind H2.
    ueberschrift = "###" if ist_thema else "##"
    # Ein grosser Bereich darf laenger schreiben als ein kleiner - sonst
    # bekommt Europa mit 40 Meldungen so viel Platz wie Ozeanien mit zweien.
    woerter = max(120, min(600, 60 + 25 * len(highlights)))
    system = BEREICH_SYSTEM.format(bereich=bereich, language=language,
                                   ueberschrift=ueberschrift, woerter=woerter)
    user = json.dumps({
        "bereich": bereich,
        "ist_themenfeld": ist_thema,
        "analyse": {k: v for k, v in daten.items() if not k.startswith("_")},
        "already_covered_topics": already_covered[-300:],
    }, ensure_ascii=False)
    try:
        raw = complete(system, user, model=model, max_tokens=BEREICH_MAX_TOKENS)
        abschnitt, kurz, topics = _teile_antwort(raw)
        if not abschnitt.lstrip().startswith("#"):
            raise ValueError(f"kein Abschnitt mit Ueberschrift: {abschnitt[:120]!r}")
    except (ValueError, RuntimeError, KeyError) as exc:
        log.error("Bereichsredaktion %s gescheitert (%s) - Regelabschnitt",
                  bereich, str(exc)[:160])
        abschnitt = _notfall_abschnitt(bereich, highlights, ueberschrift)
        kurz = str(daten.get("region_summary") or "")[:600]
        topics = [f"{h.get('operator','')}: {h.get('title','')[:120]}"
                  for h in highlights]
    return {"bereich": bereich, "abschnitt": abschnitt, "kurzfassung": kurz,
            "topics": topics, "ist_thema": ist_thema,
            "staerkste": _staerkste(highlights, CHEF_MELDUNGEN_JE_BEREICH),
            "anzahl": len(highlights)}


def synthesize_zweistufig(
        regional: dict[str, dict], already_covered: list[str], model: str,
        language: str = "Deutsch", themenbereiche: list[str] | None = None,
        workers: int = 4) -> tuple[str, list[str]]:
    """Bereichsredakteure parallel, dann Chefredaktion. Wie synthesize()."""
    themen = set(t for t in (themenbereiche or []) if t)
    bereiche = [(name, daten) for name, daten in regional.items()
                if (daten.get("highlights") or [])]
    if not bereiche:
        raise EditorialBriefingError(
            "Keine bewerteten Meldungen - nichts zu redigieren")

    log.info("Zweistufige Redaktion: %d Bereiche (%d davon Themenfelder), "
             "%d bewertete Meldungen, %d parallel",
             len(bereiche), sum(1 for n, _ in bereiche if n in themen),
             sum(len(d.get("highlights") or []) for _, d in bereiche), workers)

    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        ergebnisse = list(pool.map(
            lambda p: _ein_bereich(p[0], p[1], already_covered, model,
                                   language, p[0] in themen),
            bereiche))

    regionen = [e for e in ergebnisse if not e["ist_thema"]]
    themenfelder = [e for e in ergebnisse if e["ist_thema"]]
    # Der groesste Bereich zuerst - er traegt die Woche.
    regionen.sort(key=lambda e: -e["anzahl"])
    themenfelder.sort(key=lambda e: -e["anzahl"])

    # ------------------------------------------------------- Chefredaktion
    chef_eingabe = json.dumps({
        "bereiche": [{"bereich": e["bereich"],
                      "ist_themenfeld": e["ist_thema"],
                      "bewertete_meldungen": e["anzahl"],
                      "kurzfassung": e["kurzfassung"],
                      "staerkste_meldungen": e["staerkste"]}
                     for e in regionen + themenfelder],
        "already_covered_topics": already_covered[-300:],
    }, ensure_ascii=False)
    log.info("Chefredaktion: %d Bereiche, %.0f KB (~%dk Token) - unabhaengig "
             "von der Zahl der Meldungen",
             len(ergebnisse), len(chef_eingabe) / 1024, len(chef_eingabe) // 4000)

    system = CHEF_SYSTEM.format(language=language)
    pflicht = frozenset()  # der Themenabschnitt wird montiert, nicht geschrieben
    try:
        chefteil, chef_topics = _ein_versuch(system, chef_eingabe, model, pflicht)
    except EditorialBriefingError as exc:
        log.warning("Chefredaktion abgelehnt (%s) - ein Korrekturversuch", exc)
        nachfassen = NACHFASSEN[exc.grund]
        chefteil, chef_topics = _ein_versuch(system + nachfassen, chef_eingabe,
                                             model, pflicht)

    # ---------------------------------------------------------- Montage
    # Die Bereichsabschnitte kommen ZWISCHEN "Die wichtigsten Signale" und
    # "Muster der Woche": die Muster sollen die Woche abschliessen, nicht
    # mitten im Bericht stehen.
    kopf, muster = _teile_am_muster(chefteil)
    teile = [kopf.strip(), ""]
    teile += [e["abschnitt"].strip() + "\n" for e in regionen]
    if themenfelder:
        teile.append(THEMEN_H2 + "\n")
        teile += [e["abschnitt"].strip() + "\n" for e in themenfelder]
    if muster:
        teile.append(muster.strip() + "\n")

    markdown = "\n".join(teile).strip() + "\n"
    pflicht_gesamt = frozenset({THEMEN_UEBERSCHRIFT}) if themenfelder else frozenset()
    validate_editorial_briefing(markdown, pflicht_gesamt)

    topics = list(chef_topics)
    for e in ergebnisse:
        topics.extend(e["topics"])
    # Reihenfolge erhalten, Dubletten raus (Chef und Bereich nennen dasselbe).
    gesehen: set[str] = set()
    topics = [t for t in topics if not (t in gesehen or gesehen.add(t))]
    return markdown, topics


def _teile_am_muster(chefteil: str) -> tuple[str, str]:
    """Chefteil vor/ab "## Muster der Woche" trennen.

    Ohne diese Trennung stuenden die Muster der Woche VOR den Regionen - der
    Bericht wuerde mit seinem Fazit enden, bevor die Belege dafuer kommen.
    """
    for zeile in chefteil.splitlines():
        norm = (zeile.strip().lower().replace("ä", "ae")
                .replace("ö", "oe").replace("ü", "ue"))
        if norm.startswith("## muster der woche"):
            pos = chefteil.index(zeile)
            return chefteil[:pos], chefteil[pos:]
    return chefteil, ""


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
