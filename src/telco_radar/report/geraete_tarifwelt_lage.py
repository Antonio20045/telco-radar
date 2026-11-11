"""Liefert die Tarifwelt (Saturn/MediaMarkt mit Tarif)? Gelesen an den Bündeln.

Die Quellenlage zählt Gerätelistungen je Quellenname. Die Tarifwelt liefert keine
Listungen, sondern Bündel, und die stehen unter ihren Netzzeilen („Saturn/MediaMarkt ·
Telekom-Netz“), nicht unter dem Namen der Quelle. Die Radar-Tafel nannte sie darum
unter „Welche Händler keine Daten liefern“ mit „Die Seite gibt ihre Preise nicht
heraus“, während ihre Preise auf derselben Seite standen (Prüfung 11.11.2026).
"""

from __future__ import annotations

from ..tarifwelt_bestand import METHODE, PRAEFIX


def liefert(tco: dict) -> bool:
    """Trägt die Tafel ein frisches Tarifwelt-Bündel mit Preis?"""
    return any(
        str(k.get("tarif_id") or "").startswith(PRAEFIX)
        and k.get("frisch")
        and k.get("gesamt") is not None
        for modell in (tco or {}).get("modelle") or []
        for k in modell.get("karten") or []
    )


def ohne_lieferndes(fehlt: list[dict], quellenlage: dict, tco: dict) -> list[dict]:
    """Die Liste der Händler ohne Daten, ohne die Tarifwelt-Quelle, wenn sie liefert."""
    if not liefert(tco):
        return fehlt
    quellen = {
        z.get("name")
        for z in (quellenlage or {}).get("zeilen") or []
        if z.get("methode") == METHODE
    }
    return [z for z in fehlt if z["anbieter"] not in quellen]
