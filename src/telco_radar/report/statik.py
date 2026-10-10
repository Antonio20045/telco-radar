"""Die statischen Dateien des Designs: Logo, Schrift und Bilder.

Alles liegt neben den Vorlagen unter ``templates/static/`` und wird bei jedem
Rendern vollständig nach ``site/static/`` gespiegelt. Ein Bild, das im
Vorlagenordner fehlt, fehlt danach auch auf der Seite, und die Vorlagen
zeigen an seiner Stelle eine ruhige Fläche statt eines kaputten Bildes.
"""

from __future__ import annotations

import shutil
from pathlib import Path

ORDNER = "static"
BILDER = "bilder"
BINAER = ("logo.png",)


def kopiere(vorlagen: Path, site_dir: Path) -> set[str]:
    """Spiegelt Logo und ``static/`` in die Website und nennt die Bildnamen.

    Zurück kommen die Dateinamen ohne Endung aus ``static/bilder/``. Die
    Vorlagen fragen damit, ob ein Motiv vorhanden ist, bevor sie es setzen.
    """
    for name in BINAER:
        quelle = vorlagen / name
        if quelle.exists():
            shutil.copy(quelle, site_dir / name)
    ziel = site_dir / ORDNER
    shutil.rmtree(ziel, ignore_errors=True)
    statik = vorlagen / ORDNER
    if not statik.is_dir():
        return set()
    shutil.copytree(statik, ziel)
    bilder = statik / BILDER
    if not bilder.is_dir():
        return set()
    return {b.stem for b in bilder.iterdir() if b.is_file() and b.suffix == ".jpg"}
