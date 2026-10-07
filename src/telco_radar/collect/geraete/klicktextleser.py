"""Erste Lesung im Browser: Text der Preiszusammenfassung, Dialog und Textmuster.

``Textleser`` liest Text oder Attribut eines Bereichs in Takten von
``klicktor.WARTE_TAKT_MS`` (der Crawl-delay zählt nicht gegen die Frist). Der Text der
Zusammenfassung ist der Text des ersten Bereichs der Karte, dazu der der weiteren, ohne
den Text der Ausschlüsse (Telekom: Tarif- und Zahlungsblock, nicht die Vorteile).
Steht er in einem Dialog, öffnet ``oeffne_dialog`` ihn vor der Lesung und
``schliesse_dialog`` schließt ihn danach (Telekom „Preisübersicht anzeigen“); bleibt er
offen, ist der Lauf gestört. ``textwerte`` liest die Werte mit
``klicktext.lies_zusammenfassung`` und ersetzt jedes Feld mit Textmuster der Karte
durch die erste Gruppe des Musters ohne Leerraum, im Text der Zusammenfassung oder
am eigenen Fundort (o2 „Gerät mtl. (36 Raten)“, 1&1 „44 , 99 €/Monat“, Vodafone
Ratenzahl im gewählten Label). Dieses Modul ruft kein Netz außer über die Seite.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from typing import TYPE_CHECKING, Any

from playwright.sync_api import Error as PlaywrightFehler
from playwright.sync_api import TimeoutError as PlaywrightZeitueberschreitung

from .klickecho import feldwert
from .klicklauf import LAUF_GESTOERT
from .klicktext import Preiswerte, lies_zusammenfassung
from .klicktor import WARTE_TAKT_MS, kurz
from .klickwache import Abbruch

if TYPE_CHECKING:
    from playwright.sync_api import Locator, Page

    from .klickkarte import Klickkarte


class Textleser:
    """Liest Text, Dialog und Textmuster einer Seite nach Karte."""

    def __init__(self, seite: Page, karte: Klickkarte, frist_ms: int) -> None:
        self.seite, self.karte, self.frist_ms = seite, karte, frist_ms

    def text(
        self, bereich: Locator, gesucht: str = "", attribut: str | None = None
    ) -> str:
        """Sichtbarer Text des ersten Treffers, sobald er ``gesucht`` enthält.

        Mit ``attribut`` der Wert dieses Attributs statt des Texts. Wartet in Takten von
        ``WARTE_TAKT_MS``: Zeit, in der das Tor den Crawl-delay abwartet, zählt nicht
        gegen die Frist. Leer, wenn kein Text erscheint.
        """
        for _ in range(max(1, self.frist_ms // WARTE_TAKT_MS)):
            jetzt = self._text(bereich, attribut)
            if jetzt and gesucht in jetzt:
                return jetzt
            self.seite.wait_for_timeout(WARTE_TAKT_MS)
        return self._text(bereich, attribut)

    def zusammenfassung(self, bereich: Locator) -> str:
        """Text der Bereiche ohne Ausschlüsse; leer, wenn der erste Bereich fehlt."""
        text = self.text(bereich)
        if not text:
            return ""
        lesung = self.karte.textlesung
        weitere = [self._text(self.seite.locator(s)) for s in lesung.selektoren[1:]]
        text = "\n".join(t for t in (text, *weitere) if t)
        for ohne in lesung.ohne:
            for weg in self._alle_texte(ohne):
                text = text.replace(weg, "")
        return text

    def textwerte(self, text: str) -> tuple[Preiswerte, dict[str, tuple[str, str]]]:
        """Werte des Texts; je Feld mit Textmuster dessen Fundort und Ausschnitt."""
        werte = lies_zusammenfassung(text)
        gemustert: dict[str, Any] = {}
        fundorte: dict[str, tuple[str, str]] = {}
        for feld, muster in self.karte.textlesung.muster.items():
            ort = self.karte.zusammenfassung
            quelle = text
            if muster.selektor is not None:
                ort, quelle = (
                    muster.selektor,
                    self._text(self.seite.locator(muster.selektor)),
                )
            treffer = muster.muster.search(quelle)
            roh = None
            if treffer is not None:
                roh = treffer[1] if muster.muster.groups else treffer[0]
            gemustert[feld] = (
                None if roh is None else feldwert(feld, "".join(roh.split()))
            )
            if gemustert[feld] is not None and treffer is not None:
                fundorte[feld] = (ort, treffer[0])
        return replace(werte, **gemustert), fundorte

    def oeffne_dialog(self, bereich: Locator) -> str | None:
        """Öffnet den Dialog der Zusammenfassung; der Grund, wenn er nicht aufgeht."""
        oeffnen = self.karte.textlesung.oeffnen
        if oeffnen is None or sichtbar(bereich):
            return None
        try:
            self.seite.locator(oeffnen).first.click(timeout=self.frist_ms)
        except PlaywrightFehler as fehler:
            return f"Dialog {oeffnen} nicht klickbar: {kurz(fehler)}"
        if self._warte_bis(lambda: sichtbar(bereich)):
            return None
        return f"Dialog {oeffnen} zeigt {self.karte.zusammenfassung} nicht"

    def schliesse_dialog(self, bereich: Locator) -> None:
        """Schließt den Dialog; bleibt er offen, ist der Lauf gestört."""
        schliessen = self.karte.textlesung.schliessen
        if schliessen is None or not sichtbar(bereich):
            return
        try:
            self.seite.locator(schliessen).first.click(timeout=self.frist_ms)
        except PlaywrightFehler as fehler:
            grund = f"Dialog: {schliessen} nicht klickbar: {kurz(fehler)}"
            raise Abbruch(LAUF_GESTOERT, grund) from fehler
        if not self._warte_bis(lambda: not sichtbar(bereich)):
            grund = f"Dialog: {schliessen} schließt {self.karte.zusammenfassung} nicht"
            raise Abbruch(LAUF_GESTOERT, grund)

    def _text(self, bereich: Locator, attribut: str | None = None) -> str:
        if bereich.count() == 0:
            return ""
        try:
            if attribut is None:
                return bereich.first.inner_text(timeout=WARTE_TAKT_MS)
            wert = bereich.first.get_attribute(attribut, timeout=WARTE_TAKT_MS)
        except PlaywrightZeitueberschreitung:
            return ""
        return "" if wert is None else wert

    def _alle_texte(self, selektor: str) -> list[str]:
        try:
            texte = self.seite.locator(selektor).all_inner_texts()
        except PlaywrightFehler:
            return []
        return [t for t in texte if t.strip()]

    def _warte_bis(self, bedingung: Callable[[], bool]) -> bool:
        for _ in range(max(1, self.frist_ms // WARTE_TAKT_MS)):
            if bedingung():
                return True
            self.seite.wait_for_timeout(WARTE_TAKT_MS)
        return bedingung()


def sichtbar(bereich: Locator) -> bool:
    """Wahr, wenn der Bereich da und sichtbar ist."""
    return bereich.count() > 0 and bereich.is_visible()
