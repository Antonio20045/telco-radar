"""Legt die Handyfassungen (1200 px) der Motive neu an und räumt alte weg.

Aufruf mit ``PYTHONPATH=src`` nach jedem neuen oder getauschten Bild unter
``src/telco_radar/report/templates/static/bilder/``. Fehlt eine Fassung,
laden Handys das große Bild; ein falsches Motiv kann nie erscheinen, weil
der Dateiname den Inhalt des Originals trägt.
"""

from __future__ import annotations

from pathlib import Path

from telco_radar import bild_vorschau

WURZEL = Path(__file__).resolve().parent.parent

BILDER = WURZEL / "src" / "telco_radar" / "report" / "templates" / "static" / "bilder"


def main() -> int:
    """Schreibt fehlende Fassungen und löscht solche ohne passendes Original."""
    gueltig = set()
    for bild in sorted(BILDER.glob("*.jpg")):
        ziel = BILDER / bild_vorschau.KLEIN_ORDNER / bild_vorschau.kleiner_name(bild)
        if not ziel.exists():
            ziel = bild_vorschau.schreibe_kleine_fassung(bild) or ziel
        gueltig.add(ziel.name)
    ordner = BILDER / bild_vorschau.KLEIN_ORDNER
    for alt in sorted(ordner.glob("*.jpg")) if ordner.is_dir() else []:
        if alt.name not in gueltig:
            alt.unlink()
    print(f"{len(gueltig)} Motive geprüft, Fassungen in {ordner}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
