"""Das Blatt der KI-Seite (Pitch 9, Entwurf 10, Schnitt 2).

Jede KI-Meldung bekommt genau ein KI-Ressort, ohne LLM über Stichworte:
zuerst „KI im Mobilfunk“ (Netzbetreiber aus der Watchlist oder
Telco-Stichworte), dann die Ressorts in der Reihenfolge von ``STICHWORTE``,
erst an der Schlagzeile, dann am Kurztext; ohne Treffer „Produkte“.

Meldungen bleiben stehen wie in einer Zeitung: je Ressort stehen die
neuesten ``HOECHSTENS_JE_RESSORT`` im Blatt, die älteren im Archiv. Das
Blatt wird aus allen gespeicherten Berichten abgeleitet, es gibt keinen
eigenen Store.

Unter dem Kopf der Seite steht das Blatt in Kapiteln (``kapitel()``), je
Ressort eins mit eigenem Bild ``ki-<schluessel>``: der neueste Aufmacher,
daneben höchstens ``NEBEN_JE_KAPITEL`` weitere, der Rest zugeklappt. Die
Kapitel folgen fest ``KAPITEL_FOLGE`` wie die Ressorts einer Zeitung: der
Leser findet ein Ressort in jeder Ausgabe an derselben Stelle, und „KI im
Mobilfunk“, das Geschäft der Leser, steht vorn statt zuletzt.
"""

from __future__ import annotations

import re
from collections.abc import Iterable

HOECHSTENS_JE_RESSORT = 12
NEBEN_JE_KAPITEL = 3
MOBILFUNK = "KI im Mobilfunk"
FALLBACK = "Produkte"
RESSORTS = (
    "Modelle",
    "Chips & Rechenzentren",
    "Start-ups & Geld",
    "Produkte",
    "Regeln & Recht",
    "Forschung",
    MOBILFUNK,
)
KAPITEL_FOLGE = (
    MOBILFUNK,
    "Modelle",
    "Chips & Rechenzentren",
    "Start-ups & Geld",
    "Produkte",
    "Regeln & Recht",
    "Forschung",
)
SCHLUESSEL = {
    MOBILFUNK: "mobilfunk",
    "Modelle": "modelle",
    "Chips & Rechenzentren": "chips",
    "Start-ups & Geld": "startups",
    "Produkte": "produkte",
    "Regeln & Recht": "regeln",
    "Forschung": "forschung",
}
TELCO_STICHWORTE = (
    r"telco|telekom|telecom|mobilfunk|netzbetreiber|operator|carrier|[56]g\b|ai-ran|o-ran"
    r"|open ran|ran\b|spectrum|spektrum|glasfaser|fib(?:re|er)|broadband|breitband"
    r"|network|netzwerk|netz\b"
)
STICHWORTE: tuple[tuple[str, str], ...] = (
    (
        "Regeln & Recht",
        r"regel|regul|gesetz|laws?\b|ai act|aufsicht|behörde|kommission|commission"
        r"|polic|politi|govern|regier|court|gericht|klage|lawsuit|urheberrecht|copyright"
        r"|datenschutz|privacy|verbot|ban\b|minist",
    ),
    (
        "Chips & Rechenzentren",
        r"chip|halbleiter|semiconductor|gpus?\b|nvidia|tsmc|rechenzentr"
        r"|data ?cent|datacent|rechenleistung|compute\b|gigafactor"
        r"|memory|speicher|server|infrastru|capex",
    ),
    (
        "Start-ups & Geld",
        r"start-?ups?\b|funding|finanzier|invest|milliard|million|billion|\$|\d+ ?bn\b"
        r"|valuation|übernahme|acqui|ipo\b|börse|aktie|stock|revenue|umsatz|earnings"
        r"|gewinn|profit|kapital|capital",
    ),
    (
        "Forschung",
        r"forsch|research|studie|study|paper|wissenschaft|scien|universit|benchmark",
    ),
    (
        "Modelle",
        r"modell|sprachmodell|models?\b|llms?\b|gpt|claude|gemini|llama|mistral|deepseek|qwen|grok"
        r"|open-weight|reasoning",
    ),
)


def _muster(stichworte: str) -> re.Pattern[str]:
    return re.compile(rf"(?<!\w)(?:{stichworte})", re.I)


_TELCO = _muster(TELCO_STICHWORTE)
_RESSORT_MUSTER = tuple((name, _muster(worte)) for name, worte in STICHWORTE)


def netzbetreiber(cfg) -> frozenset[str]:
    """Namen und Aliasse der Netzbetreiber aus der Watchlist; leer ohne cfg."""
    if cfg is None:
        return frozenset()
    return frozenset(name for op in cfg.operators for name in op.match_terms)


def _ist_netzbetreiber(operator: str, namen: frozenset[str]) -> bool:
    teile = re.split(r"\s*[,/&]\s*", operator.strip())
    return operator.strip() in namen or any(t in namen for t in teile)


def ressort(h: dict, namen: frozenset[str]) -> str:
    """Genau ein KI-Ressort je Meldung; ohne Stichwort „Produkte“."""
    if _ist_netzbetreiber(h.get("operator") or "", namen):
        return MOBILFUNK
    schlagzeile = f"{h.get('schlagzeile') or ''} {h.get('title') or ''}"
    for text in (schlagzeile, h.get("summary") or ""):
        if _TELCO.search(text):
            return MOBILFUNK
        for name, muster in _RESSORT_MUSTER:
            if muster.search(text):
                return name
    return FALLBACK


def blatt(
    meldungen: Iterable[dict], namen: frozenset[str]
) -> tuple[list[dict], list[dict]]:
    """(Blatt, Archiv), beide neueste zuerst; je Ressort höchstens zwölf im Blatt."""
    geordnet = sorted(meldungen, key=lambda h: h["ki_datum"], reverse=True)
    stehen: list[dict] = []
    archiv: list[dict] = []
    je_ressort: dict[str, int] = dict.fromkeys(RESSORTS, 0)
    for h in geordnet:
        name = ressort(h, namen)
        je_ressort[name] += 1
        ziel = stehen if je_ressort[name] <= HOECHSTENS_JE_RESSORT else archiv
        ziel.append(dict(h, ki_ressort=name))
    return stehen, archiv


def kapitel(meldungen: Iterable[dict]) -> list[dict]:
    """Je Ressort mit Meldung ein Kapitel in ``KAPITEL_FOLGE``.

    ``meldungen`` sind Blattmeldungen mit ``ki_ressort``, neueste zuerst; die
    Reihenfolge bleibt in jedem Kapitel erhalten. Ein Ressort ohne Meldung
    entfällt.
    """
    je_ressort: dict[str, list[dict]] = {name: [] for name in KAPITEL_FOLGE}
    for h in meldungen:
        je_ressort[h["ki_ressort"]].append(h)
    return [
        {
            "name": name,
            "schluessel": SCHLUESSEL[name],
            "aufmacher": eigene[0],
            "neben": eigene[1 : 1 + NEBEN_JE_KAPITEL],
            "weitere": eigene[1 + NEBEN_JE_KAPITEL :],
        }
        for name, eigene in je_ressort.items()
        if eigene
    ]
