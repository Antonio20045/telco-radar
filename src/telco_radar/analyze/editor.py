"""Redaktion: aus den Analysen der Bereiche wird EIN Wochenbericht.

Zweistufig, seit dem Skalierungs-Auftrag
----------------------------------------
Bis Session 4 bekam ein einziger Editor-Aufruf saemtliche bewerteten
Meldungen. Das hielt bis rund 150 Meldungen. Hochgerechnet auf 1000 Quellen
waeren es ~650 Meldungen, ~477 KB, ~122k Token Eingabe - das passt zwar
formal in das Kontextfenster, ist aber trotzdem der falsche Weg: ein Modell,
das 650 Meldungen zu 1900 Woertern verdichten soll, produziert Brei, ein
einziger fehlgeschlagener Aufruf kostet den ganzen Wochenbericht, und die
Latenz eines 120k-Token-Calls ist nach oben offen.

Deshalb jetzt:

1. **Bereichsredakteure** - ein Aufruf je Region und je Themenfeld, parallel.
   Jeder sieht nur die bewerteten Meldungen SEINES Bereichs und liefert den
   fertigen Bereichsabschnitt plus eine Kurzfassung von 3-5 Saetzen und seine
   staerksten Meldungen.
2. **Chefredaktion** - sieht NUR die Kurzfassungen und die staerksten
   Meldungen je Bereich, nie die Rohliste, und schreibt daraus "Auf einen
   Blick", "Das Wichtigste", "Die wichtigsten Signale" und "Muster der
   Woche".

Damit haengt die Eingabelaenge der Chefredaktion an der Zahl der BEREICHE,
nicht an der Zahl der Meldungen. Die Bereichsabschnitte werden unter den
Chefteil montiert, nicht neu geschrieben.

Faellt ein Bereichsredakteur aus, tritt an seine Stelle ein deterministischer
Abschnitt aus denselben Meldungen - ein Bereich verschwindet nie stumm aus
dem Bericht. Faellt die Chefredaktion aus, greift wie bisher der eine
Korrekturversuch und danach der Notfall-Digest der Pipeline.
"""
from __future__ import annotations

import json
import logging
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import date

from ..models import Item
from .llm import complete, extract_json, llm_available

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

CHEF_SYSTEM = """\
You are the chief editor of "Telco Radar", a weekly global
competitive-intelligence briefing. The point of this briefing is simple:
show what telecommunications companies around the world did this week and
which patterns become visible across regions and operators.

You do NOT see the raw item list. Your section editors have already written
their own sections; you receive per area (region or theme area) a short
summary and that area's strongest items, plus a list of topics ALREADY
covered in previous editions. Your job is the top of the briefing and the
cross-area view - nothing else.

Write in {language} as clean Markdown (no top-level H1; start with H2).
Your readers are managers WITHOUT a technical or AI background: write
plainly, spell out abbreviations on first use, explain the concrete customer
offer or project. This is market observation, not a recommendation memo.
Direct, factual sentences. No filler, no marketing phrases.

Write EXACTLY these four sections, in this order and with these headings:

## Auf einen Blick
Exactly 3 bullet points, one sentence each: the three things a manager with
30 seconds must take away this week.

## Das Wichtigste
4-6 sentences: the most important developments worldwide this week and the
overall picture they form. Name companies and concrete moves.

## Die wichtigsten Signale
The 6-10 most relevant items across ALL areas (relevance 5 first, then 4).
Per item:
**Operator - Titel** (Kategorie, Dringlichkeit X/5)
2-3 sentences of detail (what happened, with numbers/prices/dates when given).
Source as [Quelle](url).

## Muster der Woche
2-4 cross-area patterns in this week's data (e.g. "mehrere Betreiber
buendeln KI-Assistenten in Consumer-Tarife"). Reference the supporting
companies by name.

Rules:
- Write NO area sections. They are added below your text automatically.
  Do not repeat them and do not announce them.
- NEVER re-report a topic from the "already covered" list unless there is a
  genuinely NEW development - then frame it explicitly as "Update zu ...".
- No invented facts, no padding. Use only what is in the input.
- Every factual claim that has a source must carry its [Quelle](url).
- Do not write recommendations, action items or "Fuer Vodafone" sections.
- Keep your four sections under ~900 words together.

After the Markdown, output the line ===TOPICS=== followed by a JSON array of
short topic strings (operator + subject) for every item you covered, so the
system can remember them and never repeat them.
"""

