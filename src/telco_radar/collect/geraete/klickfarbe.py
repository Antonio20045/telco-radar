"""SKU-Farbe der Klick-Sätze aus ``config/klick_farben.yaml`` (1&1, 20.11.2026).

Die Klick-Karte klickt keine Farbe; ihre Sätze tragen sonst die SKU „…-ohne-farbe“.
Die 1&1-Bündel im Bestand tragen die Farbe, die der Adapter bis zum 20.11.2026 las
(erste Variante der Preiskarte, nicht die vorgewählte der Seite). Damit dieselbe
Kombination dasselbe Bündel bleibt, nennt die Datei je Anbieter, Gerät und Speicher
diese Farbe (Herleitung im Kopf der Datei). Fehlt der Eintrag oder die Datei, gibt es
keine Farbe (``None``): die SKU bleibt „ohne-farbe“, nie eine geratene. Rein, liest
nur die eine Datei.
"""

from __future__ import annotations

import logging
from functools import cache
from pathlib import Path

import yaml

log = logging.getLogger(__name__)

DATEI = Path(__file__).resolve().parents[4] / "config" / "klick_farben.yaml"


def sku_farbe(
    anbieter: object, geraet_id: str, gb: int, datei: Path | None = None
) -> str | None:
    """Die Farbe der SKU für ``anbieter``, ``geraet_id`` und ``gb``; sonst ``None``."""
    return _farben(str(datei or DATEI)).get((str(anbieter), geraet_id, gb))


@cache
def _farben(pfad: str) -> dict[tuple[str, str, int], str]:
    try:
        roh = yaml.safe_load(Path(pfad).read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as fehler:
        log.warning("Klick-Farben %s nicht lesbar: %s", pfad, fehler)
        return {}
    farben: dict[tuple[str, str, int], str] = {}
    anbieter = roh.get("anbieter") if isinstance(roh, dict) else None
    for name, geraete in (anbieter or {}).items():
        for geraet, je_gb in (geraete or {}).items():
            for gb, farbe in (je_gb or {}).items():
                if isinstance(gb, int) and isinstance(farbe, str) and farbe.strip():
                    farben[(str(name), str(geraet), gb)] = farbe.strip()
    return farben
