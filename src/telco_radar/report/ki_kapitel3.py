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


def _runden() -> str:
    werte = [str(r) for r, _ in bild.PROBEN]
    return ", ".join(werte[:-1]) + " und " + werte[-1]


TEXTE = (
    ("Raten", "ansage", 30, ("Lernen", "heißt", "raten")),
    (
        "Raten",
        "satz",
        1000,
        "Sie rät das nächste Zeichen eines echten Textes. "
        "Liegt sie falsch, dreht sie ihre Stellschrauben ein wenig.",
    ),
    ("Runden", "ansage", 1250, ("Runde", "für", "Runde")),
    (
        "Runden",
        "satz",
        2340,
        f"So schrieb ein kleines Modell nach {_runden()} Runden, "
        "gelernt aus „Krieg und Frieden“.",
    ),
    (
        "Rechenzeit",
        "satz",
        2900,
        f"Llama 3.1 brauchte {_komma(CHIP_STUNDEN_MIO)} Mio. Chip-Stunden. "
        f"Ein einzelner Chip säße über {_zahl(chip_jahre())} Jahre daran.",
    ),
    (
        "Benutzen",
        "satz",
        3600,
        "Beim Benutzen bleiben die Stellschrauben fest. "
        "Was du ihr sagst, lernt sie dabei nicht dazu.",
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
