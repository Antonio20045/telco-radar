"""Der Tarifpreis über die ganze Ratenlaufzeit aus dem Klick-Lauf (Pitch 3).

Dieselbe Regel wie beim alten Leser (``ratenlaufzeit``, Datenkonzept Geräte 5.3): ein
Klick-Satz mit einem einzigen offenen Tarifpreis ab Monat 1 bekommt die Phase von
Monat 1 bis zur letzten Rate nur mit Beleg, sonst keine.

o2        Der Nachweis ``ratenplan`` der Karte trägt den Satz des Ratenplan-Hinweises
          („über die gesamte Laufzeit deines Geräte-Ratenplans … Rabatt auf deinen
          Tarif.“), UND der Tarif der Antwortadresse nennt dieselbe Ratenzahl
          („…-hwv-36m-05-00“ zu 36 Raten). „…-online-hwv“ und „…-online-promo“
          nennen keine und bleiben ohne Phase.

congstar  Der Nachweis ``ratenplan`` ist ``prices.recurring.discounts`` des Tarifs als
          JSON und leer („[]“): der Tarifpreis hat keine Rabattphase (Klick-Erkundung
          07.10.2026: alle acht Tarife mit ``discounts`` [] und ``listed`` gleich
          ``discounted``). Ein Nachlass, auch ein dauerhafter, ist kein Beleg.

Andere Anbieter bekommen hier keine Phase.
"""

from __future__ import annotations

import re

from .ratenlaufzeit import RATENPLAN_HINWEIS, ganze_ratenlaufzeit, konfiguration

NACHWEIS = "ratenplan"
ANBIETER_MIT_TARIFCODE = "o2"
ANBIETER_OHNE_RABATTPHASE = "congstar"
OHNE_RABATT = "[]"
TARIFTEIL = "tariff"
_TARIF_RATEN = re.compile(r"-hwv-(?P<raten>\d+)m-")


def ratenplan_phasen(
    anbieter: str, kombination: dict, laufzeit: object, betrag: object
) -> list[dict]:
    """Die Phase 1 bis ``laufzeit`` zum Tarifpreis ``betrag``, nur mit Beleg."""
    satz = (kombination.get("nachweise") or {}).get(NACHWEIS)
    if not satz or not isinstance(laufzeit, int) or not _betrag(betrag):
        return []
    if anbieter == ANBIETER_OHNE_RABATTPHASE:
        return _ohne_rabattphase(satz, laufzeit, betrag)
    if anbieter != ANBIETER_MIT_TARIFCODE:
        return []
    adresse = kombination.get("antwort_url")
    if not isinstance(adresse, str):
        return []
    tarif = konfiguration(adresse).get(TARIFTEIL, "")
    treffer = _TARIF_RATEN.search(tarif)
    if treffer is None or int(treffer["raten"]) != laufzeit:
        return []
    beleg = f"{RATENPLAN_HINWEIS}: {satz} Tarif {tarif}"
    return ganze_ratenlaufzeit(beleg, laufzeit, betrag)


def _ohne_rabattphase(satz: str, laufzeit: int, betrag: float) -> list[dict]:
    if satz != OHNE_RABATT:
        return []
    preis = f"{betrag:.2f}".replace(".", ",")
    beleg = f"prices.recurring: discounted {preis} €, discounts [] (keine Rabattphase)"
    return ganze_ratenlaufzeit(beleg, laufzeit, betrag)


def _betrag(wert: object) -> bool:
    return isinstance(wert, int | float) and not isinstance(wert, bool)
