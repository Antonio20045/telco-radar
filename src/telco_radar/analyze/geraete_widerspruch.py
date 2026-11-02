"""Ein abgeleiteter Preis, den eine gelesene Zeile widerlegt, zählt nicht.

1&1 leitet die Tarifstufen aus einem Grundangebot und dem Tarifaufschlag ab
(`einsundeins.ergaenze_tarifstufen`); die Ablöse hängt nur an der Gerätevariante.
Steht für dieselbe Variante (`sku_id`) und Ratenlaufzeit eine gelesene Zeile
(`quelle_art == QUELLE_KLICK`) mit anderer Zuzahlung, stammt die Ableitung aus dem
falschen Grundangebot. Ohne gelesene Gegenzeile ist nichts zu widerlegen; andere
Anbieter rechnen die Zuzahlung je Tarif verschieden und fallen nicht darunter
(`HERLEITUNG_PREISLISTE`).

EINE Definition (Clean Code 7): Tabelle, Bild, Teurer-Liste und Export lesen die
Bündelliste, die `ohne_widerlegte` übrig lässt. Lieber ein Preis weniger als ein
falscher.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable

from ..tarif_model import QUELLE_KLICK
from ..tco_model import Buendel
from .geraete_pruefstatus import HERLEITUNG_PREISLISTE

log = logging.getLogger(__name__)

ZUZAHLUNG_TOLERANZ = 0.005


def _variante(b: Buendel) -> tuple:
    """Gerätevariante und Ratenlaufzeit: dafür ist die Ablöse gleich."""
    return (b.anbieter, b.sku_id, b.laufzeit_monate)


def _abgeleitet(b: Buendel) -> bool:
    return (
        b.herleitung.strip() in HERLEITUNG_PREISLISTE and b.geraet_zuzahlung is not None
    )


def _gelesen(b: Buendel) -> bool:
    return b.quelle_art == QUELLE_KLICK and b.geraet_zuzahlung is not None


def ohne_widerlegte(buendel: Iterable) -> list:
    """Die Bündel ohne die abgeleiteten, deren Zuzahlung eine gelesene Zeile widerlegt.

    Kein Buendel-Objekt (unlesbarer Satz) bleibt unberührt. Jedes Weglassen steht
    im Protokoll."""
    liste = list(buendel)
    gelesen: dict[tuple, list[float]] = {}
    for b in liste:
        if isinstance(b, Buendel) and _gelesen(b):
            gelesen.setdefault(_variante(b), []).append(b.geraet_zuzahlung)
    if not gelesen:
        return liste
    rest = []
    for b in liste:
        if (
            isinstance(b, Buendel)
            and _abgeleitet(b)
            and any(
                abs(z - b.geraet_zuzahlung) > ZUZAHLUNG_TOLERANZ
                for z in gelesen.get(_variante(b), ())
            )
        ):
            log.warning(
                "%s %s %s: abgeleitete Zuzahlung %s widerspricht der gelesenen Zeile, "
                "Bündel zählt nicht",
                b.anbieter,
                b.sku_id,
                b.tarif_name,
                b.geraet_zuzahlung,
            )
            continue
        rest.append(b)
    return rest
