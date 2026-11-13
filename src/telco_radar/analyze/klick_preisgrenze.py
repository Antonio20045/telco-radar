"""Wann zwei Preismessungen desselben Bündels einander WIDERSPRECHEN.

Gebraucht wird das dort, wo eine heutige Adaptermessung auf eine ältere
Klick-Messung desselben Bündels trifft (``klick_zusammenfuehrung``). Zwei Zahlen
sind dort selten auf den Cent gleich: ein Anbieter ändert Raten um ein paar Euro,
und ein Anbieter erlässt einen Anschlusspreis. Das ist eine Preisänderung und kein
Widerspruch.

Die Grenze ist deshalb dieselbe, die der Bewegungsblock meldenswert nennt
(``report.geraete_bewegung``): ``GRENZE_EURO`` ODER ``GRENZE_PROZENT``. Darunter
gelten zwei Messungen als dieselbe Aussage, darüber widersprechen sie einander -
und dann gilt die Regel aus dem Auftrag: lieber kein Preis als ein falscher, also
bleibt der ältere, belegte Wert stehen, statt dass eine zweifelhafte Zahl ihn
überschreibt.

``report`` darf hier nicht importiert werden (``.importlinter``), die Grenze steht
darum ein zweites Mal - mit demselben Wert, aber eigener Bedeutung: dort
„meldenswerte Bewegung", hier „zwei Messungen sagen nicht dasselbe".

KEIN Vergleich ist kein Beleg: nennt keine der beiden Messungen ein gemeinsames
Preisfeld, ist nichts bestätigt, und das zählt wie ein Widerspruch
(``OHNE_VERGLEICH``). Ein Feld, das nur eine Seite nennt, bleibt außen vor - zwei
Quellen werden nie feldweise gemischt (``klick_vollstaendig``).
"""

from __future__ import annotations

from collections.abc import Mapping

GRENZE_EURO = 50.0
GRENZE_PROZENT = 5.0
OHNE_VERGLEICH = "kein gemeinsames Preisfeld"

PREISFELDER = (
    "geraet_zuzahlung",
    "geraet_monatsrate",
    "tarif_monatlich",
    "buendel_monatlich",
    "anschlusspreis",
)
"""Die Wertfelder, die einen Bündelpreis ausmachen; ``tarif_bindung_monate`` ist
eine Laufzeit und kein Preis und gehört darum nicht hierher."""


def widersprueche(gemessen: Mapping, bezug: Mapping) -> list[str]:
    """Die Felder, in denen ``gemessen`` dem ``bezug`` widerspricht, als Text.

    Leere Liste heißt: beide sagen dasselbe, soweit sie beide etwas sagen.
    """
    beide = [f for f in PREISFELDER if _zahl(gemessen, f) and _zahl(bezug, f)]
    if not beide:
        return [OHNE_VERGLEICH]
    return [
        f"{f} {gemessen[f]} statt {bezug[f]}"
        for f in beide
        if _ueber_grenze(float(gemessen[f]), float(bezug[f]))
    ]


def _ueber_grenze(a: float, b: float) -> bool:
    """Ob der Abstand ``GRENZE_EURO`` ODER ``GRENZE_PROZENT`` überschreitet."""
    abstand = abs(a - b)
    groesser = max(abs(a), abs(b))
    return abstand > GRENZE_EURO or abstand > groesser * GRENZE_PROZENT / 100


def _zahl(satz: Mapping, feld: str) -> bool:
    wert = satz.get(feld)
    return isinstance(wert, int | float) and not isinstance(wert, bool)
