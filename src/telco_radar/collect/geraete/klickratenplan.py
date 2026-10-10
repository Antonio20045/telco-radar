"""Der Tarifpreis über die ganze Ratenlaufzeit aus dem Klick-Lauf (Pitch 3).

Dieselbe Regel wie beim alten Leser (``ratenlaufzeit``, Datenkonzept Geräte 5.3): ein
Klick-Satz mit einem einzigen offenen Tarifpreis ab Monat 1 bekommt die Phase von
Monat 1 bis zur letzten Rate nur mit Beleg, sonst keine.

o2  Der Nachweis ``ratenplan`` der Karte trägt den Satz des Ratenplan-Hinweises
    („über die gesamte Laufzeit deines Geräte-Ratenplans … Rabatt auf deinen
    Tarif.“), UND der Tarif der Antwortadresse nennt dieselbe Ratenzahl
    („…-hwv-36m-05-00“ zu 36 Raten). „…-online-hwv“ und „…-online-promo“ nennen
    keine und bleiben ohne Phase.

Andere Anbieter bekommen hier keine Phase.
"""

from __future__ import annotations

import re

from .ratenlaufzeit import RATENPLAN_HINWEIS, ganze_ratenlaufzeit, konfiguration

NACHWEIS = "ratenplan"
ANBIETER_MIT_TARIFCODE = "o2"
TARIFTEIL = "tariff"
_TARIF_RATEN = re.compile(r"-hwv-(?P<raten>\d+)m-")


def ratenplan_phasen(
    anbieter: str, kombination: dict, laufzeit: object, betrag: object
) -> list[dict]:
    """Die Phase 1 bis ``laufzeit`` zum Tarifpreis ``betrag``, nur mit Beleg."""
    if anbieter != ANBIETER_MIT_TARIFCODE or not isinstance(laufzeit, int):
        return []
    satz = (kombination.get("nachweise") or {}).get(NACHWEIS)
    adresse = kombination.get("antwort_url")
    if not satz or not isinstance(adresse, str):
        return []
    tarif = konfiguration(adresse).get(TARIFTEIL, "")
    treffer = _TARIF_RATEN.search(tarif)
    if treffer is None or int(treffer["raten"]) != laufzeit:
        return []
    beleg = f"{RATENPLAN_HINWEIS}: {satz} Tarif {tarif}"
    return ganze_ratenlaufzeit(beleg, laufzeit, betrag)
