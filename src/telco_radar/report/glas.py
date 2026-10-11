"""Die Brechungskarte des Liquid-Glass-Umschalters (Antonio, 11.10.2026).

Ein Umschalter aus "Liquid Glass" biegt den Inhalt darunter an seinen
runden Kanten wie eine Linse. Die Karte dafür rechnet der Server einmal:
Rot verschiebt waagerecht, Grün senkrecht, 128 heißt keine Verschiebung.
Der Browser legt sie über ``feDisplacementMap`` auf den Hintergrund.

Rechenweg übernommen aus https://github.com/shuding/liquid-glass
(MIT License, Copyright (c) 2025 Shu Ding; Lizenztext in
``templates/static/lizenzen/liquid-glass.txt``).
"""

from __future__ import annotations

import base64
import io
import math
from dataclasses import dataclass

from PIL import Image

BREITE = 240
HOEHE = 60


@dataclass(frozen=True)
class Karte:
    """Die Karte als data-URL, die größte Verschiebung und die Rechengröße in Pixeln."""

    url: str
    staerke: float
    breite: int
    hoehe: int


def _sanft(a: float, b: float, t: float) -> float:
    t = max(0.0, min(1.0, (t - a) / (b - a)))
    return t * t * (3 - 2 * t)


def _rund(x: float, y: float, breite: float, hoehe: float, radius: float) -> float:
    qx = abs(x) - breite + radius
    qy = abs(y) - hoehe + radius
    return min(max(qx, qy), 0.0) + math.hypot(max(qx, 0.0), max(qy, 0.0)) - radius


def _linse(u: float, v: float) -> tuple[float, float]:
    ix = u - 0.5
    iy = v - 0.5
    rand = _rund(ix, iy, 0.3, 0.2, 0.6)
    verschiebung = _sanft(0.8, 0.0, rand - 0.15)
    faktor = _sanft(0.0, 1.0, verschiebung)
    return ix * faktor + 0.5, iy * faktor + 0.5


def verschiebungen(
    breite: int = BREITE, hoehe: int = HOEHE
) -> list[tuple[float, float]]:
    """Je Pixel, zeilenweise, wie weit die Linse ihn holt (dx, dy in Pixeln)."""
    werte = []
    for y in range(hoehe):
        for x in range(breite):
            px, py = _linse(x / breite, y / hoehe)
            werte.append((px * breite - x, py * hoehe - y))
    return werte


def karte(breite: int = BREITE, hoehe: int = HOEHE) -> Karte:
    """Rechnet die Brechungskarte als PNG-data-URL."""
    werte = verschiebungen(breite, hoehe)
    groesste = max(max(abs(dx), abs(dy)) for dx, dy in werte) * 0.5
    bild = Image.new("RGB", (breite, hoehe))
    bild.putdata(
        [(_kanal(dx / groesste), _kanal(dy / groesste), 0) for dx, dy in werte]
    )
    puffer = io.BytesIO()
    bild.save(puffer, "PNG", optimize=True)
    url = "data:image/png;base64," + base64.b64encode(puffer.getvalue()).decode("ascii")
    return Karte(url=url, staerke=round(groesste, 2), breite=breite, hoehe=hoehe)


def _kanal(wert: float) -> int:
    return max(0, min(255, int((wert + 0.5) * 255)))
