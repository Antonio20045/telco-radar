"""Pfade in den Schnappschuss, aus dem die Tests den Bestand lesen (wie ``data/``)."""

from __future__ import annotations

import atexit
import functools
import shutil
import tempfile
from pathlib import Path

WURZEL = Path(__file__).resolve().parents[1]
BESTAND = WURZEL / "tests" / "fixtures" / "bestand" / "2026-10-03"
ZUSTAND = BESTAND / "state"
BERICHTE = BESTAND / "reports"
NEBEN_DATA = ("config", "content")
AUTO_KATALOG = "geraete_katalog_auto.json"


def verlinke_neben_data(ziel: Path) -> None:
    """Verweist unter ``ziel`` auf die echten Ordner neben ``data/``."""
    for name in NEBEN_DATA:
        (ziel / name).symlink_to(WURZEL / name, target_is_directory=True)


def abbild(ziel: Path) -> Path:
    """Legt unter ``ziel`` ein Repo-Abbild an und gibt dessen Berichtsordner zurück.

    ``data/`` ist eine Kopie des Schnappschusses, damit ein Render ihn nie verändert.
    """
    shutil.copytree(
        BESTAND, ziel / "data", ignore=shutil.ignore_patterns("_herkunft.json")
    )
    verlinke_neben_data(ziel)
    return ziel / "data" / "reports"


@functools.cache
def lese_wurzel() -> Path:
    """Eine Repo-Wurzel mit dem Auto-Katalog des Schnappschusses unter ``data/state``,
    für ``lade_katalog``; eine Kopie, damit kein Aufrufer den Schnappschuss ändert."""
    ziel = Path(tempfile.mkdtemp(prefix="bestand-"))
    atexit.register(shutil.rmtree, ziel, ignore_errors=True)
    (ziel / "data" / "state").mkdir(parents=True)
    shutil.copy2(ZUSTAND / AUTO_KATALOG, ziel / "data" / "state" / AUTO_KATALOG)
    verlinke_neben_data(ziel)
    return ziel
