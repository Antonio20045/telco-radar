"""Die "Plus"-Fassung eines o2-Tarifs ist ein eigener Tarif mit eigener ID.

Die SIM-only-Kachel "O2 Mobile on Demand M" verlinkt den Slug
`o2-mobile-on-demand-m-plus`. Das Buendel dahinter ist aber nicht der Tarif der
Kachel: sein Preis enthaelt den Bundle-Rabatt, der nur mit einem Zweitprodukt
gilt. Truege es die ID der Kachel (`o2:o2-mobile-on-demand-m`), ueberschrieben
sich M und M Plus im Bestand (je Tarif, Geraet und Laufzeit gilt der letzte
Satz), und die Kachel-Grundgebuehr stuende als SIM-only-Vergleich neben einem
Preis, der sie nie gemeint hat.
"""

from __future__ import annotations

ANBIETER = "o2"
PLUS_SLUG = "-plus"
"""Endung des o2-Slugs der Fassung "Plus" eines Tarifs:
`o2-mobile-unlimited-l-plus` zum Grundtarif `o2-mobile-unlimited-l`."""


def plus_fassung(
    anbieter: str, slug: str, tid: str, kachel: dict
) -> tuple[str, str] | None:
    """(Tarif-ID, Grund) der Plus-Fassung zum Slug einer Kachel, sonst None.

    `tid` ist die ID des Slugs selbst (`tarif_id(anbieter, slug)`). Nur fuer o2,
    nur bei einem Slug auf `-plus` und nur, wenn die Kachel eine andere ID traegt.
    """
    if anbieter != ANBIETER or not slug.endswith(PLUS_SLUG):
        return None
    if tid == kachel.get("tarif_id"):
        return None
    return tid, (
        f"Plus-Fassung der SIM-only-Kachel {kachel.get('name', '')!r}: eigener Tarif "
        f"(Slug {slug!r}), Preis nur mit Zweitprodukt"
    )


def mit_plus(baender: dict) -> dict:
    """Jede Plus-Fassung steht im Band ihres Grundtarifs, falls sie keines hat."""
    for tid, band in list(baender.items()):
        baender.setdefault(tid + PLUS_SLUG, band)
    return baender
