"""Regel 18 über den Bestand: ein Anschlusspreis, den eine neuere Messung widerlegt.

Der Anschlusspreis (congstar: „Bereitstellungspreis Tarif“) gehört dem TARIF IN SEINER
VERTRAGSFORM, nicht dem Gerät: er ist bei allen Bündeln desselben Anbieters, Tarifs,
Gerätezustands und derselben Ratenlaufzeit derselbe. Misst der Anbieter ihn heute anders
als an einem früheren Tag, ist der frühere Betrag nicht mehr belegt - und eine Zeile mit
einem nicht mehr belegten Pflichtwert zählt nicht (CLAUDE.md, Clean Code 6: „nicht
gelesen“ ist nicht „leer“, und im Zweifel die Lücke).

Der Fall vom 12.11.2026 (Ist-Aufnahme, Befund D1): congstar misst am 11.11. 15,00 €
(24 Monate) bzw. 35,00 € (Flex) und am 12.11. an denselben Tarifen 0,00 €. Die Zeilen
vom 11.11. blieben gültig und trugen 15 bzw. 35 € weiter in die Leitzahl.

Die Prüfung ist eine Bestandsprüfung wie Regel 5 und läuft darum neben
``geraete_regel5.speicherstufen`` in ``geraete_regeln.pruefe_bestand``. Sie trägt seit
dem 13.11.2026 die eigene Nummer 18 (vorher die der Frische, 16): die FOLGE ist
dieselbe - die Zeile ist nicht mehr belegt, bis der Anbieter sie neu misst -, der
GRUND aber ein anderer. Unter einer Nummer sagte die Seite an einer Zeile vom 11.11.
„Preis veraltet: Preis vom 11.11.2026“: frisch und veraltet in einem Satz
(Analyse A-RUJNK5, Abschnitt 2 (d)). Eine Zeile, die Regel 16 schon wegen ihres
Alters verletzt, bekommt keinen zweiten Befund.

Drei Hürden, und alle drei fallen im Zweifel nach „niemand wird widerlegt“ aus
(Prüfung A-DBURQP vom 12.11.2026, Auflagen 1 und 2):

1. **Der jüngste Messtag der Gruppe nennt GENAU EINEN Betrag.** Nennt er zwei, belegt
   er keinen; der Widerspruch innerhalb eines Tages ist Sache von Regel 12.
2. **Mindeststütze**: der jüngste Messtag trägt den Betrag an mindestens zwei
   verschiedenen Geräten oder an einer Zeile mit Klick-Beleg. Eine einzelne Zeile ohne
   Beleg kann ein Lesefehler sein, und ein Lesefehler darf keinen ganzen Tarif löschen.
3. **Der Messtag der älteren Zeile ist selbst eindeutig.** War der Tarif schon an ihrem
   eigenen Abruftag uneins (zwei Beträge nebeneinander), ist nicht entscheidbar, welchen
   davon die neue Messung ersetzt - dann widerlegt sie keinen.

Hürde 3 ist die Antwort auf den o2-Befund der Prüfung: „Unlimited S Special Plus“ führte
am 11.11.2026 nebeneinander 0,00 € (33 Klick-Zeilen) und 39,99 € (20 Klick-Zeilen); die
39,99 € stehen am 12.11. unverändert auf o2online.de, die 0,00 € des JSON-Adapters sind
für Neugeräte zweifelhaft. Ohne Hürde 3 strich die Regel die 40 richtigen Zeilen.

Nicht nach QUELLE gruppiert, bewusst: der Klick-Lauf vom 12.11.2026 verlor 380 von 760
congstar-Sätzen in der Tarifauflösung, die belegte 0,00-€-Messung steht nur am
JSON-Adapter. Eine Gruppe je Quelle hätte am echten Bestand gar nichts mehr widerlegt
(congstar 950 → 950 statt 950 → 174) - der Fix wäre leer gewesen.
"""

from __future__ import annotations

from collections.abc import Iterable

from ..geraete_model import normalisiere
from ..tarif_model import QUELLE_KLICK
from ..tco_model import Buendel
from .geraete_pruefstatus import (
    CENT,
    REGEL_ANSCHLUSS,
    VERLETZT,
    Befund,
    datum,
    eur,
)

REGEL = REGEL_ANSCHLUSS

MIN_GERAETE = 2
"""So viele verschiedene Geräte muss der jüngste Messtag tragen, wenn keine seiner
Zeilen einen Klick-Beleg hat."""

Gruppe = tuple[str, str, str, int | None]

Zeile = tuple[str, str, float, str, str]
"""(Bündel-ID, abgerufen_am, Anschlusspreis, sku_id, quelle_art)."""


def _schluessel(b: Buendel) -> Gruppe:
    """Anbieter, Tarif, Gerätezustand und Ratenlaufzeit - die Vertragsform, für die ein
    Anschlusspreis gilt. ``zustand`` und ``laufzeit_monate`` sind seit der Nachbesserung
    im Schlüssel: congstar nimmt 15,00 € auf 24 Monate und 35,00 € flex, und die
    Refurbished-Ware kommt aus einem eigenen Bestand."""
    return (normalisiere(b.anbieter), b.tarif_id, b.zustand, b.laufzeit_monate)


def _gestuetzt(juengste: list[Zeile]) -> bool:
    """Trägt der jüngste Messtag seinen Betrag breit genug, um einen älteren zu
    widerlegen? Ein Klick-Beleg genügt allein, sonst braucht es ``MIN_GERAETE``
    verschiedene Geräte (Auflage 2 der Prüfung A-DBURQP)."""
    if any(quelle == QUELLE_KLICK for *_, quelle in juengste):
        return True
    return len({sku for *_, sku, _ in juengste}) >= MIN_GERAETE


def widerlegter_anschluss(
    lesbar: Iterable[tuple[str, Buendel]], ohne_befund: frozenset[str] = frozenset()
) -> dict[str, Befund]:
    """Je Bündel-ID der Befund 16, wenn eine neuere Messung derselben Vertragsform
    (Anbieter, Tarif, Zustand, Laufzeit) einen anderen Anschlusspreis nennt.

    ``ohne_befund`` sind die Bündel, die Regel 16 schon verletzen (zu alt): sie bleiben
    bei ihrem einen Befund.
    """
    gruppen: dict[Gruppe, list[Zeile]] = {}
    for bid, b in lesbar:
        if b.anschlusspreis is None or not b.abgerufen_am:
            continue
        gruppen.setdefault(_schluessel(b), []).append(
            (
                bid,
                b.abgerufen_am,
                round(float(b.anschlusspreis), 2),
                b.sku_id,
                b.quelle_art,
            )
        )

    befunde: dict[str, Befund] = {}
    for liste in gruppen.values():
        juengster = max(tag for _, tag, *_ in liste)
        juengste = [z for z in liste if z[1] == juengster]
        betraege = {preis for _, _, preis, _, _ in juengste}
        if len(betraege) != 1:
            continue
        if not _gestuetzt(juengste):
            continue
        belegt = betraege.pop()
        je_tag: dict[str, set[float]] = {}
        for _, tag, preis, _, _ in liste:
            je_tag.setdefault(tag, set()).add(preis)
        for bid, tag, preis, _, _ in liste:
            if tag >= juengster or bid in ohne_befund:
                continue
            if len(je_tag[tag]) != 1:
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
