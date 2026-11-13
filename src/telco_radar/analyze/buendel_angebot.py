"""Was eine Bündel-ID über das ANGEBOT sagt: Modell, Speicherstufe und - für den
Tagesvergleich - dieselbe Kombination ohne Farbe.

`buendel_abdeckung` fragt beim Vergleich zweier Messtage "ist dieses Angebot
weg?". Die Farbe gehört zu dieser Frage nicht: bei der Telekom ist sie nicht
einmal stabil. Dieselbe Produktseite
(`.../apple-iphone-17-pro/tiefblau-256-gb`, gemessen 13.11.2026) steht am selben
Messtag einmal als `tiefblau` und einmal als `ohne-farbe` in der ID, am Vortag
stand sie als `cosmic-orange`. Wer auf der vollen ID vergleicht, meldet einen
Wegfall, wo nur die Farbangabe der Quelle gewechselt hat - Lauf 43401542782 war
genau deshalb rot: alle fünf Telekom-Kombinationen vom 12.11. waren am 13.11.
unter anderer Farbe da. Die Farbe bleibt in der ID und auf der Seite, sie fällt
NUR aus diesem Vergleich heraus (CLAUDE.md Clean Code 4).
"""

from __future__ import annotations

import re

_SKU_MUSTER = re.compile(r"^(?P<modell>.+?)-(?P<speicher>\d+gb|ohne-speicher)-")


def modell_und_speicher(sku_id: str) -> tuple[str | None, str | None]:
    """Katalogmodell und Speicherstufe aus der SKU-ID
    (`geraete_model.sku_id`: Gerät-Speicher-Farbe[-Zustand])."""
    treffer = _SKU_MUSTER.match(sku_id or "")
    if not treffer:
        return None, None
    return treffer.group("modell"), treffer.group("speicher")


def angebot_ohne_farbe(buendel_id: str) -> str:
    """Dieselbe Kombination ohne Farbe: Anbieter, Modell, Speicher, Tarif,
    Laufzeit. Eine ID ohne lesbare SKU bleibt, wie sie ist."""
    teile = (buendel_id or "").split("--")
    if len(teile) < 3:
        return buendel_id or ""
    modell, speicher = modell_und_speicher(teile[2])
    if modell is None:
        return buendel_id or ""
    teile[2] = f"{modell}-{speicher}"
    return "--".join(teile)
