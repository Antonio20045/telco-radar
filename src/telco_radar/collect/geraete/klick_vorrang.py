"""Die Topmodelle, deren Telekom-Seiten im Klick-Tageslauf Vorrang haben.

Katalog-IDs, nicht Präfixe: ein Präfix traf pixel-11-pro-fold und s26-fe und
verfehlte das iPhone 17 Pro (Befund 02.11.2026). Ein Test hält jede ID gegen den
Katalog.
"""

from __future__ import annotations

VORRANG_GERAETE = frozenset(
    {
        "apple-iphone-17",
        "apple-iphone-17-pro",
        "apple-iphone-17-pro-max",
        "apple-iphone-air",
        "apple-iphone-18-pro",
        "apple-iphone-18-pro-max",
        "samsung-galaxy-s26",
        "samsung-galaxy-s26-plus",
        "samsung-galaxy-s26-ultra",
        "google-pixel-11",
        "google-pixel-11-pro",
        "google-pixel-11-pro-xl",
    }
)