# ---------------------------------------------------------------------------
# Stufe 1: ein Redakteur je Bereich. Zwei Varianten, aus demselben Grund, aus
# dem es zwei Analysten-Prompts gibt: ein Chiphersteller ist kein Wettbewerber
# von Vodafone, und ein Prompt, der ihn dazu erklaert, liefert systematisch
# falsche Saetze ("Preisdruck, den Vodafone kontern muss").
# ---------------------------------------------------------------------------
_BEREICH_GEMEINSAM = """\
Write in {language}. Your readers are managers WITHOUT a technical or AI
background: plain language, spell out abbreviations on first use, explain the
concrete offer or project. Market observation, not a recommendation memo.
No filler, no marketing phrases, no advice for Vodafone.

You receive the assessed items of YOUR area only, plus the topics already
covered in earlier editions. Respond with ONLY valid JSON, no markdown fence:

{{
  "kurzfassung": "<3-5 sentences in {language}: what happened in this area this week and where it points. This is what the chief editor sees - it must stand on its own.>",
  "abschnitt": "<the finished section as Markdown, WITHOUT a heading (the heading is added by the system). Start with 2-3 sentences on the area, then the items, most relevant first, 1-2 sentences each, EVERY one with its [Quelle](url). Use \\n for line breaks.>",
  "top": [
    {{"title": "<verbatim title>", "operator": "<company>", "url": "<verbatim url>", "relevance": <1-5>, "warum": "<one sentence: why this is one of the strongest items of the area>"}}
  ],
  "themen": ["<short topic string per item you covered, e.g. 'Orange: eSIM-Tarif'>"]
}}

Rules:
- "top" holds the {top_n} strongest items at most, relevance 5 first.
- Never invent items or URLs. Use only what is in the input list.
- Items whose topic is already in "already_covered" belong in the section
  only if there is a genuinely new development - then as "Update zu ...".
- Keep the section under ~{woerter} words. Skip weak items rather than
  padding: the weekly briefing must not become a link list.
"""

BEREICH_SYSTEM = """\
You are the section editor for the region "{bereich}" of "Telco Radar", a
weekly global competitive-intelligence briefing for Vodafone Group's strategy
team. You write the section about what competing operators in this region did
this week.
""" + _BEREICH_GEMEINSAM

THEMA_BEREICH_SYSTEM = """\
You are the section editor for the theme area "{bereich}" of "Telco Radar",
a weekly briefing for Vodafone Group's strategy team.

The companies in this area are NOT competing operators. They are suppliers,
device and chip makers, AI providers, satellite operators, regulators or
industry bodies - they shape the market a network operator works in. Write
about what changes for a network OPERATOR: a new network capability, a device
feature customers will ask for, a cost or supply shift, a rule that
constrains or enables an offer. Never present these companies as Vodafone's
competitors.
""" + _BEREICH_GEMEINSAM

# Eigener Abschnitt fuer die Themenfelder (config/tech_sources.yaml). Ohne ihn
# verteilt der Bericht Nvidia-, Qualcomm- und Ofcom-Meldungen zwischen die
# Betreibermeldungen, wo sie untergehen und den Bericht zur Linkliste machen -
# genau das, was der Auftrag verhindern will. Seit der zweistufigen Redaktion
# ist es eine gemeinsame KLAMMER: die Ueberschrift setzt der Code, darunter
# steht je Themenfeld ein H3-Abschnitt seines Redakteurs.
# Die Klammer erscheint NUR, wenn dieser Lauf auch Themenmeldungen hat; sonst
# stuende eine Pflicht-Ueberschrift da, zu der es nichts zu schreiben gibt.
# Deshalb haengen Aufbau und Pflichtpruefung am selben Schalter (siehe
# validate_editorial_briefing).
THEMEN_TITEL = "Technologie, Geräte & Regulierung"
THEMEN_VORSPANN = (
    "_Die folgenden Meldungen stammen nicht von Wettbewerbern, sondern von "
    "Zulieferern, Geräte- und Chipherstellern, KI-Anbietern, "
    "Satellitenbetreibern und Behörden — also von denen, die den Rahmen "
    "setzen, in dem Netzbetreiber arbeiten._"
)

