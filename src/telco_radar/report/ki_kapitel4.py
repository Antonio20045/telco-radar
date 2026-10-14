"""Kapitel 4 der KI-Seite: „Warum sie würfelt“ (Pitch 9, Anhang Kapitel 4).

Eine eigene Seite ``ki-kapitel-4.html`` in der Machart von Kapitel 1:
dieselbe Frage, ein Würfel, drei Temperaturen, fünf Versuche. Die Geometrie
und jede Prozentzahl rechnet ``ki_kapitel4_bild``. Quellen in ``QUELLEN``,
Recherche im Projektordner unter ``pitches/ki/kapitel-recherche.md``.
"""

from __future__ import annotations

from . import ki_kapitel
from . import ki_kapitel4_bild as bild

DATEI = "ki-kapitel-4.html"
NUMMER = 4
TITEL = "Warum sie würfelt"
STATIONEN = ("Würfel", "Temperatur", "Ziehen")
BESCHREIBUNG = "Zeichnung: wie die Temperatur das Würfeln der KI verändert"
QUELLEN = (
    (
        "Hinton, Vinyals, Dean: Distilling the Knowledge (2015)",
        "https://arxiv.org/abs/1503.02531",
    ),
    (
        "Anthropic, Messages-API: temperature",
        "https://platform.claude.com/docs/en/api/messages",
    ),
)
KALT, HEISS = bild.TEMPERATUREN[-1][0], bild.TEMPERATUREN[0][0]
TEXTE = (
    ("Würfel", "ansage", 30, ("Warum", "würfelt", "sie?")),
    (
        "Würfel",
        "satz",
        1060,
        "Für das nächste Wort kennt sie nur Wahrscheinlichkeiten. "
        "Daraus zieht sie wie mit einem gezinkten Würfel.",
    ),
    ("Temperatur", "ansage", 1440, ("Ein Regler", "für den", "Zufall")),
    (
        "Temperatur",
        "satz",
        bild.ROHR[2] + 120,
        f"Der Regler heißt Temperatur. Kalt gewinnt „Ja“ "
        f"{bild.prozent(bild.verteilung(KALT)[0][1])}, heiß nur "
        f"{bild.prozent(bild.verteilung(HEISS)[0][1])}: Dann kommt Seltenes dran.",
    ),
    (
        "Ziehen",
        "satz",
        bild.ZUG_Y + 340,
        "Fünfmal gefragt, fünfmal gewürfelt: meist „Ja“, manchmal etwas "
        "anderes. Darum klingt sie nie ganz gleich.",
    ),
    (
        "Ziehen",
        "satz",
        bild.ZUG_Y + 580,
        "Für Fakten stellt man sie kalt, für Ideen warm. "
        "Ganz ohne Zufall ist sie laut Anthropic nie.",
    ),
    ("Ziehen", "ansage", bild.ENDE - 410, ("Fakten kalt", "Ideen", "warm")),
)


def seite(env, kapitel: list[dict]) -> str:
    """Das HTML von ``ki-kapitel-4.html``."""
    return ki_kapitel.rendere(
        env,
        kapitel,
        NUMMER,
        TITEL,
        bild=dict(bild.zeichnung(STATIONEN), texte=ki_kapitel.texte(TEXTE, bild.HOEHE)),
        beschreibung=BESCHREIBUNG,
        quellen=QUELLEN,
    )
