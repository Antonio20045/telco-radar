"""Leser mit Bildfolge: nimmt die drei Wahl-Schritte auf (``klickbildfolge``).

``Leser`` (``klicklesung``) erbt davon. ``nimm_bildfolge`` läuft einmal je Lesung,
nachdem alle Dimensionen gewählt sind und bevor ein Dialog der Zusammenfassung sie
verdeckt; ``folgefelder`` gibt die Bilder und Lücken dieser Lesung an die Belegquelle
weiter. ``_screenshot`` liest den sichtbaren Text des Preisbereichs unmittelbar vor dem
Bild (``bildtext``): nur Beträge, die dort stehen, nennt der Text des Preisschritts.
Dieses Modul ruft kein Netz.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

from playwright.sync_api import Error as PlaywrightFehler

from .klickbildfolge import Folgebild, lies_folge
from .klickecho import Befund
from .klicktextleser import Textleser
from .klicktor import kurz

if TYPE_CHECKING:
    from playwright.sync_api import Locator


class Bildleser(Textleser):
    """Textleser, der die Bilder der Wahl-Schritte der letzten Lesung hält."""

    modell: str | None = None
    folge: Mapping[str, Folgebild] = {}
    folge_fehlt: Mapping[str, str] = {}
    bildtext: str | None = None

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
            "bildtext": self.bildtext,
        }

    def _screenshot(self, bereich: Locator) -> tuple[bytes | None, tuple[Befund, ...]]:
        """Das Bild des Preisbereichs; sein Text wird davor gelesen (``bildtext``)."""
        self.bildtext = None
        try:
            text = self._text(bereich)
            bild = bereich.screenshot(type="png", timeout=self.frist_ms)
        except PlaywrightFehler as fehler:
            return None, (Befund("screenshot", f"Screenshot fehlt: {kurz(fehler)}"),)
        self.bildtext = text
        return bild, ()
