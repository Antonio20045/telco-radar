"""Notbremse der Geräteseite: welche Karte in Sieger, Δ und Kernzahl zählt.

Datenkonzept Geräteradar, Schritt 1 (docs/datenkonzept-geraete.md): Nur gemessene
Bündel zählen. Ein Bündel mit ``herleitung`` (1&1 aus dem Tarifraster, o2 aus
Tarifsumme minus Geräterate) stand so nie auf der Anbieterseite und ist eine
Schätzung. Ein Bündel, in dessen Preis eine abgelaufene Aktion steckt, ist veraltet.
Beide bleiben als Zeile sichtbar, stellen aber weder Δ noch Referenz noch Sieger.
"""

from __future__ import annotations

from ..tco_model import Buendel

DELTA_SCHAETZUNG = "Schätzung"
SATZ_SCHAETZUNG = "Kein Abstand zur Vodafone-Referenz: dieser Preis ist abgeleitet."
DELTA_AKTION_ABGELAUFEN = "Aktion abgelaufen"
SATZ_AKTION_ABGELAUFEN = (
    "Kein Abstand zur Vodafone-Referenz: die eingerechnete Aktion ist abgelaufen."
)


def felder(b: Buendel, heute: str) -> dict:
    """Die Notbremse-Felder einer Karte: Flags, ``zaehlt``, benannter Zustand.

    Abgelaufen ist eine eingerechnete Aktion, die der Anbieter vor ``heute``
    befristet hat (``Aktion.gilt_am``); ein Platzhalter-Ende wie 2050 läuft weiter.
    """
    schaetzung = bool(b.herleitung.strip())
    veraltet = any(a.eingerechnet and not a.gilt_am(heute) for a in b.aktionen)
    flags = {"schaetzung": schaetzung, "veraltet_aktion": veraltet}
    return {
        **flags,
        "zaehlt": not schaetzung and not veraltet,
        "notbremse": zustand(flags),
    }


def zaehlt(karte: dict) -> bool:
    """Darf die Karte Δ, Referenz oder Sieger stellen? Karten ohne die Felder
    (Listungen ohne Bündel) zählen wie bisher."""
    return karte.get("zaehlt", True)


def zustand(karte: dict) -> dict | None:
    """Der benannte Δ-Zustand einer Karte, die nicht zählt, sonst ``None``."""
    if karte.get("schaetzung"):
        return {"kurz": DELTA_SCHAETZUNG, "satz": SATZ_SCHAETZUNG}
    if karte.get("veraltet_aktion"):
        return {"kurz": DELTA_AKTION_ABGELAUFEN, "satz": SATZ_AKTION_ABGELAUFEN}
    return None
