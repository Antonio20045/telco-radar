"""Der Chip an einer Bündelzeile, deren Preis nicht von heute ist.

Preisprüfung 11.10.2026: ein Telekom-Preis vom 10.10. sah aus wie einer von heute.
Eine Zeile, die frisch genug für den Vergleich ist (``geraete_tco_karten.ist_frisch``),
aber nicht von heute, trägt „Preis vom 10.10.2026“; jenseits der Frische gilt
„kein aktueller Stand seit …“ (``geraete_tco_karten.alt_marke_fuer``).
"""

from __future__ import annotations


def marke(abgerufen_am: str, heute: str, frisch: bool) -> str:
    """Der Chip der Zeile; eine Zeile von heute (oder ohne ``heute``) trägt keinen."""
    from .geraete_tco_karten import alt_marke_fuer, kurz_datum

    if not frisch:
        return alt_marke_fuer(abgerufen_am)
    if not heute or abgerufen_am == heute:
        return ""
    return f"Preis vom {kurz_datum(abgerufen_am)}"
