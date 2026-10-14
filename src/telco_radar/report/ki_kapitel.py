"""Kapitel 1 der KI-Seite: „Wie eine KI antwortet“ (Pitch 9, Schnitte 10–12).

Eine eigene Seite ``ki-kapitel-1.html``: eine lange Linienzeichnung im
Zajno-Stil, durch die man scrollt, ein roter Punkt führt. Die Stationen
stehen in ``STATIONEN``: Frage, Wörter (Tokens), Bedeutung (Karte),
Aufmerksamkeit, Antwort. Die Geometrie rechnet ``ki_kapitel_bild``; hier
stehen Ansagen und Sätze, die als HTML über der Zeichnung liegen (``top`` in
Prozent ihrer Höhe). Ihre Lücken in der Zeichnung sind so gewählt, dass auch
bei 390 px kein Satz auf einer Pille oder Beschriftung liegt.
"""

from __future__ import annotations

from . import ki_kapitel_bild as bild

VORLAGE = "ki-kapitel.html.j2"
DATEI = "ki-kapitel-1.html"
NUMMER = 1
TITEL = "Wie eine KI antwortet"
STATIONEN = ("Frage", "Wörter", "Bedeutung", "Aufmerksamkeit", "Antwort")
BESCHREIBUNG = "Zeichnung: wie eine KI aus einer Frage eine Antwort macht"
TEXTE = (
    ("Frage", "ansage", 30, ("Eine KI", "liest keine", "Wörter")),
    (
        "Wörter",
        "satz",
        925,
        "Zuerst zerschneidet sie deinen Satz in Stücke, die Tokens. "
        "Jedes Stück bekommt eine Nummer.",
    ),
    (
        "Bedeutung",
        "satz",
        1745,
        "Jede Nummer ist ein Ort auf einer Karte der Bedeutungen. "
        "Ähnliches liegt nah beieinander.",
    ),
    ("Aufmerksamkeit", "ansage", 1960, ("Jedes Wort", "schaut die", "anderen an")),
    (
        "Aufmerksamkeit",
        "satz",
        2750,
        "Jedes Stück schaut, welche anderen für es zählen. "
        "„künd“ achtet vor allem auf „Vertrag“.",
    ),
    (
        "Antwort",
        "satz",
        bild.WAHL_Y + 95,
        "Am Ende rechnet sie aus, welches Wort am wahrscheinlichsten folgt.",
    ),
    (
        "Antwort",
        "satz",
        bild.ANTWORT_Y + 120,
        "Dann hängt sie das Wort an und rechnet weiter. Für jedes einzelne Wort.",
    ),
    (
        "Antwort",
        "ansage",
        bild.ANTWORT_Y + 350,
        ("So entsteht", "jede Antwort.", "Wort für Wort"),
    ),
)


def texte(eintraege=TEXTE, hoehe: float = bild.HOEHE) -> list[dict]:
    """Ansagen und Sätze mit ihrer Höhe in der Zeichnung und als Prozentwert."""
    out = []
    for station, art, y, inhalt in eintraege:
        eintrag = {"station": station, "art": art, "y": y}
        eintrag["top"] = round(y / hoehe * 100, 3)
        eintrag["zeilen" if art == "ansage" else "text"] = inhalt
        out.append(eintrag)
    return out


def rendere(env, kapitel: list[dict], nummer: int, titel: str, **teile) -> str:
    """Eine Kapitelseite: ``teile`` sind ``bild``, ``beschreibung``, ``quellen``.

    ``kapitel`` ist die Schiene der KI-Seite; „Weiter“ führt zum nächsten
    fertigen Kapitel, sonst zurück zu allen.
    """
    weiter = next((k for k in kapitel if k["nr"] == nummer + 1 and k["ziel"]), None)
    return env.get_template(VORLAGE).render(
        prefix="", nummer=nummer, titel=titel, weiter=weiter, **teile
    )


def seite(env, kapitel: list[dict]) -> str:
    """Das HTML von ``ki-kapitel-1.html``; ``kapitel`` ist die Schiene der KI-Seite."""
    return rendere(
        env,
        kapitel,
        NUMMER,
        TITEL,
        bild=dict(bild.zeichnung(STATIONEN), texte=texte()),
        beschreibung=BESCHREIBUNG,
        quellen=(),
    )
