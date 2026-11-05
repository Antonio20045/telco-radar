"""Monate benennen: wie viele Phasen einen Monat nennen, und Monatsspannen als Text.

Aus `tco_kosten` herausgelöst; die Lückenmeldungen der Kernzahl („Monat 25–36“)
benutzen sie.
"""

from __future__ import annotations

from .tarif_model import Preisphase


def preise_im_monat(phasen: list[Preisphase], monat: int) -> int:
    """Wie viele Phasen einen Preis für `monat` nennen."""
    return sum(
        p.von_monat <= monat and (p.bis_monat is None or monat <= p.bis_monat)
        for p in phasen
    )


def spannen(monate: list[int]) -> list[str]:
    """Aufeinanderfolgende Monate als „25–36“, ein einzelner als „25“."""
    reihen: list[list[int]] = []
    for monat in monate:
        if reihen and monat == reihen[-1][1] + 1:
            reihen[-1][1] = monat
        else:
            reihen.append([monat, monat])
    return [spanne(von, bis) for von, bis in reihen]


def spanne(von: int, bis: int) -> str:
    """„von–bis“, bei gleichem Anfang und Ende nur „von“."""
    return f"{von}–{bis}" if bis > von else f"{von}"