# Ueberschrift dieses Abschnitts, normalisiert wie in
# validate_editorial_briefing (klein, Umlaute aufgeloest).
THEMEN_UEBERSCHRIFT = "## technologie, geraete & regulierung"

# Wie viele Meldungen ein Bereichsredakteur der Chefredaktion vorlegt. Genug,
# dass die Chefredaktion aus jedem Bereich waehlen kann, wenig genug, dass ihre
# Eingabe an der Zahl der BEREICHE haengt und nicht an der Zahl der Meldungen -
# das ist der ganze Zweck der zweiten Stufe.
TOP_JE_BEREICH = 5

# Eigenes Budget je Bereichsabschnitt. Grosszuegig, weil bei 1000 Quellen ein
# Bereich mehrere Dutzend Meldungen tragen kann und ein abgeschnittener
# Abschnitt schlimmer ist als ein langer.
BEREICH_MAX_TOKENS = 12000


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


def _sortiert(highlights: list[dict]) -> list[dict]:
    return sorted(highlights, key=lambda h: (h.get("relevance") or 0),
                  reverse=True)


def _notabschnitt(bereich: str, daten: dict) -> dict:
    """Deterministischer Ersatz, wenn ein Bereichsredakteur ausfaellt.

    Ein Bereich darf nie stumm aus dem Bericht verschwinden: die Meldungen
    sind bewertet, sie stehen im Berichts-JSON, und der Seen-Store hat sie
    als erledigt vermerkt - sie kommen also kein zweites Mal. Lieber eine
    nuechterne Liste mit Quellenlinks als eine Luecke, die aussieht wie eine
    ruhige Woche.
    """
    highlights = _sortiert(daten.get("highlights") or [])
    zeilen: list[str] = []
    if daten.get("region_summary"):
        zeilen.append(str(daten["region_summary"]).strip())
        zeilen.append("")
    zeilen.append("_Dieser Abschnitt wurde ohne redaktionelle Verdichtung "
                  "erzeugt; die Meldungen stehen unverändert mit ihrer "
                  "Originalquelle._")
    zeilen.append("")
    for h in highlights:
        titel = h.get("title") or "(ohne Titel)"
        wer = h.get("operator") or ""
        url = h.get("url") or ""
        text = (h.get("summary") or "").strip()
        kopf = f"- **{wer} – {titel}**" if wer else f"- **{titel}**"
        quelle = f" [Quelle]({url})" if url else ""
        zeilen.append(f"{kopf}: {text}{quelle}".rstrip())
    return {
        "kurzfassung": (str(daten.get("region_summary") or "").strip()
                        or f"{len(highlights)} bewertete Meldungen aus dem "
                           f"Bereich {bereich}, ohne redaktionelle "
                           f"Zusammenfassung."),
        "abschnitt": "\n".join(zeilen),
        "top": [
            {"title": h.get("title"), "operator": h.get("operator"),
             "url": h.get("url"), "relevance": h.get("relevance"),
             "warum": h.get("why_it_matters") or ""}
            for h in highlights[:TOP_JE_BEREICH]
        ],
        "themen": [f"{h.get('operator') or bereich}: "
                   f"{str(h.get('title') or '')[:120]}" for h in highlights],
        "_notfall": True,
    }


def bereichsredaktion(bereich: str, daten: dict, model: str,
                      language: str, already_covered: list[str],
                      ist_thema: bool = False) -> dict:
    """Stufe 1: EIN Bereich, ein Aufruf. Faellt er aus, kommt der Notabschnitt."""
    highlights = _sortiert(daten.get("highlights") or [])
    if not highlights:
        return {"kurzfassung": "", "abschnitt": "", "top": [], "themen": []}
    vorlage = THEMA_BEREICH_SYSTEM if ist_thema else BEREICH_SYSTEM
    system = vorlage.format(bereich=bereich, language=language,
                            top_n=TOP_JE_BEREICH,
                            woerter=min(900, 120 + 45 * len(highlights)))
    user = json.dumps({
        "bereich": bereich,
        "zusammenfassung_der_analysten": daten.get("region_summary", ""),
        "items": highlights,
        "already_covered": already_covered[-300:],
    }, ensure_ascii=False)
    try:
        roh = complete(system, user, model=model, max_tokens=BEREICH_MAX_TOKENS)
        ergebnis = extract_json(roh)
        if not str(ergebnis.get("abschnitt") or "").strip():
            raise ValueError("leerer Abschnitt")
        ergebnis.setdefault("kurzfassung", "")
        ergebnis.setdefault("top", [])
        ergebnis.setdefault("themen", [])
        return ergebnis
    except (ValueError, RuntimeError, KeyError, TypeError) as exc:
        log.error("Bereichsredaktion %s fehlgeschlagen (%s) - Notabschnitt",
                  bereich, str(exc)[:160])
        return _notabschnitt(bereich, daten)


