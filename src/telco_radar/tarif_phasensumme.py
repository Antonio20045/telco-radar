"""Die phasengewichtete Summe der Monatsentgelte: der Kern der Tarif-Rechnung.

Aus `tco_model` herausgelöst (dort re-exportiert), damit die Leitzahl-Datei nicht
weiter wächst; Leitzahl, Kernzahl und Effektivpreis rechnen mit dieser einen Summe.
"""

from __future__ import annotations

from .tarif_model import Preisphase


def phasensumme(phasen: list[Preisphase], horizont: int) -> float | None:
    """Die Summe der Monatsentgelte ueber den Horizont - phasengewichtet.

    Der Kern der Tarif-Rechnung, seit A1 (20.09.2026) die Summe der Leitzahl:
    Leitzahl und Effektivpreis teilen EINE phasengewichtete Summe, sonst
    rechneten zwei Stellen dasselbe Blatt verschieden (`tco_model`
    re-exportiert sie, `report/effektivpreis.py` ebenso). Eine Phase ohne Ende
    laeuft bis zum Horizont; eine Phase, die darueber hinausreicht, wird
    gekappt; Monate nach der letzten Phase laufen zum letzten bekannten
    Preis weiter - die vorsichtige Annahme: der letzte Preis eines Tarifs
    ist der Normalpreis, nicht der Rabattpreis.
    """
    if not phasen:
        return None
    summe = 0.0
    abgedeckt = 0
    for phase in sorted(phasen, key=lambda p: p.von_monat):
        monate = phase.monate(horizont)
        if monate <= 0:
            continue
        summe += monate * phase.betrag
        abgedeckt += monate
    if abgedeckt <= 0:
        return None
    if abgedeckt < horizont:
        letzter = sorted(phasen, key=lambda p: p.von_monat)[-1]
        summe += (horizont - abgedeckt) * letzter.betrag
    return round(summe, 2)
