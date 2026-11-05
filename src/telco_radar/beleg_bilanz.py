"""Zähler und Protokollzeilen eines Belege-Laufs (``beleg_ablage``)."""

from __future__ import annotations

from dataclasses import dataclass, field

BEISPIELE_DOPPELT = 5


@dataclass
class Bilanz:
    """Zähler und Fehler eines Laufs."""

    hochgeladen: int = 0
    gross: int = 0
    ausgelassen: int = 0
    fehlgeschlagen: int = 0
    fehler: list[str] = field(default_factory=list)
    releases_geloescht: list[str] = field(default_factory=list)
    assets_geloescht: int = 0
    doppelt: list[str] = field(default_factory=list)

    def zeilen(self) -> list[str]:
        """Protokollzeilen."""
        return [
            f"Belege: {self.hochgeladen} Bilder in Tages-Releases, {self.gross} in "
            f"Monats-Releases (große Änderungen), {self.ausgelassen} ausgelassen "
            f"(Zeit), {self.fehlgeschlagen} fehlgeschlagen, {len(self.fehler)} Fehler",
            f"Belege: {len(self.releases_geloescht)} Releases und "
            f"{self.assets_geloescht} Dateien gelöscht",
        ]

    def hinweise(self) -> list[str]:
        """Eine Zeile, wenn Namen mehrfach übergeben, aber nur einmal geladen wurden."""
        if not self.doppelt:
            return []
        beispiele = ", ".join(self.doppelt[:BEISPIELE_DOPPELT])
        mehr = len(self.doppelt) - BEISPIELE_DOPPELT
        rest = f" und {mehr} weitere" if mehr > 0 else ""
        return [
            f"Belege: {len(self.doppelt)} Dateinamen mehrfach übergeben, je einmal "
            f"hochgeladen: {beispiele}{rest}"
        ]
