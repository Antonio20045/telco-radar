"""Vodafone-Preis in Prüfung: kein Ersatzwert im Vergleich (Prüfung 11.11.2026).

Befund am Galaxy S26 256 GB: Vodafone hatte am 10.11. die Geräterate gesenkt, die
Prüfstelle hielt alle eigenen Bündel zurück (Regel 11). Weil damit kein eigenes Bündel
mehr zählte, sprang die Näherung ein (günstigster Vodafone-Tarif ohne Gerät plus
Barpreis, 1.518,70 €) und stand im Radar als gewöhnliche Vodafone-Zahl neben 1&1
(„18,9 % günstiger“) - ein Preis, den Vodafone so nicht anbietet und der 327 € über
dem zurückgehaltenen Bündel lag.

Die Regel: Führt Vodafone frische, gemessene Bündel, die nur deshalb nicht zählen,
weil die Prüfstelle sie zurückhält (Quarantäne oder gescheiterte Prüfung), dann stellt
nichts an ihrer Stelle eine Zahl. Das Modell hat keine Vodafone-Referenz, jeder
Vergleich nennt „Vodafone-Preis wird geprüft“. Die Näherung bleibt für Geräte, zu
denen Vodafone gar kein Bündel führt.
"""

from __future__ import annotations

from .geraete_preisstand import in_pruefung

KURZ = "Vodafone-Preis wird geprüft"
SATZ = (
    "Kein Abstand zu Vodafone: der aktuelle Vodafone-Preis für dieses Gerät wird "
    "geprüft und zählt bis dahin in keinem Vergleich."
)
KURZ_NICHT_ERHOBEN = "keine Vodafone-Kosten erhoben"
SATZ_NICHT_ERHOBEN = (
    "Keine Vodafone-Kosten für dieses Gerät erhoben – "
    "kein Bündel und kein eigener Barpreis."
)


def zurueckgehalten(karten: list) -> bool:
    """Hält die Prüfstelle ein frisches, gemessenes Vodafone-Bündel zurück?

    Gemessen heißt: die Karte hat eine SKU (die Näherung und die Leerkarte haben
    keine). Ein veraltetes Bündel ist kein Preis in Prüfung, sondern ein alter Stand.
    """
    return any(
        k.get("eigen")
        and k.get("sku_id")
        and k.get("frisch", True)
        and (in_pruefung(k) or k.get("pruefung_gescheitert"))
        for k in karten
    )


def ohne_basis(modell: dict) -> dict:
    """Warum das Modell keine Vodafone-Basis hat: Kurzwort und Satz für den Radar."""
    if zurueckgehalten(modell.get("karten") or []):
        return {"vodafone_luecke": KURZ, "vodafone_grund": SATZ}
    return {"vodafone_luecke": KURZ_NICHT_ERHOBEN, "vodafone_grund": SATZ_NICHT_ERHOBEN}


def ohne_referenz(modell: dict, sonst: tuple[str, str]) -> tuple[str, str]:
    """Kurzwort und Satz der Δ-Zelle eines Modells ohne Referenz; `sonst`, wenn
    Vodafone das Gerät gar nicht führt."""
    if zurueckgehalten(modell.get("karten") or []):
        return KURZ, SATZ
    return sonst
