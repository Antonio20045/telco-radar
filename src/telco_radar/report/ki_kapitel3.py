"""Kapitel 3 der KI-Seite: „Wie eine KI lernt“ (Pitch 9, Anhang Kapitel 2).

Eine eigene Seite ``ki-kapitel-3.html`` in der Machart von Kapitel 1: Raten
und Nachstellen, Textproben nach wachsenden Runden, Rechenzeit, feste
Stellschrauben beim Benutzen. Die Geometrie rechnet ``ki_kapitel3_bild``.
Jede Zahl steht in ``QUELLEN`` mit ihrer Originalquelle; die Recherche liegt
im Projektordner unter ``pitches/ki/kapitel-recherche.md``. Die Jahre auf
einem Chip rechnet ``chip_jahre()`` aus den Stunden der Model Card.
"""

from __future__ import annotations

from . import ki_kapitel
from . import ki_kapitel3_bild as bild

DATEI = "ki-kapitel-3.html"
NUMMER = 3
TITEL = "Wie eine KI lernt"
STATIONEN = ("Raten", "Runden", "Rechenzeit", "Benutzen")
BESCHREIBUNG = "Zeichnung: wie eine KI durch Raten und Nachstellen lernt"
CHIP_STUNDEN_MIO = 30.84
STUNDEN_JE_JAHR = 365 * 24
QUELLEN = (
    (
        "A. Karpathy, RNN-Textproben (2015)",
        "https://karpathy.github.io/2015/05/21/rnn-effectiveness/",
    ),
    (
        "Meta, Llama 3.1 Model Card (2024)",
        "https://github.com/meta-llama/llama-models/blob/main/"
        "models/llama3_1/MODEL_CARD.md",
    ),
)


def chip_jahre() -> int:
    """Volle Jahre, die ein einzelner Chip für das Training bräuchte."""
    return int(CHIP_STUNDEN_MIO * 1_000_000 // STUNDEN_JE_JAHR)


def _zahl(n: int) -> str:
    return f"{n:,}".replace(",", ".")


def _komma(x: float) -> str:
    return f"{x:.2f}".replace(".", ",")


TEXTE = (
    ("Raten", "ansage", 30, ("Wie lernt", "eine", "KI?")),
    (
        "Raten",
        "satz",
        1000,
        "Sie liest echten Text und rät immer das nächste Zeichen. "
        "Nach „Vertra“ tippt sie „k“, richtig wäre „g“.",
    ),
    (
        "Raten",
        "satz",
        1250,
        "Liegt sie falsch, stellt sie ihre Stellschrauben ein Stück nach, "
        "damit es beim nächsten Mal eher passt.",
    ),
    ("Runden", "ansage", 1500, ("Runde", "für", "Runde")),
    (
        "Runden",
        "satz",
        bild.KARTE_Y[-1] + 90,
        "Ein kleines Modell, das „Krieg und Frieden“ las, schrieb nach "
        f"{bild.PROBEN[0][0]} Runden Salat, nach {bild.PROBEN[-1][0]} fast Englisch.",
    ),
    (
        "Rechenzeit",
        "satz",
        3150,
        f"Große Modelle üben an Billionen Textstücken. Llama 3.1 brauchte "
        f"{_komma(CHIP_STUNDEN_MIO)} Mio. Chip-Stunden, ein Chip allein über "
        f"{_zahl(chip_jahre())} Jahre.",
    ),
    (
        "Benutzen",
        "satz",
        3850,
        "Danach ist das Lernen vorbei. Wenn du sie fragst, bleiben die "
        "Stellschrauben fest: Sie wendet nur an.",
    ),
    ("Benutzen", "ansage", bild.ENDE - 410, ("Erst lernen", "dann", "arbeiten")),
)


def seite(env, kapitel: list[dict]) -> str:
    """Das HTML von ``ki-kapitel-3.html``."""
    return ki_kapitel.rendere(
        env,
        kapitel,
        NUMMER,
        TITEL,
        bild=dict(bild.zeichnung(STATIONEN), texte=ki_kapitel.texte(TEXTE, bild.HOEHE)),
        beschreibung=BESCHREIBUNG,
        quellen=QUELLEN,
    )
