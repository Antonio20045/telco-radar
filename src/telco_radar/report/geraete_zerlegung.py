"""Der Zerlegungsbalken der Bündelkarte: die Segmente mit ihrem Breitenanteil.

Aus ``geraete_tco_karten`` herausgelöst (dort darf die Datei nicht wachsen); die
Karten rufen ``zerlegung_balken`` weiter auf, das Template liest nur ``zerlegung``.
"""

from __future__ import annotations

import logging

log = logging.getLogger(__name__)

_ZERLEGUNG_RATENKATEGORIEN = ("raten", "buendel")
LABEL_RESTSCHULD = "Restschuld nach Monat 24"


def zerlegung_balken(
    bestandteile: list, restbetrag: float | None, gesamt: float | None
) -> list:
    """Die Segmente des Zerlegungsbalkens, mit ihrem Breitenanteil `pct`.

    Ohne `gesamt` (die Kennzahl ist nicht belastbar) oder ohne einen
    einzigen Posten gibt es keinen Balken - eine leere Liste, kein Balken
    aus Teilbeträgen ohne Summe (Regel 9: eine Lücke bleibt eine Lücke).

    Review-Fix S3 (mitgenommen): ein Segment mit Betrag exakt 0,00 EUR
    (eine gemessene "keine Zuzahlung"/"kein Anschlusspreis", Clean Code 3
    - 0 ist hier eine Aussage, kein fehlender Wert) bekommt keinen
    eigenen Balkenteil. Der Posten steht textlich ohnehin schon im
    Rechenweg darunter; ein Nullbreiten-Segment wuerde nur durch die
    optische Mindestbreite (D3-CSS-Block) als Phantomstreifen sichtbar.
    """
    if gesamt is None or not bestandteile:
        return []
    rest = round(restbetrag, 2) if restbetrag is not None else 0.0
    segmente = []
    gesplittet = False
    for posten in bestandteile:
        name, betrag = posten["name"], posten["betrag"]
        kategorie = posten["kategorie"]
        if rest and not gesplittet and kategorie in _ZERLEGUNG_RATENKATEGORIEN:
            faellig = round(betrag - rest, 2)
            if faellig < 0:
                log.warning(
                    "zerlegung_balken: restbetrag %.2f EUR groesser als "
                    "der Posten %r (%.2f EUR) - Balken bleibt "
                    "ungezeichnet",
                    rest,
                    name,
                    betrag,
                )
                return []
            if faellig:
                segmente.append(
                    {
                        "name": name,
                        "betrag": faellig,
                        "kategorie": kategorie,
                        "offen": False,
                    }
                )
            segmente.append(
                {
                    "name": LABEL_RESTSCHULD,
                    "betrag": rest,
                    "kategorie": "restschuld",
                    "offen": True,
                }
            )
            gesplittet = True
        elif betrag:
            segmente.append(
                {"name": name, "betrag": betrag, "kategorie": kategorie, "offen": False}
            )
    for seg in segmente:
        seg["pct"] = round(seg["betrag"] / gesamt * 100, 3) if gesamt else 0.0
    return segmente
