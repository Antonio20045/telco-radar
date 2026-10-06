"""Lesung nach einem Klick: Antwort, Text, markierte Optionen und Screenshot.

Der Klick-Crawler (``klickcrawler``) ruft ``Leser.lies``, sobald die Antwort zum Klick
da ist. Der Leser liest erst die mitgeschnittene Antwort, dann nach zwei Bildern den
Text der Preiszusammenfassung (in Takten, der Crawl-delay zählt nicht gegen die Frist),
prüft die roh markierten Optionen gegen die geklickten und das Echo (``klickecho``) und
macht einen Screenshot des Preisbereichs; den gelesenen Text gibt er für die Fundstellen
des Belegs mit. Fehlt die Zusammenfassung, heißt die Kombination ``nicht_erfasst``;
widerspricht sich etwas, ``befund``. Gefundene Wertfelder zählt der Strukturwächter.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from playwright.sync_api import Error as PlaywrightFehler
from playwright.sync_api import TimeoutError as PlaywrightZeitueberschreitung

from .klickecho import (
    KEINE_AUSWAHL,
    Antwortlesung,
    Befund,
    Echo,
    Variante,
    lies_antwort,
    pruefe_echo,
)
from .klickkarte import DIMENSIONEN, WERTFELDER, Klickkarte
from .klicklauf import BEFUND, ERFASST, NICHT_ERFASST, Kombiergebnis, Strukturbilanz
from .klickoptionen import Option, lies_optionen
from .klicktext import Preiswerte, lies_zusammenfassung
from .klicktor import WARTE_TAKT_MS, kurz

if TYPE_CHECKING:
    from playwright.sync_api import Locator, Page, Response

_ZWEI_BILDER_JS = (
    "() => new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r)))"
)


class Leser:
    """Liest Optionen, Text und die Kombination auf einer Seite nach Karte."""

    def __init__(self, seite: Page, karte: Klickkarte, frist_ms: int) -> None:
        self.seite, self.karte, self.frist_ms = seite, karte, frist_ms

    def optionen(self, dimension: str) -> list[Option]:
        """Die Knöpfe einer Dimension im aktuellen Zustand der Seite."""
        return lies_optionen(self.seite, self.karte, dimension)

    def text(self, bereich: Locator, gesucht: str = "") -> str:
        """Sichtbarer Text des ersten Treffers, sobald er ``gesucht`` enthält.

        Wartet in Takten von ``WARTE_TAKT_MS``: Zeit, in der das Tor den Crawl-delay
        abwartet, zählt nicht gegen die Frist. Leer, wenn kein Text erscheint.
        """
        for _ in range(max(1, self.frist_ms // WARTE_TAKT_MS)):
            jetzt = self._text(bereich)
            if jetzt and gesucht in jetzt:
                return jetzt
            self.seite.wait_for_timeout(WARTE_TAKT_MS)
        return self._text(bereich)

    def _text(self, bereich: Locator) -> str:
        if bereich.count() == 0:
            return ""
        try:
            return bereich.first.inner_text(timeout=WARTE_TAKT_MS)
        except PlaywrightZeitueberschreitung:
            return ""

    def lies(
        self,
        variante: Variante,
        ziel: dict[str, str | None],
        antwort: Response | None,
        struktur: Strukturbilanz,
    ) -> Kombiergebnis:
        """Liest Antwort, dann Text: der Antwortkörper ist da, bevor die Seite malt."""
        bereich = self.seite.locator(self.karte.zusammenfassung).first
        lesung, unlesbar = self._lies_antwort(antwort)
        url = antwort.url if antwort is not None else None
        self.seite.evaluate(_ZWEI_BILDER_JS)
        text = self.text(bereich)
        if not text:
            struktur.felder(0)
            ort = self.karte.zusammenfassung
            grund = f"Preiszusammenfassung nicht gefunden ({ort})"
            return Kombiergebnis(variante, NICHT_ERFASST, grund, antwort_url=url)
        im_text = lies_zusammenfassung(text)
        struktur.felder(sum(getattr(im_text, f) is not None for f in WERTFELDER))
        if unlesbar is not None:
            befunde: tuple[Befund, ...] = (unlesbar,)
            return Kombiergebnis(variante, BEFUND, unlesbar.grund, befunde=befunde)
        abweichung = self._abweichung(ziel)
        echo = (
            Echo(Preiswerte(), abweichung, ())
            if abweichung
            else pruefe_echo(variante, variante, im_text, lesung)
        )
        bild, bildbefunde = self._screenshot(bereich)
        befunde = echo.befunde + bildbefunde
        erster: str | None = befunde[0].grund if befunde else None
        status = BEFUND if befunde else ERFASST
        return Kombiergebnis(
            variante,
            status,
            erster,
            echo.werte,
            befunde,
            echo.luecken,
            bild,
            url,
            text=text,
        )

    def _abweichung(self, ziel: dict[str, str | None]) -> tuple[Befund, ...]:
        """Befunde, wo die Seite eine andere Option markiert als die geklickte."""
        befunde = []
        for dimension in DIMENSIONEN:
            gezeigt = self._gewaehlt(dimension)
            if gezeigt != ziel[dimension]:
                zeige = KEINE_AUSWAHL if gezeigt is None else gezeigt
                grund = f"Seite zeigt {zeige} statt {ziel[dimension]}"
                befunde.append(Befund(f"variante.{dimension}", grund))
        return tuple(befunde)

    def _gewaehlt(self, dimension: str) -> str | None:
        gewaehlt = [o.wert for o in self.optionen(dimension) if o.gewaehlt]
        return gewaehlt[0] if len(gewaehlt) == 1 else None

    def _lies_antwort(
        self, antwort: Response | None
    ) -> tuple[Antwortlesung | None, Befund | None]:
        if antwort is None:
            return None, None
        try:
            nutzlast = antwort.json()
        except (PlaywrightFehler, ValueError) as fehler:
            return None, Befund("antwort", f"Antwort nicht lesbar: {kurz(fehler)}")
        return lies_antwort(nutzlast, self.karte.antwort, antwort.url), None

    def _screenshot(self, bereich: Locator) -> tuple[bytes | None, tuple[Befund, ...]]:
        try:
            return bereich.screenshot(type="png", timeout=self.frist_ms), ()
        except PlaywrightFehler as fehler:
            return None, (Befund("screenshot", f"Screenshot fehlt: {kurz(fehler)}"),)
