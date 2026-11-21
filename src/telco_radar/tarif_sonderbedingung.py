"""Tarife mit Sonderbedingung: am Namen erkennbar, nicht im Preisvergleich.

Die Tarifwelt (Saturn/MediaMarkt) führt neben vergleichbaren Tarifen solche mit
Sonderbedingung (Young, Kids, Senior, Aktion, Doppelkarte, „2x“). Die Messung nimmt
sie nicht in den Vergleich; die Angebotszählung (``geraete_angebot.einhaengen``)
zählt sie trotzdem als Angebot und benennt die Lücke mit diesem Grund, statt sie
„unbenannt“ zu lassen. Die Liste ist fachlich dieselbe wie
``collect.geraete.tarifwelt_merkmale.NAMENSMERKMALE``; dieses Modul importiert den
Sammler bewusst nicht (der Zähler bleibt unabhängig), ein Test hält beide gleich.
"""

from __future__ import annotations

NAMENSMERKMALE = ("young", "aktion", "kids", "senior", "doppelkarte", "2x")
GRUND = "Tarif mit Sonderbedingung ({merkmal}), nicht im Vergleich"


def sonderbedingung(name: str) -> str | None:
    """Der Grund, wenn der Tarifname eine Sonderbedingung nennt; sonst ``None``."""
    klein = (name or "").lower()
    for merkmal in NAMENSMERKMALE:
        if merkmal in klein:
            return GRUND.format(merkmal=merkmal.capitalize())
    return None
