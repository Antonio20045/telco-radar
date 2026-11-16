"""Das Sammelbudget des Geraetelaufs auf die Anbieter aufteilen.

BEFUND 16.11.2026: Der Tageslauf sammelt mit EINEM Budget fuer ALLE Anbieter
(`geraete.yml`, `--frist 1500`, 25 Minuten). Es war eine gemeinsame Weide: jeder
Anbieter durfte nehmen, was da war, solange jedem nach ihm noch
`MINDEST_JE_ANBIETER` Sekunden blieben. o2 steht mit dem groessten Katalog
(rund 2.500 Preise, die Vertiefung ruft je Geraet Speicher x Laufzeiten ab) an
spaeter Stelle und bekam, was die Haendler vor ihm uebrig liessen - gemessen
2.216 Zeilen am 13.11., 1.012 am 14.11., 1.108 am 15.11. Dieselbe Quelle,
dieselbe Software, drei Zahlen: die Luecke hing an der Reihenfolge, nicht am
Anbieter.

Hier wird das Budget deshalb VOR dem ersten Abruf benannt aufgeteilt. Jeder
crawlende Anbieter bekommt einen Sockel (`MINDEST_JE_ANBIETER`), der Rest geht
nach seinem Bedarf (`sammelbedarf`). Die Summe der Anteile ist das Gesamtbudget
und nie mehr: der Anteil verschiebt, WER wartet - er verlaengert den Job nicht
(CLAUDE.md Regel 8).

Was die Aufteilung NICHT kann: Zeit schaffen. Die Bedarfe aller crawlenden
Anbieter summieren sich am 16.11.2026 auf rund 3.000 Sekunden gegen 1.500
Sekunden Budget. Die Aufteilung macht die Luecke berechenbar und sichtbar
(Protokollzeile in `sammle`, `bilanz.gedeckelt` je Anbieter); sie schliesst sie
nicht. Dafuer braucht der Lauf mehr Zeit, und das steht im Workflow, nicht hier.

Kein LLM, keine Uhr, kein Netz: eine Rechnung ueber Konfigurationswerte.
"""

from __future__ import annotations

import logging

log = logging.getLogger(__name__)

MINDEST_JE_ANBIETER = 120.0
"""Der Sockel: so viel bekommt jeder crawlende Anbieter, bevor der Bedarf zaehlt.
Weniger reicht nicht fuer robots.txt und eine Seite."""

ABRUF_SEKUNDEN = 1.0
"""Netzzeit EINES Abrufs, wo kein groesserer Abstand aus robots.txt gilt."""


def sammelbedarf(anbieter) -> float:
    """Wie viele Sekunden dieser Anbieter zum Sammeln braucht.

    Erste Wahl ist `sammelbedarf_sekunden` aus `config/geraete_quellen.yaml`:
    dort steht die Zahl mit ihrer Herleitung und ihrem Datum. Fehlt sie, wird
    GESCHAETZT, was der Anbieter anfassen wird - seine crawlbaren Einstiege plus
    sein Produktdeckel, mal dem Abstand, den seine robots.txt ihm auferlegt.
    Das ist eine Schaetzung und heisst so; sie verteilt Anteile und verlaengert
    nie das Gesamtbudget.

    Nie kleiner als `MINDEST_JE_ANBIETER`.
    """
    erklaert = getattr(anbieter, "sammelbedarf_sekunden", None)
    if erklaert is not None:
        return max(MINDEST_JE_ANBIETER, float(erklaert))
    abrufe = len(anbieter.crawled_einstiege) + anbieter.max_produkte
    takt = max(float(anbieter.rate_limit_sekunden), ABRUF_SEKUNDEN)
    return max(MINDEST_JE_ANBIETER, abrufe * takt)


def sammelanteile(anbieter: list, gesamt: float | None) -> dict[str, float]:
    """Das Budget `gesamt` je Anbietername; die Summe ist `gesamt` und nie mehr.

    Sockel fuer jeden, der Rest nach Bedarf. Reicht das Budget nicht einmal fuer
    die Sockel, bekommt jeder denselben Bruchteil - niemand faellt still heraus.
    Der Anteil ist eine Zusage, keine Obergrenze fuer den ganzen Lauf: was ein
    frueher Anbieter nicht braucht, reicht `sammle` an den naechsten weiter.
    """
    namen = [a.name for a in anbieter]
    if not namen or not gesamt or gesamt <= 0:
        return {}
    sockel = min(MINDEST_JE_ANBIETER, gesamt / len(namen))
    rest = gesamt - sockel * len(namen)
    ueber = {a.name: max(0.0, sammelbedarf(a) - sockel) for a in anbieter}
    summe = sum(ueber.values())
    if rest <= 0 or summe <= 0:
        gleich = rest / len(namen) if rest > 0 else 0.0
        return _protokolliere({n: sockel + gleich for n in namen}, gesamt)
    return _protokolliere({n: sockel + rest * ueber[n] / summe for n in namen}, gesamt)


def _protokolliere(anteile: dict[str, float], gesamt: float) -> dict[str, float]:
    """Die Aufteilung ins Protokoll: wer wie viel bekommt, steht im Log des Laufs."""
    log.info(
        "Sammelbudget %.0f s je Anbieter: %s",
        gesamt,
        ", ".join(f"{n} {w:.0f}" for n, w in anteile.items()),
    )
    return anteile
