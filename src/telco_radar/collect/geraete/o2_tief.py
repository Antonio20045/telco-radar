"""o2: Vertiefung und danach die Nachmessung offener Anschlusspreise, ein Schritt.

``o2.vertiefe_buendel`` liest je Gerät Speicher und Laufzeiten und leitet die übrigen
Tarife ab; ``o2_anschluss.nachmesse`` holt danach, solange Zeit ist, für jeden
abgeleiteten Satz ohne Anschlusspreis die Antwort seines Tarifs. Die Nachmessung läuft
erst nach der ganzen Vertiefung, damit sie kein Gerät verdrängt (Regel 8: dieselbe
Frist ``weiter``), und höchstens ``NACHMESSUNG_HOECHSTENS_S``: die Frist eines Anbieters
lässt jedem nach ihm nur ``sammelbudget.MINDEST_JE_ANBIETER`` (120 s), congstar brauchte
am 21.11.2026 aber rund 290 s. Gemessen am Gerätelauf 44858465074: o2 endete 03:23:55,
congstar, mobilcom-debitel und ALDI TALK brauchten danach zusammen rund 420 s, bis zum
Ende der Sammelfrist (03:46:58) blieben rund 960 s frei; 600 s davon (rund 150 Abrufe
à 3,9 s) gehen an die Nachmessung, in der Reihenfolge der Bündelpriorität.
"""

from __future__ import annotations

import time
from collections.abc import Callable

from . import o2
from .o2_anschluss import nachmesse

NACHMESSUNG_HOECHSTENS_S = 600.0


def vertiefe_und_messe(
    hole: Callable[[str], str],
    rohsaetze: list,
    weiter: Callable[[], bool] | None = None,
    zaehler: dict | None = None,
    zusatz: object = None,
    uhr: Callable[[], float] = time.monotonic,
) -> list[dict]:
    """Wie ``o2.vertiefe_buendel``, danach ``o2_anschluss.nachmesse``."""
    z = {} if zaehler is None else zaehler
    frist = weiter or (lambda: True)
    tief = o2.vertiefe_buendel(hole, rohsaetze, frist, z, zusatz)
    ende = uhr() + NACHMESSUNG_HOECHSTENS_S

    def noch() -> bool:
        return frist() and uhr() < ende

    return nachmesse(tief, lambda u: o2._hole_seite(hole, u, z), o2._gemessen, noch, z)
