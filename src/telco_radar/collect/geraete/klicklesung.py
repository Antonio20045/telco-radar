"""Lesung nach einem Klick: Quellen, Text, markierte Optionen und Screenshot.

Der Klick-Crawler (``klickcrawler``) ruft ``Leser.lies``, sobald die Antwort zum Klick
da ist oder die Seite ruht. Der Leser liest erst die Seitenwerte und die Quellen der
zweiten Lesung (``klickquellen``; ihre Platzhalter sind die geklickten Werte, die
Seitenwerte und der Modellname), dann nach zwei Bildern den Text der
Preiszusammenfassung (``klicktextleser``, bei Bedarf in einem Dialog), prüft die roh
markierten Optionen gegen die geklickten, die Seitenwerte mit dem Namen einer Dimension
als „Seite zeigt“ und das Echo (``klickecho``) und macht einen Screenshot des
Preisbereichs. Was der Beleg braucht (Mitschnitt, JSON-Pfade, Fundorte der
Textmuster), legt er in ``belegteile``. Fehlt die Zusammenfassung, heißt die
Kombination ``nicht_erfasst``; widerspricht sich etwas, ``befund``. Eine feste
Dimension hat keine Markierung. Gefundene Wertfelder zählt der Strukturwächter.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from playwright.sync_api import Error as PlaywrightFehler

from .klickecho import KEINE_AUSWAHL, Befund, Echo, Variante, pruefe_echo, variante_aus
from .klickhar import Antwortkopie
from .klickkarte import DIMENSIONEN, PLATZHALTER_MODELL, WERTFELDER, Klickkarte
from .klicklauf import BEFUND, ERFASST, NICHT_ERFASST, Kombiergebnis, Strukturbilanz
from .klickoptionen import Option, lies_optionen
from .klickquellen import Quellenleser
from .klicktext import Preiswerte
from .klicktextleser import Textleser
from .klicktor import kurz

if TYPE_CHECKING:
    from playwright.sync_api import Locator, Page

    from .klickwache import Wache

_ZWEI_BILDER_JS = (
    "() => new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r)))"
)


@dataclass(frozen=True)
class Belegteile:
    """Was der Beleg einer Lesung braucht außer Werten, Text und Bild."""

    kopie: Antwortkopie | None = None
    json_pfade: Mapping[str, str] = field(default_factory=dict)
    fundorte: Mapping[str, tuple[str, str]] = field(default_factory=dict)


class Leser(Textleser):
    """Liest Optionen, Quellen, Text und die Kombination auf einer Seite nach Karte."""

    def __init__(
        self,
        seite: Page,
        karte: Klickkarte,
        frist_ms: int,
        wache: Wache,
        modell: str | None = None,
    ) -> None:
        super().__init__(seite, karte, frist_ms)
        self.wache, self.modell = wache, modell
        self.quellen = Quellenleser(seite, karte, wache.mitschnitt)
        self.belegteile = Belegteile()

    def optionen(self, dimension: str) -> list[Option]:
        """Die Knöpfe einer Dimension im aktuellen Zustand der Seite."""
        return lies_optionen(self.seite, self.karte, dimension)

    def lies(
        self,
        variante: Variante,
        ziel: dict[str, str | None],
        struktur: Strukturbilanz,
        unberuehrt: bool = False,
    ) -> Kombiergebnis:
        """Liest Quellen, dann Text: der Antwortkörper ist da, bevor die Seite malt.

        ``unberuehrt`` heißt: seit dem Laden wurde nichts geklickt (``start``-Quellen).
        """
        bereich = self.seite.locator(self.karte.textlesung.selektoren[0]).first
        seitenwerte = self.quellen.seitenwerte()
        platz = {**seitenwerte, **ziel, PLATZHALTER_MODELL: self.modell}
        zweite = self.quellen.lies(self.wache.seit, unberuehrt, platz)
        self.belegteile = Belegteile(zweite.kopie, zweite.json_pfade)
        url = None if zweite.kopie is None else zweite.kopie.url
        in_antwort = zweite.lesung.werte if zweite.lesung is not None else None
        self.seite.evaluate(_ZWEI_BILDER_JS)
        dialog = self.oeffne_dialog(bereich)
        text = self.zusammenfassung(bereich) if dialog is None else ""
        if not text:
            self.schliesse_dialog(bereich)
            struktur.felder(0)
            grund = (
                f"Preiszusammenfassung nicht gefunden ({self.karte.zusammenfassung})"
            )
            if dialog is not None:
                grund = dialog
            return Kombiergebnis(
                variante, NICHT_ERFASST, grund, antwort_url=url, antwortwerte=in_antwort
            )
        im_text, fundorte = self.textwerte(text)
        self.belegteile = Belegteile(zweite.kopie, zweite.json_pfade, fundorte)
        struktur.felder(sum(getattr(im_text, f) is not None for f in WERTFELDER))
        if zweite.befund is not None:
            befunde: tuple[Befund, ...] = (zweite.befund,)
            grund = zweite.befund.grund
            return Kombiergebnis(
                variante, BEFUND, grund, befunde=befunde, textwerte=im_text
            )
        abweichung = self._abweichung(ziel)
        angezeigt = self._angezeigt(variante, seitenwerte)
        echo = (
            Echo(Preiswerte(), abweichung, ())
            if abweichung
            else pruefe_echo(variante, angezeigt, im_text, zweite.lesung)
        )
        bild, bildbefunde = self._screenshot(bereich)
        self.schliesse_dialog(bereich)
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
            textwerte=im_text,
            antwortwerte=in_antwort,
        )

    def _angezeigt(
        self, variante: Variante, seitenwerte: Mapping[str, str | None]
    ) -> Variante:
        """Die Variante, die die Seite zeigt: Seitenwerte mit dem Namen einer
        Dimension, sonst die geklickte."""
        gezeigt = [
            seitenwerte[d] if d in self.karte.seite else getattr(variante, d)
            for d in DIMENSIONEN
        ]
        return variante_aus(*gezeigt)

    def _abweichung(self, ziel: dict[str, str | None]) -> tuple[Befund, ...]:
        """Befunde, wo die Seite eine andere Option markiert als die geklickte."""
        befunde = []
        for dimension in DIMENSIONEN:
            if self.karte.knoepfe[dimension].fest is not None:
                continue
            gezeigt = self._gewaehlt(dimension)
            if gezeigt != ziel[dimension]:
                zeige = KEINE_AUSWAHL if gezeigt is None else gezeigt
                grund = f"Seite zeigt {zeige} statt {ziel[dimension]}"
                befunde.append(Befund(f"variante.{dimension}", grund))
        return tuple(befunde)

    def _gewaehlt(self, dimension: str) -> str | None:
        gewaehlt = [o.wert for o in self.optionen(dimension) if o.gewaehlt]
        return gewaehlt[0] if len(gewaehlt) == 1 else None

    def _screenshot(self, bereich: Locator) -> tuple[bytes | None, tuple[Befund, ...]]:
        try:
            return bereich.screenshot(type="png", timeout=self.frist_ms), ()
        except PlaywrightFehler as fehler:
            return None, (Befund("screenshot", f"Screenshot fehlt: {kurz(fehler)}"),)
