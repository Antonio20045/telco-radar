"""Welche Kombinationen ein Bestandseintrag noch als frisch verteidigt.

Befund 17.11.2026 (Lauf 44129470685, o2): 83 von 452 Kombinationen galten in
`buendel_abdeckung.kombis_weg` als weg, weil die Klick-Vertiefung nicht jede
Kombination jeden Tag neu misst - der Bestandseintrag hielt trotzdem ein
`last_verified` innerhalb `FRISCHEGRENZE_TAGE`. Das ist kein Wegfall.
"""

from __future__ import annotations

from ..klick_vertrag import FRISCHEGRENZE_TAGE
from .buendel_angebot import angebot_ohne_farbe
from .klick_alter import alter_tage


def frisch_im_bestand(buendel: list[dict], messtag: str) -> dict[str, set[str]]:
    """Je Anbieter die Kombinationen ohne Farbe, deren Bestandseintrag
    innerhalb `FRISCHEGRENZE_TAGE` neu geschrieben wurde: ein solcher
    Eintrag ist nicht weg, auch wenn er am Messtag selbst nicht erneut
    gemessen wurde."""
    frisch: dict[str, set[str]] = {}
    for b in buendel:
        if (b.get("zustand") or "neu") != "neu":
            continue
        alter = alter_tage(b.get("last_verified"), messtag)
        if alter is not None and 0 <= alter < FRISCHEGRENZE_TAGE:
            frisch.setdefault(str(b.get("anbieter") or ""), set()).add(
                angebot_ohne_farbe(b.get("id") or "")
            )
    return frisch
