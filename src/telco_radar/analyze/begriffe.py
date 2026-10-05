"""Feste Begriffe der Analyse, die auch die Seite braucht.

Das Modul importiert weder das LLM noch das Netz, damit `report/` es lesen
darf, ohne über den Analyseweg an `httpx` zu hängen.
"""

from __future__ import annotations

import re

MECHANICS: dict[str, str] = {
    "wechselpraemie": "Wechsel- oder Altgerätprämie",
    "geraetesubvention": "Gerät vergünstigt",
    "preisnachlass": "Preisnachlass auf den Tarif",
    "datenbonus": "mehr Datenvolumen",
    "gebuehrenerlass": "Gebühren erlassen",
    "zugabe": "Gratis-Zugabe",
    "bindungsfrei": "ohne Bindung",
    "zielgruppe": "Zielgruppentarif",
    "sonstiges": "sonstiges",
}

DIGEST_MARKER = "Für diesen Lauf liegt kein Redaktionstext vor."

THEMES = [
    ("ki", "KI & Assistenten"),
    ("entertainment", "Entertainment & Streaming"),
    ("garantie", "Garantie & Service-Versprechen"),
    ("geraete", "Geräte-Programme & Zubehör"),
    ("security", "Security & Betrugsschutz"),
    ("fintech", "Fintech & Payment"),
    ("superapp", "Super-App & Ökosystem"),
    ("cloud", "Cloud & Speicher"),
    ("smarthome", "Smart Home & IoT"),
    ("gaming", "Gaming"),
    ("loyalty", "Loyalty & Perks"),
    ("health", "Health & Wellbeing"),
]
THEME_LABEL = dict(THEMES)

MIND_TREFFER = 2


def suchmuster(suchwoerter) -> list[re.Pattern]:
    """Wortgrenzen-Muster je Suchwort - dieselbe Regel wie in
    analyze/competitors.py. Ohne die Grenzen faende "fold" jedes "Foldable"
    und "O2" jedes "CO2"."""
    muster = []
    for w in suchwoerter or []:
        w = " ".join(str(w or "").split())
        if len(w) >= 2:
            muster.append(re.compile(r"(?<!\w)" + re.escape(w.lower()) + r"(?!\w)"))
    return muster


def treffer(text: str, muster: list[re.Pattern]) -> int:
    """Wie viele VERSCHIEDENE Suchwoerter in diesem Text vorkommen."""
    t = (text or "").lower()
    return sum(1 for p in muster if p.search(t))
