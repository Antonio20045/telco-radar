"""Die Brechungskarte des Liquid-Glass-Umschalters (Antonio, 11.10.2026).

Ein Umschalter aus "Liquid Glass" biegt den Inhalt darunter an seinen
runden Kanten wie eine Linse. Die Karte dafür rechnet der Server einmal:
Rot verschiebt waagerecht, Grün senkrecht, 128 heißt keine Verschiebung.
Der Browser legt sie über ``feDisplacementMap`` auf den Hintergrund.

Die Karte liegt als fertige Datei unter ``templates/static/glas-linse.png``,
nicht als PNG-Bytes im HTML: die Bytes hängen von der zlib-Fassung ab, die
Pixel nicht (Golden-Seiten auf Antonios Mac, 12.10.2026). Neu schreiben mit
``python -m telco_radar.report.glas``; ein Test vergleicht Datei und Rechnung.

Rechenweg übernommen aus https://github.com/shuding/liquid-glass
(MIT License, Copyright (c) 2025 Shu Ding; Lizenztext in
``templates/static/lizenzen/liquid-glass.txt``).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

from PIL import Image

BREITE = 240
HOEHE = 60
DATEI = "static/glas-linse.png"
PFAD = Path(__file__).parent / "templates" / DATEI


@dataclass(frozen=True)
class Karte:
    """Pfad der Karte unter der Seite, größte Verschiebung, Größe in Pixeln."""

    datei: str
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


def _staerke(werte: list[tuple[float, float]]) -> float:
    return max(max(abs(dx), abs(dy)) for dx, dy in werte) * 0.5


def bild(breite: int = BREITE, hoehe: int = HOEHE) -> Image.Image:
    """Rechnet die Brechungskarte als Bild."""
    werte = verschiebungen(breite, hoehe)
    groesste = _staerke(werte)
    ergebnis = Image.new("RGB", (breite, hoehe))
    ergebnis.putdata(
        [(_kanal(dx / groesste), _kanal(dy / groesste), 0) for dx, dy in werte]
    )
    return ergebnis


def karte() -> Karte:
    """Die Angaben, mit denen die Seite die fertige Karte einbindet."""
    staerke = round(_staerke(verschiebungen()), 2)
    return Karte(datei=DATEI, staerke=staerke, breite=BREITE, hoehe=HOEHE)


def _kanal(wert: float) -> int:
    return max(0, min(255, int((wert + 0.5) * 255)))


if __name__ == "__main__":
    bild().save(PFAD, "PNG", optimize=True)
