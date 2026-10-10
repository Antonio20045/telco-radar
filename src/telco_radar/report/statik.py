"""Die statischen Dateien des Designs: Logo, Schrift und Bilder.

Alles liegt neben den Vorlagen unter ``templates/static/`` und wird bei jedem
Rendern vollständig nach ``site/static/`` gespiegelt. Ein Bild, das im
Vorlagenordner fehlt, fehlt danach auch auf der Seite, und die Vorlagen
zeigen an seiner Stelle eine ruhige Fläche statt eines kaputten Bildes.

Zu jedem Bild gehört eine winzige Vorschau als data-URL (``bild_vorschau``).
Die Vorlagen legen sie als Hintergrund unter das Bild, damit beim Laden
sofort dessen Farben stehen und keine fremde Fläche aufblitzt (Antonio,
10.10.2026).
"""

from __future__ import annotations

import shutil
from pathlib import Path

from ..bild_vorschau import kleine_fassungen, vorschau

ORDNER = "static"
BILDER = "bilder"
BINAER = ("logo.png",)


def kopiere(vorlagen: Path, site_dir: Path) -> dict[str, str]:
    """Spiegelt Logo und ``static/`` in die Website und nennt die Bildnamen.

    Zurück kommen die Dateinamen ohne Endung aus ``static/bilder/``, je mit
    ihrer Vorschau. Die Vorlagen fragen damit, ob ein Motiv vorhanden ist,
    bevor sie es setzen.
    """
    for name in BINAER:
        quelle = vorlagen / name
        if quelle.exists():
            shutil.copy(quelle, site_dir / name)
    ziel = site_dir / ORDNER
    shutil.rmtree(ziel, ignore_errors=True)
    statik = vorlagen / ORDNER
    if not statik.is_dir():
        return {}
    shutil.copytree(statik, ziel)
    bilder = statik / BILDER
    if not bilder.is_dir():
        return {}
    return {
        b.stem: vorschau(b)
        for b in sorted(bilder.iterdir())
        if b.is_file() and b.suffix == ".jpg"
    }


def kleine(vorlagen: Path) -> dict[str, str]:
    """Je Motiv der Pfad seiner 1200-px-Fassung unter ``static/bilder/``."""
    return kleine_fassungen(vorlagen / ORDNER / BILDER)
