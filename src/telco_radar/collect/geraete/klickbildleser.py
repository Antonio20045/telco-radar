"""Leser mit Bildfolge: nimmt die drei Wahl-Schritte auf (``klickbildfolge``).

``Leser`` (``klicklesung``) erbt davon. ``nimm_bildfolge`` läuft einmal je Lesung,
nachdem alle Dimensionen gewählt sind und bevor ein Dialog der Zusammenfassung sie
verdeckt; ``folgefelder`` gibt die Bilder und Lücken dieser Lesung an die Belegquelle
weiter. Dieses Modul ruft kein Netz.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .klickbildfolge import Folgebild, lies_folge
from .klicktextleser import Textleser


class Bildleser(Textleser):
    """Textleser, der die Bilder der Wahl-Schritte der letzten Lesung hält."""

    modell: str | None = None
    folge: Mapping[str, Folgebild] = {}
    folge_fehlt: Mapping[str, str] = {}

    def nimm_bildfolge(self, ziel: Mapping[str, str | None]) -> None:
        """Nimmt die Bilder für ``ziel`` auf; vergisst die der Lesung davor."""
        self.folge, self.folge_fehlt = lies_folge(
            self.seite, self.karte, ziel, self.frist_ms
        )

    def folgefelder(self) -> dict[str, Any]:
        """Die Felder der Belegquelle zur Bildfolge."""
        return {
            "folge": self.folge,
            "folge_fehlt": self.folge_fehlt,
            "modell": self.modell,
        }
