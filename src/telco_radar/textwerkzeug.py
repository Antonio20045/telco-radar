"""Textwerkzeuge, die Anzeige UND Analyse teilen.

Zwei Stellen im Projekt rechnen dasselbe aus, und beide muessen es gleich
ausrechnen:

  * `report/html._faden()` sucht zu jedem Fuehrungssatz des Wochenberichts
    die Meldung, die ihn belegt.
  * `analyze/highlight_topics` sucht Gruppen von Meldungen, die dasselbe
    Ereignis beschreiben.

Beide beantworten die Frage "reden diese zwei Texte von derselben Sache?",
und beide beantworten sie ueber SELTENE gemeinsame Woerter. Ein Abgleich
ueber alle Woerter faende "Netz", "Kunden" und "Milliarden" in jeder zweiten
Meldung; gezaehlt reicht auch nicht, GEWICHTET muss es sein - ein Wort, das
genau zweimal vorkommt, beweist mehr als eines, das siebzehnmal vorkommt.
Deshalb 1/Haeufigkeit (die ausfuehrliche Begruendung mit dem gemessenen
Fehlgriff steht bei `_faden()`).

Der Slug steht aus demselben Grund hier: die Berichtsabschnitte
(`_anchor_headings`) und die Themenseiten (`site/thema/<slug>.html`) muessen
denselben Anker aus demselben Titel erzeugen - zwei Fassungen davon waeren
zwei Fassungen der URLs, die in Mails stehen.
"""
from __future__ import annotations

import re

_SLUG_MAP = str.maketrans({"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss",
                           "Ä": "ae", "Ö": "oe", "Ü": "ue"})

# Vier Zeichen Mindestlaenge: kuerzer sind im Deutschen fast nur Fuellwoerter
# ("der", "und", "mit"), und die traegt der Haeufigkeitsdeckel ohnehin aus.
WORT_RE = re.compile(r"[\wÄÖÜäöüß][\wÄÖÜäöüß-]{3,}")


def slug(text: str) -> str:
    """Stabiler Anker aus einer Ueberschrift ("Afrika & Naher Osten" ->
    "afrika-naher-osten"). Muss ueber Laeufe hinweg gleich bleiben - die
    Anker landen in Mails."""
    s = (text or "").strip().lower().translate(_SLUG_MAP)
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s or "abschnitt"


def wortmenge(text: str) -> set[str]:
    """Die inhaltstragenden Woerter eines Textes, kleingeschrieben."""
    return {w.lower() for w in WORT_RE.findall(text or "")}


def haeufigkeiten(mengen) -> dict[str, int]:
    """Wie oft jedes Wort in wie vielen der Wortmengen vorkommt."""
    zaehler: dict[str, int] = {}
    for menge in mengen:
        for w in menge:
            zaehler[w] = zaehler.get(w, 0) + 1
    return zaehler


def gewicht(woerter, haeufigkeit: dict[str, int]) -> float:
    """Beweiskraft gemeinsamer Woerter: jeder Treffer zaehlt 1/Haeufigkeit."""
    return round(sum(1.0 / haeufigkeit[w] for w in woerter if haeufigkeit.get(w)), 6)
