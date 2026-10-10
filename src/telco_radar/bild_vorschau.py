"""Winzige Vorschau eines Motivs als data-URL.

Liegt ausserhalb von ``report/``, weil die Seiten dort keine Dateien oeffnen;
``report.statik`` ruft sie beim Spiegeln der Bilder.
"""

from __future__ import annotations

import base64
import hashlib
import io
from pathlib import Path

from PIL import Image

VORSCHAU_BREITE = 32
VORSCHAU_QUALITAET = 60


def vorschau(bild: Path) -> str:
    """Das Bild auf VORSCHAU_BREITE Pixel verkleinert, als JPEG-data-URL."""
    with Image.open(bild) as im:
        hoehe = max(1, round(im.height * VORSCHAU_BREITE / im.width))
        klein = im.convert("RGB").resize(
            (VORSCHAU_BREITE, hoehe), Image.Resampling.LANCZOS
        )
    puffer = io.BytesIO()
    klein.save(puffer, "JPEG", quality=VORSCHAU_QUALITAET)
    return "data:image/jpeg;base64," + base64.b64encode(puffer.getvalue()).decode()


KLEIN_BREITE = 1200
KLEIN_ORDNER = "1200"
KLEIN_QUALITAET = 82


def kleiner_name(bild: Path) -> str:
    """Name der Handyfassung; der Inhaltsschlüssel macht alte Fassungen ungültig."""
    schluessel = hashlib.sha256(bild.read_bytes()).hexdigest()[:10]
    return f"{bild.stem}-{schluessel}.jpg"


def kleine_fassungen(bilder: Path) -> dict[str, str]:
    """Je Motiv die passende Handyfassung unter ``1200/``, sofern sie zum Bild passt."""
    ordner = bilder / KLEIN_ORDNER
    if not ordner.is_dir():
        return {}
    vorhanden = {b.name for b in ordner.iterdir()}
    fassungen = {}
    for bild in sorted(bilder.glob("*.jpg")):
        name = kleiner_name(bild)
        if name in vorhanden:
            fassungen[bild.stem] = f"{KLEIN_ORDNER}/{name}"
    return fassungen


def schreibe_kleine_fassung(bild: Path) -> Path | None:
    """Legt die Handyfassung eines Bildes an, das breiter als KLEIN_BREITE ist."""
    with Image.open(bild) as im:
        if im.width <= KLEIN_BREITE:
            return None
        hoehe = round(im.height * KLEIN_BREITE / im.width)
        klein = im.convert("RGB").resize(
            (KLEIN_BREITE, hoehe), Image.Resampling.LANCZOS
        )
    ziel = bild.parent / KLEIN_ORDNER / kleiner_name(bild)
    ziel.parent.mkdir(exist_ok=True)
    klein.save(ziel, "JPEG", quality=KLEIN_QUALITAET, optimize=True, progressive=True)
    return ziel
