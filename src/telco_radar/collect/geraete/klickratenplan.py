"""Der Tarifpreis über die ganze Ratenlaufzeit aus dem Klick-Lauf (Pitch 3).

Dieselbe Regel wie beim alten Leser (``ratenlaufzeit``, Datenkonzept Geräte 5.3): ein
Klick-Satz mit einem einzigen offenen Tarifpreis ab Monat 1 bekommt die Phase von
Monat 1 bis zur letzten Rate nur mit Beleg, sonst keine.

Welche Art Beleg gilt, steht in der Klick-Karte des Anbieters (Feld ``ratenplan``,
``klickregeln``), nicht im Code:

``tarifcode``  (o2) Der Nachweis ``ratenplan`` der Karte trägt den Satz des
          Ratenplan-Hinweises („über die gesamte Laufzeit deines Geräte-Ratenplans …
          Rabatt auf deinen Tarif.“), UND der ``teil`` der Antwortadresse nennt mit
          ``muster`` dieselbe Ratenzahl („…-hwv-36m-05-00“ zu 36 Raten).
          „…-online-hwv“ und „…-online-promo“ nennen keine und bleiben ohne Phase.

``ohne_rabattphase``  (congstar) Der Nachweis ``ratenplan`` ist ``nachweis`` der Karte,
          bei congstar ``prices.recurring.discounts`` des Tarifs als JSON und leer
          („[]“): der Tarifpreis hat keine Rabattphase (Klick-Erkundung 07.10.2026: alle
          acht Tarife mit ``discounts`` [] und ``listed`` gleich ``discounted``). Ein
          Nachlass, auch ein dauerhafter, ist kein Beleg.

Eine Karte ohne ``ratenplan`` liefert keine Phase. Liest sie aber den Nachweis
(``antwort.pfade.ratenplan``) und trägt der Satz ihn, fehlt die Regel dazu:
``RatenplanRegelFehlt`` (der Rohsatz ist die Lücke ``ratenplan_regel_fehlt``), nie eine
geratene Ratenzahl.
"""

from __future__ import annotations

from pathlib import Path

from .klickkartenteile import RATENPLAN_OHNE_RABATTPHASE, RATENPLAN_TARIFCODE
from .klickregeln import regeln
from .ratenlaufzeit import RATENPLAN_HINWEIS, ganze_ratenlaufzeit, konfiguration

NACHWEIS = "ratenplan"


class RatenplanRegelFehlt(LookupError):
    """Der Satz trägt den Nachweis ``ratenplan``, die Karte seines Anbieters keine
    Regel dazu."""


def ratenplan_phasen(
    anbieter: str,
    kombination: dict,
    laufzeit: object,
    betrag: object,
    karten: Path | None = None,
) -> list[dict]:
    """Die Phase 1 bis ``laufzeit`` zum Tarifpreis ``betrag``, nur mit Beleg."""
    satz = (kombination.get("nachweise") or {}).get(NACHWEIS)
    if not satz or not isinstance(laufzeit, int) or isinstance(betrag, bool):
        return []
    if not isinstance(betrag, int | float):
        return []
    karte = regeln(anbieter, karten)
    regel = karte.ratenplan
    if regel is None:
        if karte.liest_ratenplan_nachweis:
            raise RatenplanRegelFehlt(
                f"{anbieter}: Karte liest den Nachweis {NACHWEIS!r}, "
                "aber das Feld ratenplan fehlt"
            )
        return []
    if regel.art == RATENPLAN_OHNE_RABATTPHASE:
        return _ohne_rabattphase(satz, regel.nachweis, laufzeit, betrag)
    if regel.art != RATENPLAN_TARIFCODE:
        return []
    adresse = kombination.get("antwort_url")
    if not isinstance(adresse, str) or regel.muster is None:
        return []
    tarif = konfiguration(adresse).get(regel.teil or "", "")
    treffer = regel.muster.search(tarif)
    if treffer is None or int(treffer[1]) != laufzeit:
        return []
    beleg = f"{RATENPLAN_HINWEIS}: {satz} Tarif {tarif}"
    return ganze_ratenlaufzeit(beleg, laufzeit, betrag)


def _ohne_rabattphase(
    satz: str, nachweis: str | None, laufzeit: int, betrag: float
) -> list[dict]:
    if satz != nachweis:
        return []
    preis = f"{betrag:.2f}".replace(".", ",")
    beleg = f"prices.recurring: discounted {preis} €, discounts [] (keine Rabattphase)"
    return ganze_ratenlaufzeit(beleg, laufzeit, betrag)


def buendelphasen(werte: dict, satz: dict, kombination: dict) -> list[dict]:
    """Bündelphasen wie gelesen, eine offene bleibt offen; ein einzelner offener Preis
    ab Monat 1 ist keine, außer mit Ratenplan-Beleg (``ratenplan_phasen``); fehlt der
    Karte dafür die Regel, wirft sie ``RatenplanRegelFehlt``."""
    roh = werte.get("tarifphasen")
    if satz.get("buendel_monatlich") is not None or not isinstance(roh, list):
        return []
    if len(roh) == 1 and roh[0][1] is None:
        if roh[0][0] != 1:
            return []
        laufzeit, betrag = satz["laufzeit_monate"], roh[0][2]
        return ratenplan_phasen(satz["anbieter"], kombination, laufzeit, betrag)
    beleg = f"Klick-Beleg {satz['beleg_id'] or satz['quelle_url']}"
    return [
        {"von_monat": von, "bis_monat": bis, "betrag": betrag, "beleg": beleg}
        for von, bis, betrag in roh
    ]
