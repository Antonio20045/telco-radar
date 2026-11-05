"""Welche Messung je Tag in die Zeitreihe kommt - und welche als Lücke fehlt.

Bei 1&1 ist die Einmalzahlung nach Monat 24 ein Gerätewert, gleich für alle Tarife
desselben Geräts (Manager, 05.11.2026; Tafel: `analyze.geraete_widerspruch`). Eine
Messung, die an ihrem Tag davon abweicht, ist kein Punkt und kein Rechenweg.
"""

from __future__ import annotations

import logging

from ..analyze.geraete_widerspruch import (
    abweichende_einmalzahlungen,
    hat_einmalzahlung_nach_24,
)
from ..tco_model import zeitraum_vergleichbar
from . import geraete_notbremse as notbremse
from .geraete_rechenweg import _buendel_aus_messung

log = logging.getLogger(__name__)


def _tag(k: dict) -> tuple:
    return (k["schluessel"][0], k["anbieter"], k["datum"])


def ohne_abweichende_einmalzahlung(kandidaten: list[dict], tarife: dict | None) -> list:
    """Die Kandidaten ohne die, deren Einmalzahlung am selben Tag vom Gerät abweicht."""
    zahlung = []
    for k in kandidaten:
        b = _buendel_aus_messung(k["mess"], tarife)
        gilt = b is not None and hat_einmalzahlung_nach_24(b)
        zahlung.append(b.geraet_zuzahlung if b is not None and gilt else None)
    je_tag: dict[tuple, list[float]] = {}
    for k, z in zip(kandidaten, zahlung, strict=True):
        if z is not None:
            je_tag.setdefault(_tag(k), []).append(z)
    abweichend = {
        t: w for t, v in je_tag.items() if (w := abweichende_einmalzahlungen(v))
    }
    rest = [
        k
        for k, z in zip(kandidaten, zahlung, strict=True)
        if z is None or round(z, 2) not in abweichend.get(_tag(k), ())
    ]
    if len(rest) < len(kandidaten):
        log.info(
            "Zeitreihe: %d Messung(en) mit abweichender Einmalzahlung, Lücke",
            len(kandidaten) - len(rest),
        )
    return rest


def einsortieren(kandidaten: list[dict], messungen: dict, tarife: dict | None) -> None:
    """Je (Modell, Band, Laufzeit, Anbieter, Tag) gewinnt die beste Messung.

    Zählende vor nicht zählenden, dann der niedrigere Wert (nur bei vergleichbarem
    Zeitraum), sonst der zum Zeitraum der Ansicht passende."""
    for k in ohne_abweichende_einmalzahlung(kandidaten, tarife):
        slot = messungen.setdefault(k["schluessel"], {}).setdefault(k["anbieter"], {})
        neu, alt = k["mess"], slot.get(k["datum"])
        if alt is None or notbremse.zaehlt(neu) != notbremse.zaehlt(alt):
            besser = alt is None or notbremse.zaehlt(neu)
        elif zeitraum_vergleichbar(neu["monate"], alt["monate"]):
            besser = neu["wert"] < alt["wert"]
        else:
            besser = zeitraum_vergleichbar(neu["monate"], k["h"])
        if besser:
            slot[k["datum"]] = neu
