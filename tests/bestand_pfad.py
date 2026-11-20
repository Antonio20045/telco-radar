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
BILDER_BESTAND = WURZEL / "tests" / "fixtures" / "bestand" / "2026-08-08"
"""Die Ausgabe 2026-08-08 mit den 52 Meldungsbildern, auf die sie zeigt."""
BILDER_ZUSTAND = WURZEL / "tests" / "fixtures" / "bestand" / "2026-10-02" / "state"
"""Promo- und Meldungsbilder zum Bestand 2026-10-03 (``promo_db.json`` ist gleich)."""
ARCHIV = BILDER_ZUSTAND.parent / "reports"
"""Alle Ausgaben ab 2026-08-06, seit die Berichte Bildbreiten tragen."""
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


KACHELN = (
    WURZEL / "tests" / "fixtures" / "klickliste" / "telekom_uebersichten_20261120.json"
)
"""Die fünf Telekom-Übersichten des Klick-Laufs vom 20.11.2026 (nur Titel, Speicher,
Produktlink): Quelle der Telekom-Seiten (``klickliste_kacheln``)."""


@functools.cache
def kachel_wurzel() -> Path:
    """Wie ``lese_wurzel``, dazu ``data/state/klick/telekom.json`` aus ``KACHELN``:
    die Telekom-Einträge der Tagesdatei bekommen daraus ihre Seiten."""
    ziel = Path(tempfile.mkdtemp(prefix="kacheln-"))
    atexit.register(shutil.rmtree, ziel, ignore_errors=True)
    (ziel / "data" / "state" / "klick").mkdir(parents=True)
    shutil.copy2(ZUSTAND / AUTO_KATALOG, ziel / "data" / "state" / AUTO_KATALOG)
    shutil.copy2(KACHELN, ziel / "data" / "state" / "klick" / "telekom.json")
    verlinke_neben_data(ziel)
    return ziel
