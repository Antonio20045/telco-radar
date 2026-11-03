"""Bedienung neben den Knöpfen: Kanarienwert, Einwilligung und Vorbereitung.

Der Klick-Crawler (``klickcrawler``) prüft nach dem Öffnen den Kanarienwert der Karte:
Text oder Attribut am ersten Treffer, ``{modell}`` steht für den Modellnamen aus dem
Katalog. Fehlt er oder der Modellname, ist der Abruf gestört. Dann lehnt
``lehne_einwilligung_ab`` eine sichtbare Einwilligungsabfrage ab wie die Erkundung
(``klickproben.einwilligungsknopf``); hinter ihr nimmt die Seite keinen Klick an (1&1,
Erkundung 07.10.2026). Ein anderer Knopf der Abfrage wird nie geklickt; lässt sich der
Ablehnen-Knopf nicht klicken, ist der Lauf gestört. Vor jeder Lesung stellt
``bereite_vor`` die Zustände der Karte her (``klickkarte.Vorbereitung``): passt das
geprüfte Element nicht auf ``bis``, klickt sie ``klick`` und wartet in Takten der Wache
darauf; fehlt das Element, lässt es sich nicht klicken oder kommt der Zustand nicht, ist
der Lauf gestört (kein Wert aus einem falschen Zustand). Beides nach bestandener
Bot-Prüfung heißt ``STOERUNG_SEITE``: diese eine Seite hat eine andere Form, der
Tageslauf liest die nächste (``klicktageslauf``). Lädt der Klick eine
Preisantwort, gehört sie zu ihm wie zu einem Knopf. Leitet der Anbieter die
Produktseite auf eine Übersicht um, bietet er das Gerät nicht mehr an: die Seite ist
``leer``, keine andere Form (congstar 27.10.2026, drei ausgelistete Geräte in Folge
hielten den ganzen Tageslauf an: ``AUSGELISTET``; Telekom 02.11.2026 ebenso, alle zwölf
Detailläufe gestört). Die Telekom-Regel steht in der Karte (``kanarie.ausgelistet_url``,
``ist_ausgelistet``): Endadresse anders als die angeforderte, Host genau der des Musters
und Pfad (nicht Query) ganz im Muster. Beides gilt nur, wenn der Kanarienwert fehlt.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from urllib.parse import urlsplit

from playwright.sync_api import Error as PlaywrightFehler

from .klickergebnis import LAUF_LEER
from .klickkarte import PLATZHALTER_MODELL, Kanarie, Klickkarte, Vorbereitung
from .klicklauf import LAUF_GESTOERT, STOERUNG_SEITE
from .klickproben import einwilligungsknopf
from .klicktor import kurz
from .klickwache import Abbruch, Wache

if TYPE_CHECKING:
    from playwright.sync_api import Locator, Page

    from .klicklesung import Leser

PLATZHALTER = "{" + PLATZHALTER_MODELL + "}"
_PASST_JS = "(element, css) => element.matches(css)"
AUSGELISTET = ("redirectFrom=device-details",)
GRUND_AUSGELISTET = "Gerät nicht mehr angeboten, Umleitung auf"


def ist_ausgelistet(kanarie: Kanarie, angefordert: str, endadresse: str) -> bool:
    """Wahr, wenn die Endadresse die Übersicht für ausgelistete Geräte der Karte ist.

    Nur mit ``kanarie.ausgelistet_url``, nur nach einer Umleitung (anderer Host oder
    Pfad als angefordert), beim genauen Host und mit dem Pfad ganz im Muster; die Query
    zählt nicht (eine Login- oder Fehlerseite trägt den Rückweg oft darin).
    """
    regel = kanarie.ausgelistet_url
    if regel is None:
        return False
    ende, anfang = urlsplit(endadresse), urlsplit(angefordert)
    if (ende.hostname, ende.path.rstrip("/")) == (
        anfang.hostname,
        anfang.path.rstrip("/"),
    ):
        return False
    return ende.hostname == regel.host and regel.pfad.fullmatch(ende.path) is not None


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
            ende = self.seite.url
            if any(m in ende for m in AUSGELISTET) or ist_ausgelistet(
                kanarie, self.wache.lauf.adresse, ende
            ):
                raise Abbruch(LAUF_LEER, f"{GRUND_AUSGELISTET} {ende}")
            stelle = kanarie.selektor
            if kanarie.attribut is not None:
                stelle = f"{stelle} [{kanarie.attribut}]"
            grund = f"Kanarienwert fehlt: {stelle} ohne „{erwartet}“"
            raise self._seitenform(grund)

    def lehne_einwilligung_ab(self) -> None:
        """Lehnt eine sichtbare Einwilligungsabfrage ab (``lehne_einwilligung_ab``)."""
        lehne_einwilligung_ab(self.seite, self.wache)

    def bereite_vor(self) -> bool:
        """Stellt jeden Zustand der Karte her; wahr, wenn dafür geklickt wurde."""
        geklickt = False
        for schritt in self.karte.vorbereitung:
            if self._fehlt_erlaubt(schritt) or self._erfuellt(schritt):
                continue
            self._klicke(schritt)
            geklickt = True
        return geklickt

    def _fehlt_erlaubt(self, schritt: Vorbereitung) -> bool:
        selektor = schritt.klick if schritt.pruefe is None else schritt.pruefe
        if not schritt.darf_fehlen:
            return False
        return not self.wache.warte(lambda: self.seite.locator(selektor).count() > 0)

    def _erfuellt(self, schritt: Vorbereitung) -> bool:
        selektor = schritt.klick if schritt.pruefe is None else schritt.pruefe
        ort = self.seite.locator(selektor)
        if not self.wache.warte(lambda: ort.count() > 0):
            raise self._seitenform(f"Vorbereitung: {selektor} nicht gefunden")
        return _passt(ort.first, schritt.bis)

    def _klicke(self, schritt: Vorbereitung) -> None:
        self.wache.warte_offen()
        marke = self.wache.marke()
        try:
            self.seite.locator(schritt.klick).first.click(timeout=self.wache.frist_ms)
        except PlaywrightFehler as fehler:
            grund = f"Vorbereitung: {schritt.klick} nicht klickbar: {kurz(fehler)}"
            raise self._seitenform(grund) from fehler
        if not self.wache.warte(lambda: self._erfuellt(schritt)):
            grund = f"Vorbereitung: {schritt.klick} erreicht „{schritt.bis}“ nicht"
            raise self._seitenform(grund)
        self.wache.nimm_angefragte(marke)

    def _seitenform(self, grund: str) -> Abbruch:
        """Abbruch einer Seite anderer Form; Bot-Schutz im Tor geht vor."""
        self.wache.pruefe_tor()
        self.wache.lauf.stoerung = STOERUNG_SEITE
        return Abbruch(LAUF_GESTOERT, grund)


def lehne_einwilligung_ab(seite: Page, wache: Wache) -> str | None:
    """Klickt den sichtbaren Ablehnen-Knopf einer Einwilligungsabfrage und wartet
    auf Ruhe; ohne ihn nichts. Der Text des geklickten Knopfs, sonst ``None``."""
    knopf = einwilligungsknopf(seite)
    if knopf is None:
        return None
    text = knopf.inner_text().strip()
    wache.warte_offen()
    marke = wache.marke()
    try:
        knopf.click(timeout=wache.frist_ms)
    except PlaywrightFehler as fehler:
        grund = f"Einwilligung nicht abgelehnt: {kurz(fehler)}"
        raise Abbruch(LAUF_GESTOERT, grund) from fehler
    wache.nimm_angefragte(marke)
    wache.warte_ruhe()
    return text


def _passt(element: Locator, css: str) -> bool:
    return element.evaluate(_PASST_JS, css) is True
