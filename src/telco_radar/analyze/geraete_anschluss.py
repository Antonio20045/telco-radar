"""Regel 16 über den Bestand: ein Anschlusspreis, den eine neuere Messung widerlegt.

Der Anschlusspreis (congstar: „Bereitstellungspreis Tarif“) gehört dem TARIF, nicht
dem Gerät: er ist bei allen Bündeln desselben Anbieters und Tarifs derselbe. Misst der
Anbieter ihn heute anders als an einem früheren Tag, ist der frühere Betrag nicht mehr
belegt - und eine Zeile mit einem nicht mehr belegten Pflichtwert zählt nicht
(CLAUDE.md, Clean Code 6: „nicht gelesen“ ist nicht „leer“, und im Zweifel die Lücke).

Der Fall vom 12.11.2026 (Ist-Aufnahme, Befund D1): congstar misst am 11.11. 15,00 €
(24 Monate) bzw. 35,00 € (Flex) und am 12.11. an denselben Tarifen 0,00 €. Die Zeilen
vom 11.11. blieben gültig und trugen 15 bzw. 35 € weiter in die Leitzahl.

Die Prüfung ist eine Bestandsprüfung wie Regel 5 und läuft darum neben
``geraete_regel5.speicherstufen`` in ``geraete_regeln.pruefe_bestand``. Sie trägt die
Nummer der Frische (16): die Folge ist dieselbe - die Zeile ist veraltet, bis der
Anbieter sie neu misst. Eine Zeile, die Regel 16 schon wegen ihres Alters verletzt,
bekommt keinen zweiten Befund.

Belegt ist der neue Betrag nur, wenn der jüngste Messtag der Gruppe GENAU EINEN Betrag
nennt. Nennt er zwei, belegt er keinen, und niemand wird widerlegt (fail-open an dieser
Stelle, weil sonst ein Lesefehler einen ganzen Tarif löschen würde); der Widerspruch
innerhalb eines Tages ist Sache von Regel 12.
"""

from __future__ import annotations

from collections.abc import Iterable

from ..geraete_model import normalisiere
from ..tco_model import Buendel
from .geraete_pruefstatus import CENT, VERLETZT, Befund, datum, eur

REGEL = 16


def widerlegter_anschluss(
    lesbar: Iterable[tuple[str, Buendel]], ohne_befund: frozenset[str] = frozenset()
) -> dict[str, Befund]:
    """Je Bündel-ID der Befund 16, wenn eine neuere Messung desselben Anbieters und
    Tarifs einen anderen Anschlusspreis nennt.

    ``ohne_befund`` sind die Bündel, die Regel 16 schon verletzen (zu alt): sie bleiben
    bei ihrem einen Befund.
    """
    gruppen: dict[tuple[str, str], list[tuple[str, str, float]]] = {}
    for bid, b in lesbar:
        if b.anschlusspreis is None or not b.abgerufen_am:
            continue
        gruppen.setdefault((normalisiere(b.anbieter), b.tarif_id), []).append(
            (bid, b.abgerufen_am, round(float(b.anschlusspreis), 2))
        )

    befunde: dict[str, Befund] = {}
    for liste in gruppen.values():
        juengster = max(tag for _, tag, _ in liste)
        betraege = {preis for _, tag, preis in liste if tag == juengster}
        if len(betraege) != 1:
            continue
        belegt = betraege.pop()
        for bid, tag, preis in liste:
            if tag >= juengster or bid in ohne_befund:
                continue
            if abs(preis - belegt) <= CENT:
                continue
            befunde[bid] = Befund(
                REGEL,
                VERLETZT,
                f"Anschluss {eur(preis)} vom {datum(tag)}; "
                f"die Messung vom {datum(juengster)} nennt an diesem Tarif "
                f"{eur(belegt)}",
            )
    return befunde
