"""Die Zeitreihen-Fragmente einer gebauten Seite als ein Text (je Modell `data/zr/`)."""

from __future__ import annotations

from pathlib import Path


def lies(daten: Path) -> str:
    """Alle Dateien unter ``daten/zr`` in Namensfolge; fehlt der Ordner, wirft das."""
    dateien = sorted((Path(daten) / "zr").glob("*.html"))
    if not dateien:
        raise FileNotFoundError(f"{daten}/zr ohne Zeitreihen-Fragment")
    return "".join(p.read_text(encoding="utf-8") for p in dateien)
