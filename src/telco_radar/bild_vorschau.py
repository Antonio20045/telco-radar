"""Winzige Vorschau eines Motivs als data-URL.

Liegt ausserhalb von ``report/``, weil die Seiten dort keine Dateien oeffnen;
``report.statik`` ruft sie beim Spiegeln der Bilder.
"""

from __future__ import annotations

import base64
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