def _tiefer(text: str, mindestens: int) -> str:
    """Ueberschriften eines Bereichsabschnitts unter seine Klammer druecken.

    Der Prompt verlangt einen Abschnitt OHNE eigene Ueberschrift, aber ein
    Modell setzt gelegentlich doch eine. Bliebe sie als H2 stehen, waere die
    Gliederung des Wochenberichts hin: der Abschnitt eines Themenfelds
    stuende dann neben der Themen-Klammer statt darunter, und die
    Pflichtpruefung faende Ueberschriften, die niemand angefordert hat.
    """
    zeilen = []
    for zeile in text.splitlines():
        blank = zeile.lstrip()
        if blank.startswith("#"):
            ebene = len(blank) - len(blank.lstrip("#"))
            if ebene < mindestens:
                zeile = "#" * mindestens + blank.lstrip("#")
        zeilen.append(zeile)
    return "\n".join(zeilen)


def _montiere(chef_markdown: str, regionen: list[tuple[str, str]],
              themen: list[tuple[str, str]]) -> str:
    """Bereichsabschnitte unter den Chefteil setzen.

    "Muster der Woche" bleibt der Schluss des Berichts - die Bereiche werden
    davor eingeschoben. Findet sich die Ueberschrift nicht (dann haette die
    Pruefung ohnehin angeschlagen), haengen die Abschnitte hinten an.
    """
    teile: list[str] = []
    for name, text in regionen:
        teile.append(f"## {name}\n\n{_tiefer(text.strip(), 3)}\n")
    if themen:
        teile.append(f"## {THEMEN_TITEL}\n\n{THEMEN_VORSPANN}\n")
        for name, text in themen:
            teile.append(f"### {name}\n\n{_tiefer(text.strip(), 4)}\n")
    bereiche = "\n".join(teile)
    if not bereiche.strip():
        return chef_markdown

    marke = "## Muster der Woche"
    kopf, treffer, schluss = chef_markdown.partition(marke)
    if not treffer:
        return chef_markdown.rstrip() + "\n\n" + bereiche
    return f"{kopf.rstrip()}\n\n{bereiche}\n{treffer}{schluss}"


