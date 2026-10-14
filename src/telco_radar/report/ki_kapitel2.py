"""Kapitel 2 der KI-Seite: „Was ist eigentlich KI?“ (Pitch 9, Anhang Kapitel 1).

Eine eigene Seite ``ki-kapitel-2.html`` in der Machart von Kapitel 1: Regel
gegen gelernte Trennlinie am Beispiel Spam. Die Geometrie rechnet
``ki_kapitel2_bild``. Jede Zahl in einem Satz steht in ``QUELLEN`` mit ihrer
Originalquelle; die Recherche liegt im Projektordner unter
``pitches/ki/kapitel-recherche.md``.
"""

from __future__ import annotations

from . import ki_kapitel
from . import ki_kapitel2_bild as bild

DATEI = "ki-kapitel-2.html"
NUMMER = 2
TITEL = "Was ist eigentlich KI?"
STATIONEN = ("Regel", "Beispiele", "Neue Mail", "Gelernt")
BESCHREIBUNG = "Zeichnung: eine starre Regel gegen eine gelernte Trennlinie"
KLICK_FANG, KLICK_FALSCH = "79,7", "1,2"
GMAIL = "99,9"
SAMUEL = ("1959", "8 bis 10")
QUELLEN = (
    ("Paul Graham, A Plan for Spam (2002)", "https://paulgraham.com/spam.html"),
    (
        "Google, Gmail-Sicherheit (2017)",
        "https://blog.google/products/g-suite/"
        "keeping-your-company-data-safe-new-security-updates-gmail/",
    ),
    (
        "A. L. Samuel, IBM Journal (1959)",
        "https://people.csail.mit.edu/brooks/idocs/Samuel.pdf",
    ),
    (
        "EU-KI-Verordnung, Art. 3 Nr. 1",
        "https://eur-lex.europa.eu/eli/reg/2024/1689/oj",
    ),
)
TEXTE = (
    ("Regel", "ansage", 30, ("Früher", "schrieb man", "Regeln")),
    (
        "Regel",
        "satz",
        1130,
        f"Die Regel „klick“ fängt {KLICK_FANG} % des Spams. Aber sie sperrt "
        f"{KLICK_FALSCH} % echte Mails und lässt neuen Spam durch.",
    ),
    ("Beispiele", "ansage", 1380, ("Eine KI", "lernt aus", "Beispielen")),
    (
        "Beispiele",
        "satz",
        2270,
        "Mit jedem Beispiel dreht sich ihre Trennlinie. "
        "Niemand schreibt sie als Regel hin.",
    ),
    (
        "Neue Mail",
        "satz",
        bild.KLEIN[3] + 50,
        "Die Mail, die der Regel entwischt ist, landet im Spam. "
        f"Gmail sortierte 2017 so über {GMAIL} % richtig.",
    ),
    (
        "Gelernt",
        "satz",
        3460,
        f"{SAMUEL[0]} lernte ein Dame-Programm von Arthur Samuel in {SAMUEL[1]} "
        "Stunden, besser zu spielen als er selbst.",
    ),
    (
        "Gelernt",
        "satz",
        3700,
        "Genau das meint die EU: Ein KI-System leitet aus Eingaben ab, was es ausgibt.",
    ),
    ("Gelernt", "ansage", bild.ENDE - 410, ("Nicht", "befohlen,", "gelernt")),
)


def seite(env, kapitel: list[dict]) -> str:
    """Das HTML von ``ki-kapitel-2.html``."""
    return ki_kapitel.rendere(
        env,
        kapitel,
        NUMMER,
        TITEL,
        bild=dict(bild.zeichnung(STATIONEN), texte=ki_kapitel.texte(TEXTE, bild.HOEHE)),
        beschreibung=BESCHREIBUNG,
        quellen=QUELLEN,
    )
