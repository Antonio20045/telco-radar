"""Bedienung neben den Knöpfen: Kanarienwert und Vorbereitung vor jeder Lesung.

Der Klick-Crawler (``klickcrawler``) prüft nach dem Öffnen den Kanarienwert der Karte:
Text oder Attribut am ersten Treffer, ``{modell}`` steht für den Modellnamen aus dem
Katalog. Fehlt er oder der Modellname, ist der Abruf gestört. Vor jeder Lesung stellt
``bereite_vor`` die Zustände der Karte her (``klickkarte.Vorbereitung``): passt das
geprüfte Element nicht auf ``bis``, klickt sie ``klick`` und wartet in Takten der Wache
darauf; fehlt das Element, lässt es sich nicht klicken oder kommt der Zustand nicht, ist
der Lauf gestört (kein Wert aus einem falschen Zustand). Lädt der Klick eine
Preisantwort, gehört sie zu ihm wie zu einem Knopf.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from playwright.sync_api import Error as PlaywrightFehler

from .klickkarte import PLATZHALTER_MODELL, Kanarie, Klickkarte, Vorbereitung
from .klicklauf import LAUF_GESTOERT
from .klicktor import kurz
from .klickwache import Abbruch, Wache

if TYPE_CHECKING:
    from playwright.sync_api import Locator, Page

    from .klicklesung import Leser

PLATZHALTER = "{" + PLATZHALTER_MODELL + "}"
_PASST_JS = "(element, css) => element.matches(css)"


def kanarientext(kanarie: Kanarie, modell: str | None) -> str:
    """Der erwartete Kanarienwert; ohne Modellname bei ``{modell}`` gestört."""
    if PLATZHALTER not in kanarie.enthaelt:
        return kanarie.enthaelt
    if modell is None or not modell.strip():
        grund = f"Kanarienwert braucht den Modellnamen des Geräts ({PLATZHALTER})"
        raise Abbruch(LAUF_GESTOERT, grund)
    return kanarie.enthaelt.replace(PLATZHALTER, modell.strip())


class Bedienung:
    """Kanarie und Vorbereitung eines Laufs auf einer Seite."""

    def __init__(
        self,
        seite: Page,
        karte: Klickkarte,
        wache: Wache,
        leser: Leser,
        modell: str | None,
    ) -> None:
        self.seite, self.karte, self.wache, self.leser = seite, karte, wache, leser
        self.modell = modell

    def pruefe_kanarie(self) -> None:
        """Bricht ab, wenn der Kanarienwert nicht an seiner Stelle steht."""
        kanarie = self.karte.kanarie
        erwartet = kanarientext(kanarie, self.modell)
        ort = self.seite.locator(kanarie.selektor)
        if erwartet not in self.leser.text(ort, erwartet, kanarie.attribut):
            self.wache.pruefe_tor()
            stelle = kanarie.selektor
            if kanarie.attribut is not None:
                stelle = f"{stelle} [{kanarie.attribut}]"
            grund = f"Kanarienwert fehlt: {stelle} ohne „{erwartet}“"
            raise Abbruch(LAUF_GESTOERT, grund)

    def bereite_vor(self) -> bool:
        """Stellt jeden Zustand der Karte her; wahr, wenn dafür geklickt wurde."""
        geklickt = False
        for schritt in self.karte.vorbereitung:
            if self._erfuellt(schritt):
                continue
            self._klicke(schritt)
            geklickt = True
        return geklickt

    def _erfuellt(self, schritt: Vorbereitung) -> bool:
        selektor = schritt.klick if schritt.pruefe is None else schritt.pruefe
        ort = self.seite.locator(selektor)
        if not self.wache.warte(lambda: ort.count() > 0):
            raise Abbruch(LAUF_GESTOERT, f"Vorbereitung: {selektor} nicht gefunden")
        return _passt(ort.first, schritt.bis)

    def _klicke(self, schritt: Vorbereitung) -> None:
        self.wache.warte_offen()
        marke = self.wache.marke()
        try:
            self.seite.locator(schritt.klick).first.click(timeout=self.wache.frist_ms)
        except PlaywrightFehler as fehler:
            grund = f"Vorbereitung: {schritt.klick} nicht klickbar: {kurz(fehler)}"
            raise Abbruch(LAUF_GESTOERT, grund) from fehler
        if not self.wache.warte(lambda: self._erfuellt(schritt)):
            grund = f"Vorbereitung: {schritt.klick} erreicht „{schritt.bis}“ nicht"
            raise Abbruch(LAUF_GESTOERT, grund)
        self.wache.nimm_angefragte(marke)


def _passt(element: Locator, css: str) -> bool:
    return element.evaluate(_PASST_JS, css) is True