def synthesize(regional: dict[str, dict], already_covered: list[str],
               model: str, language: str = "Deutsch",
               highlight_budget: int = EDITOR_HIGHLIGHT_BUDGET,
               themenbereiche: list[str] | None = None,
               bereichs_model: str | None = None,
               bereichs_workers: int = 4) -> tuple[str, list[str]]:
    """Zweistufige Redaktion. Liefert (Markdown-Bericht, behandelte Themen).

    `themenbereiche` sind die Anzeigenamen der Themenfelder, die in DIESEM
    Lauf bewertete Meldungen haben (z. B. ["KI-Anbieter", "Netzausruester"]).
    Ist die Liste leer, entfaellt die Themen-Klammer samt Pflichtpruefung.

    `bereichs_model` ist das Modell der ersten Stufe. Getrennt vom
    Chefredaktions-Modell, weil die erste Stufe die Mengenarbeit ist (ein
    Aufruf je Bereich, bei 1000 Quellen ein Dutzend und mehr) und die zweite
    die Synthese - teures Modell nur dort, wo es den Unterschied macht.
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

    themen_namen = [t for t in (themenbereiche or []) if t]
    mit_inhalt = [rn for rn, r in clean.items() if r.get("highlights")]
    n_highlights = sum(len(clean[rn].get("highlights") or []) for rn in mit_inhalt)

    # ------------------------------------------------ Stufe 1: die Bereiche
    stufe1 = bereichs_model or model
    log.info("Bereichsredaktion: %d Bereiche, %d bewertete Meldungen, "
             "Modell=%s, %d parallel",
             len(mit_inhalt), n_highlights, stufe1, bereichs_workers)
    ergebnisse: dict[str, dict] = {}
    if mit_inhalt:
        with ThreadPoolExecutor(max_workers=max(1, bereichs_workers)) as pool:
            gestartet = {
                rn: pool.submit(bereichsredaktion, rn, clean[rn], stufe1,
                                language, already_covered,
                                rn in themen_namen)
                for rn in mit_inhalt
            }
            for rn, fut in gestartet.items():
                try:
                    ergebnisse[rn] = fut.result()
                except Exception as exc:  # noqa: BLE001 - nie den Lauf kosten
                    log.error("Bereichsredaktion %s abgestuerzt: %s", rn, exc)
                    ergebnisse[rn] = _notabschnitt(rn, clean[rn])
    notfaelle = sum(1 for e in ergebnisse.values() if e.get("_notfall"))
    if notfaelle:
        log.warning("%d von %d Bereichsabschnitten kommen aus dem "
                    "Notfallweg (ohne redaktionelle Verdichtung)",
                    notfaelle, len(ergebnisse))

    # ---------------------------------------------- Stufe 2: Chefredaktion
    bereiche_fuer_chef = [
        {"bereich": rn,
         "art": "Themenfeld" if rn in themen_namen else "Region",
         "kurzfassung": ergebnisse[rn].get("kurzfassung", ""),
         "staerkste_meldungen": ergebnisse[rn].get("top", [])[:TOP_JE_BEREICH]}
        for rn in mit_inhalt if ergebnisse.get(rn)
    ]
    payload = {
        "bereiche": bereiche_fuer_chef,
        "already_covered_topics": already_covered[-300:],
    }
    if omitted:
        payload["note"] = (
            f"{omitted} further assessed items were left out of this payload "
            "because they scored lower on relevance. They are published in the "
            "report data, so do not claim this is everything that happened."
        )
    user = json.dumps(payload, ensure_ascii=False)
    # Die Zahl, an der sich der ganze Umbau messen laesst: sie haengt jetzt an
    # der Zahl der Bereiche, nicht mehr an der Zahl der Meldungen.
    log.info("Chefredaktion: %d Bereiche, %.0f KB (~%dk Token), Modell=%s",
             len(bereiche_fuer_chef), len(user) / 1024, len(user) // 4000, model)

    system = CHEF_SYSTEM.format(language=language)
    try:
        chef_md, themen_chef = _ein_versuch(system, user, model)
    except EditorialBriefingError as exc:
        # Der Wochenbericht ist das Herzstueck der Seite. Ihn beim ersten
        # Formfehler wegzuwerfen und stattdessen den Roh-Digest zu
        # veroeffentlichen, ist die teuerste moegliche Reaktion - der Inhalt
        # war ja da, nur die Gliederung stimmte nicht. Also einmal gezielt
        # nachfassen, mit den Ueberschriften woertlich im Auftrag.
        log.warning("Editor-Ausgabe abgelehnt (%s) - ein Korrekturversuch", exc)
        chef_md, themen_chef = _ein_versuch(
            system + NACHFASSEN[exc.grund], user, model)

    # ------------------------------------------------------------- Montage
    regionen = [(rn, ergebnisse[rn]["abschnitt"]) for rn in mit_inhalt
                if rn not in themen_namen and ergebnisse[rn].get("abschnitt")]
    themen = [(rn, ergebnisse[rn]["abschnitt"]) for rn in mit_inhalt
              if rn in themen_namen and ergebnisse[rn].get("abschnitt")]
    bericht = _montiere(chef_md, regionen, themen)

    pflicht = frozenset({THEMEN_UEBERSCHRIFT}) if themen else frozenset()
    validate_editorial_briefing(bericht, pflicht)

    themen_gesamt = list(themen_chef)
    for rn in mit_inhalt:
        themen_gesamt.extend(str(t) for t in (ergebnisse[rn].get("themen") or []))
    # Reihenfolge erhalten, Dubletten raus - das Themengedaechtnis ist eine
    # Liste, keine Menge, und derselbe Eintrag zweimal verkuerzt es nur.
    gesehen: set[str] = set()
    eindeutig = [t for t in themen_gesamt
                 if not (t in gesehen or gesehen.add(t))]
    return bericht, eindeutig


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
