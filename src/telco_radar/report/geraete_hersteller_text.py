"""Texte der Herstellergrafik: Rundung, Prozentzahl, Richtung, Erklärsatz.

Alles aus den Daten der Bauzeit (Laufzeit, Tarifnamen, Lücken); nichts davon
ist fest verdrahtet. Die Rechnung steht in `geraete_hersteller`.
"""

from __future__ import annotations

import math

from .geraete_preisposition_preise import FEHLT_TEXT, LAUFZEIT

EIGEN = "Vodafone"
GLEICHAUF = 1
KLEIN = 3
MINUS = "−"
NBSP = "\u00a0"


def runde(x: float) -> int:
    """Kaufmännisch auf ganze Prozent - dieselbe Rundung wie `Math.round`."""
    return math.floor(x + 0.5)


def prozent_text(mittel: float) -> str:
    """„+12 %“ / „−17 %“ / „0 %“ (echtes Minus, geschütztes Leerzeichen)."""
    r = runde(mittel)
    vorzeichen = "+" if r > 0 else MINUS if r < 0 else ""
    return f"{vorzeichen}{abs(r)}{NBSP}%"


def richtung(mittel: float) -> str:
    """Bis ±`GLEICHAUF` % (der gezeigten, gerundeten Zahl) gilt „gleichauf“ -
    eine feste Schwelle, damit +1 und 0 nicht verschieden heißen."""
    if abs(runde(mittel)) <= GLEICHAUF:
        return "gleichauf"
    return "teurer" if mittel > 0 else "günstiger"


def modell_wort(n: int) -> str:
    """„4 Modelle“; unter `KLEIN` mit „nur“ (kleine Stichprobe)."""
    wort = f"{n} Modell" if n == 1 else f"{n} Modelle"
    return f"nur {wort}" if n < KLEIN else wort


def tarif_text(tarife: dict[str, list[str]], spalten: list[str]) -> str:
    """„Vodafone: Vodafone Mobil M · Telekom: MagentaMobil M · ...“ - die Namen
    stehen so, wie die Daten sie führen; ein Anbieter ohne Namen entfällt."""
    teile = [
        f"{a}: {' / '.join(tarife[a])}" for a in (EIGEN, *spalten) if tarife.get(a)
    ]
    return " · ".join(teile)


def erklaerung(
    tarife: dict[str, list[str]],
    spalten: list[str],
    wettbewerber_ohne: list[str],
    ohne_hersteller: list[str],
) -> list[str]:
    """Die Absätze unter dem Bild; Lücken stehen mit Namen, alles aus den Daten."""
    absaetze = [
        f"Die Prozentzahl sagt, um wie viel die Gesamtkosten über {LAUFZEIT} Monate "
        f"(Gerät mit {LAUFZEIT} Raten, neu, plus Tarif) bei Vodafone über (+) oder "
        f"unter ({MINUS}) dem Wettbewerber liegen; bis ±{GLEICHAUF}{NBSP}% gilt als "
        f"gleichauf. Es zählen die aktuellen Modelle: je Reihe die neueste "
        f"Generation, mit dem kleinsten Speicher, zu dem Vodafone einen Preis hat, "
        f"und nur dort, wo auch der Wettbewerber einen frischen Preis führt."
    ]
    tarife_satz = tarif_text(tarife, spalten)
    if tarife_satz:
        absaetze.append(f"Verglichene Tarife: {tarife_satz}.")
    absaetze.append(
        f"„Alle Hersteller“ ist das Mittel über alle Modelle, also nach Modellzahl "
        f"gewichtet. Zellen mit weniger als {KLEIN} Modellen sind blasser und als "
        f"kleine Stichprobe benannt; die Modellzahl steht in jeder Zelle, weil sie "
        f"mit dem Zeitraum wechseln kann."
    )
    if wettbewerber_ohne:
        namen = " und ".join(wettbewerber_ohne)
        absaetze.append(
            f"{namen}: {FEHLT_TEXT} - Angebote mit anderer Laufzeit zählen nicht, "
            f"deshalb bleibt die Spalte weg."
        )
    if ohne_hersteller:
        absaetze.append(f"Ohne Vodafone-Preis: {', '.join(ohne_hersteller)}.")
    return absaetze
