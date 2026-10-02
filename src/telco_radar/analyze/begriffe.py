"""Feste Begriffe der Analyse, die auch die Seite braucht.

Das Modul importiert weder das LLM noch das Netz, damit `report/` es lesen
darf, ohne über den Analyseweg an `httpx` zu hängen.
"""

from __future__ import annotations

import re

# Geschlossene Mechanik-Liste fuer Achse D. Bewusst klein und trennscharf:
# die Achse zaehlt, wie viele ANDERE Marken gerade dieselbe Mechanik fahren,
# und das funktioniert nur mit einem festen Vokabular. Alles, was nicht
# eindeutig passt, faellt auf "sonstiges" und traegt damit nichts bei.
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

# Der Digest ist KEIN Redaktionstext, und er darf auch nicht so aussehen.
# Bis zum 07.08.2026 stand er unter derselben Ueberschrift und in derselben
# Form wie die Prosa des Editors - die Promo-Uebersicht schnitt daraus ihren
# Vorspann und zeigte am 06.08. "ALDI TALK imoo Kinder-Smartwatch kaufen + 2
# MovieChoice-Kinogutscheine ALDI TALK - imoo Kinder-Smartwatch kaufen + 2
# MovieChoice-Kinogutscheine ." - derselbe Titel zweimal, mit freistehendem
# Punkt. Der Fehler lag nicht im Schnitt, sondern hier: der Titel stand
# zweimal in der Zeile (einmal blank, einmal als Linktext), und nichts sagte
# der Seite, dass sie keine Saetze vor sich hat.
DIGEST_MARKER = "Für diesen Lauf liegt kein Redaktionstext vor."

# Hebel-Definitionen (Key -> Anzeige) — Reihenfolge = Anzeige-Reihenfolge.
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

# Wie viele Suchwoerter eine neue Meldung treffen muss, um einem Thema
# zugeordnet zu werden. Eins reicht nicht: "Samsung" allein zieht jede
# Geraetemeldung des Herstellers in den Launch der Z-Fold-Reihe.
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
