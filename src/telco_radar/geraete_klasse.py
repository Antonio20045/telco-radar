"""Die Geräteklasse eines Katalogeintrags, aus den Wortmarken seiner Geräte-ID.

Eine Übersichtsseite deckt nur Klassen ab: die Smartphone-Übersicht der Telekom und
„Alle Smartphones“ bei 1&1 belegen nichts über Zubehör, Tablets oder Uhren. Das
Telekom-Zubehörportal führte AirPods 5 für 144 EUR, als der Radar „bei Telekom nicht
im Angebot (Übersicht ganz gelesen)“ sagte (Stichprobe 10.11.2026). Welche Klassen die
Übersicht eines Anbieters abdeckt, steht in ``config/klick_tageslauf.yaml``
(``uebersicht_klassen``, gelesen von ``klickziele.uebersicht_klassen``); hier steht nur,
wie eine Klasse aus dem Namen folgt. Ohne Wortmarke einer anderen Klasse gilt ein
Katalogeintrag als Telefon, denn der Katalog führt Telefone, und eine neue Klasse
braucht hier genau eine Zeile.
"""

from __future__ import annotations

TELEFON = "telefon"
TABLET = "tablet"
UHR = "uhr"
AUDIO = "audio"
KLASSEN = frozenset({TELEFON, TABLET, UHR, AUDIO})
_WORTMARKEN = {
    TABLET: frozenset({"ipad", "tab", "tablet"}),
    UHR: frozenset({"watch"}),
    AUDIO: frozenset({"airpods", "buds"}),
}


def geraeteklasse(device_id: str) -> str:
    """Die Klasse einer Geräte-ID (``TELEFON`` ohne Wortmarke anderer Klasse)."""
    marken = set(device_id.split("-"))
    for klasse, woerter in _WORTMARKEN.items():
        if marken & woerter:
            return klasse
    return TELEFON
