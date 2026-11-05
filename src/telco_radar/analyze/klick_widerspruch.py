"""Widerspricht ein Klick-Satz dem Adaptersatz einer 1&1-„24+12“-Zelle: Lücke.

Betrifft Sätze mit einem Bündelbetrag und Ratenzahl über dem Vergleichszeitraum
(1&1: 36 Raten, gerechnet wird bis Monat 24). Nennen Klick- und Adaptersatz in einem
Wertfeld verschiedene Werte, sagt kein Satz, welcher Messlauf der jüngere ist, und die
24-Monats-Rechnung hängt an der Einmalzahlung. Der Adaptersatz bleibt dann ohne
Einmalzahlung (benannte Lücke, nie 0) und überschreibt so den älteren Klick-Eintrag im
Bestand; ``_vorrang`` lässt ihn nicht wieder vom Klick-Eintrag verdrängen. Getrennte
Verträge (Telekom, o2) mit 36 Raten sind nicht betroffen. Bilanz:
``widerspruch_24_plus_12``.
"""

from __future__ import annotations

import logging

from ..tco_model import TCO_HORIZONT
from .geraete_pruefstatus import HERLEITUNG_WIDERSPRUCH
from .klick_geschwister import Schluessel
from .klick_vollstaendig import nennt

log = logging.getLogger(__name__)


def widerspruch_luecke(
    schluessel: Schluessel, klick: dict, adapter: dict, anders: list[str]
) -> dict | None:
    """Der Adaptersatz ohne Einmalzahlung, wenn die 24+12-Zelle widersprochen wird.

    ``anders`` sind die Felder, in denen Klick- und Adaptersatz Verschiedenes nennen;
    ``None``, wenn nichts widerspricht oder die Zelle kein 24+12-Vertrag ist."""
    laufzeit = schluessel[4]
    if not anders or not nennt(klick, "buendel_monatlich"):
        return None
    if laufzeit is None or laufzeit <= TCO_HORIZONT:
        return None
    log.warning(
        "Klick-Satz %s widerspricht dem Adapter (%s): 24+12-Zelle ohne Preis, "
        "die Einmalzahlung bleibt Lücke",
        klick.get("sku_id"),
        ", ".join(anders),
    )
    return {
        **adapter,
        "geraet_zuzahlung": None,
        "herleitung": HERLEITUNG_WIDERSPRUCH,
    }
