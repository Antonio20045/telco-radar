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
KLICK_FANG = "79,7"
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
    ("Regel", "ansage", 30, ("Was ist", "eigentlich", "KI?")),
    (
        "Regel",
        "satz",
        1130,
        "Ein normales Programm folgt Regeln, die ein Mensch schreibt. "
        "Etwa: Steht „klick“ in der Mail, ist sie Spam.",
    ),
    (
        "Regel",
        "satz",
        1380,
        f"So fängt man {KLICK_FANG} % des Spams. Aber die Regel sperrt auch "
        "echte Mails und übersieht Spam ohne „klick“.",
    ),
    ("Beispiele", "ansage", 1630, ("KI lernt", "aus", "Beispielen")),
    (
        "Beispiele",
        "satz",
        2520,
        "Eine KI bekommt keine Regel, sondern sortierte Mails. "
        "Mit jedem Beispiel rückt sie ihre Trennlinie zurecht.",
    ),
    (
        "Neue Mail",
        "satz",
        bild.KLEIN[3] + 50,
        "Neue Mails ordnet sie nach dieser Linie ein, auch die, an der die "
        f"Regel scheiterte. Gmail traf so 2017 über {GMAIL} %.",
    ),
    (
        "Gelernt",
        "satz",
        3710,
        f"Das Prinzip ist alt: {SAMUEL[0]} brachte sich ein Dame-Programm in "
        f"{SAMUEL[1]} Stunden bei, besser zu spielen als sein Erfinder.",
    ),
    (
        "Gelernt",
        "satz",
        3960,
        "Das ist KI: Ein Programm leitet aus Beispielen selbst ab, was es "
        "tun soll, statt nur Regeln zu befolgen.",
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
