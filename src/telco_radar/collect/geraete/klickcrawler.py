"""Klick-Crawler: klickt jede angebotene Variante einer Produktseite, liest zweifach.

Gerüst aus Schritt 4 des Datenkonzepts Geräteradar (Abschnitt 8); noch ruft es kein
Tageslauf. Je Produktseite und Klick-Karte (``klickkarte``):

1. Der Crawler legt einen eigenen Browserkontext ohne Service Worker an. Jede Anfrage
   geht durch das Tor (``klicktor``): robots.txt für jede Adresse und jedes Ziel einer
   Umleitung, Crawl-delay je Host für Seiten, XHR und Fetch. Gesperrte Adressen gehen
   nicht hinaus und stehen in ``verworfen``. Nach dem Lauf verlässt er die Seite und
   schließt den Kontext; die Seite lädt danach nichts mehr.
2. Antwortet die Seite mit 202 (Challenge), 4xx oder 5xx oder fehlt der Kanarienwert,
   ist der Abruf gestört: kein zweiter Versuch, keine Umgehung (CLAUDE.md Regel 4).
   Sperrt robots.txt die Seite oder ihre Preisantwort, ist der Lauf gesperrt.
3. Er liest die angebotenen Optionen je Dimension und klickt jede Kombination; nach
   jedem Klick liest er die Optionen neu und führt neu erschienene Werte mit. Eine
   Antwort gehört nur zu dem Klick, nach dem ihre Anfrage hinausging; bleibt eine
   Anfrage über die Frist offen, wartet er sie vor dem nächsten Klick ab oder bricht
   den Lauf als gestört ab. Dann liest er die Preiszusammenfassung, prüft die roh
   markierten Optionen und das Echo (``klickecho``) und macht einen Screenshot.
4. Je Kombination: erfasst, nicht_angeboten, nicht_erfasst oder befund; dazu der
   Strukturwächter je Lauf (beides in ``klicklauf``).

Den Browser startet der Aufrufer; dieses Modul setzt keine Tarnung, keinen Proxy und
keine fremde Kennung.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import replace
from datetime import datetime
from typing import TYPE_CHECKING

from playwright.sync_api import Error as PlaywrightFehler
from playwright.sync_api import TimeoutError as PlaywrightZeitueberschreitung

from .klickecho import (
    KEINE_AUSWAHL,
    LAUFZEIT,
    Antwortlesung,
    Befund,
    Echo,
    Variante,
    lies_antwort,
    pruefe_echo,
    variante_aus,
)
from .klickkarte import DIMENSIONEN, WERTFELDER, Klickkarte
from .klicklauf import (
    BEFUND,
    ERFASST,
    LAUF_GELESEN,
    LAUF_GESPERRT,
    LAUF_GESTOERT,
    NICHT_ANGEBOTEN,
    NICHT_ERFASST,
    Klicklauf,
    Kombiergebnis,
    abruf_gestoert,
    strukturgrund,
)
from .klickoptionen import (
    Auswahl,
    Option,
    angebotene_werte,
    lies_optionen,
    naechste,
    vereinige,
)
from .klicktext import Preiswerte, lies_zusammenfassung
from .klicktor import (
    GRUND_ZU_VIELE,
    HOECHSTE_UMLEITUNGEN,
    SEITEN_FRIST_MS,
    Mitschnitt,
    Schleuse,
    Tor,
    kurz,
    schliesse,
    sperre_beiwege,
)
from .robots import RobotsWaechter

if TYPE_CHECKING:
    from playwright.sync_api import (
        Browser,
        BrowserContext,
        Locator,
        Page,
        Response,
        ViewportSize,
    )


log = logging.getLogger(__name__)

ANTWORT_FRIST_MS = 15000
WARTE_TAKT_MS = 50
HOECHSTE_KOMBINATIONEN = 200
FENSTER: ViewportSize = {"width": 1280, "height": 900}
_ZWEI_BILDER_JS = (
    "() => new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r)))"
)


def klicke_durch(
    browser: Browser,
    adresse: str,
    karte: Klickkarte,
    waechter: RobotsWaechter,
    uhr: Callable[[], datetime],
    *,
    schleuse: Schleuse,
    vorlauf: Klicklauf | None = None,
    frist_ms: int = ANTWORT_FRIST_MS,
) -> Klicklauf:
    """Klickt alle angebotenen Kombinationen auf ``adresse``; wirft nie.

    ``uhr`` liefert die Zeit des nächsten Abrufs für robots.txt; ``schleuse`` hält den
    Crawl-delay je Host über Läufe hinweg (``klicktor.Hostschleuse``, eine je
    Anbieterlauf). ``vorlauf`` ist der letzte Lauf derselben Seite; er zählt nur, wenn
    er gelesen ist. Ein Abbruch steht als Status und Grund im Lauf, die Kombinationen
    bis dahin bleiben erhalten.
    """
    lauf = Klicklauf(anbieter=karte.anbieter, adresse=adresse)
    tor = Tor(waechter, uhr, schleuse, lauf.verworfen, frist_ms)
    kontext: BrowserContext | None = None
    seite: Page | None = None
    try:
        kontext = browser.new_context(service_workers="block", viewport=FENSTER)
        kontext.route("**/*", tor)
        seite = kontext.new_page()
        sperre_beiwege(kontext, seite)
        _Gang(seite, karte, tor, frist_ms, lauf).laufe()
    except _Abbruch as abbruch:
        lauf.status, lauf.grund = abbruch.status, abbruch.grund
    except PlaywrightFehler as fehler:
        lauf.status, lauf.grund = LAUF_GESTOERT, f"Browserfehler: {kurz(fehler)}"
    finally:
        schliesse(kontext, seite)
    bruch = strukturgrund(lauf.struktur, vorlauf)
    if lauf.status == LAUF_GELESEN and bruch is not None:
        lauf.status, lauf.grund = LAUF_GESTOERT, bruch
    if lauf.status != LAUF_GELESEN:
        log.warning("Klick-Crawler %s %s: %s", karte.anbieter, adresse, lauf.grund)
    return lauf


class _Abbruch(Exception):
    """Beendet einen Lauf mit Status und Grund."""

    def __init__(self, status: str, grund: str) -> None:
        super().__init__(grund)
        self.status = status
        self.grund = grund


class _Klickfehler(Exception):
    """Ein Knopf ließ sich nicht klicken."""


class _Gang:
    """Zustand eines Laufs: Seite, Karte, Tor, Mitschnitt und die aktuelle Antwort."""

    def __init__(
        self, seite: Page, karte: Klickkarte, tor: Tor, frist_ms: int, lauf: Klicklauf
    ) -> None:
        self.seite, self.karte, self.tor, self.lauf = seite, karte, tor, lauf
        self.frist_ms = frist_ms
        self.antwort: Response | None = None
        self.geklickt = False
        self.mitschnitt = Mitschnitt(karte.antwort.passt)
        seite.on("request", self.mitschnitt.anfrage)
        seite.on("response", self.mitschnitt.antwort)
        seite.on("requestfailed", self.mitschnitt.gescheitert)

    def laufe(self) -> None:
        self._oeffne()
        werte = {d: self._angebotene_werte(d) for d in DIMENSIONEN}
        besucht: set[Auswahl] = set()
        while (auswahl := naechste(werte, besucht)) is not None:
            besucht.add(auswahl)
            self.geklickt = False
            ergebnis = self._kombination(auswahl, len(besucht))
            self.lauf.ergebnisse.append(replace(ergebnis, auswahl=auswahl))
            if self.geklickt:
                for d in DIMENSIONEN:
                    werte[d] = vereinige(werte[d], self._angebotene_werte(d))

    def _oeffne(self) -> None:
        ziel, haupt = self.lauf.adresse, None
        for _ in range(HOECHSTE_UMLEITUNGEN + 1):
            darf, grund = self.tor.darf(ziel)
            if not darf:
                raise _Abbruch(LAUF_GESPERRT, grund)
            haupt = self._lade(ziel)
            if self.tor.umleitung is None:
                break
            ziel = self.tor.umleitung
        else:
            raise _Abbruch(LAUF_GESTOERT, f"Abruf gestört ({GRUND_ZU_VIELE})")
        self.lauf.http_status = haupt.status if haupt is not None else None
        stoerung = abruf_gestoert(self.lauf.http_status)
        if stoerung is not None:
            raise _Abbruch(LAUF_GESTOERT, stoerung)
        darf, grund = self.tor.darf(self.seite.url)
        if not darf:
            raise _Abbruch(LAUF_GESPERRT, grund)
        kanarie = self.karte.kanarie
        if kanarie.enthaelt not in self._text(self.seite.locator(kanarie.selektor)):
            grund = f"Kanarienwert fehlt: {kanarie.selektor} ohne „{kanarie.enthaelt}“"
            raise _Abbruch(LAUF_GESTOERT, grund)
        self._nimm_antwort(self._antwort_seit(0), 0)

    def _lade(self, ziel: str) -> Response | None:
        self.tor.umleitung = None
        seit = len(self.lauf.verworfen)
        try:
            return self.seite.goto(ziel, timeout=SEITEN_FRIST_MS)
        except PlaywrightFehler as fehler:
            if self.tor.umleitung is not None:
                return None
            gesperrt = self.lauf.verworfen[seit:]
            if gesperrt:
                raise _Abbruch(LAUF_GESPERRT, gesperrt[0].grund) from fehler
            raise

    def _warte(self, bedingung: Callable[[], bool]) -> bool:
        for _ in range(max(1, self.frist_ms // WARTE_TAKT_MS)):
            if bedingung():
                return True
            self.seite.wait_for_timeout(WARTE_TAKT_MS)
        return bedingung()

    def _antwort_seit(self, seit: int) -> Response | None:
        if not self._warte(lambda: self.mitschnitt.fertig_seit(seit)):
            return None
        return self.mitschnitt.letzte_seit(seit)

    def _nimm_antwort(self, antwort: Response | None, seit: int) -> None:
        if antwort is None:
            verworfen = self.lauf.verworfen[seit:]
            gesperrt = [v for v in verworfen if self.karte.antwort.passt(v.anfrage)]
            if gesperrt:
                raise _Abbruch(LAUF_GESPERRT, f"Preisantwort {gesperrt[0].grund}")
        else:
            stoerung = abruf_gestoert(antwort.status)
            if stoerung is not None:
                raise _Abbruch(LAUF_GESTOERT, f"Preisantwort: {stoerung}")
        self.antwort = antwort

    def _optionen(self, dimension: str) -> list[Option]:
        return lies_optionen(self.seite, self.karte, dimension)

    def _angebotene_werte(self, dimension: str) -> list[str | None]:
        optionen = self._optionen(dimension)
        self.lauf.struktur.knopf(bool(optionen))
        return angebotene_werte(optionen)

    def _kombination(self, auswahl: Auswahl, nummer: int) -> Kombiergebnis:
        ziel = dict(zip(DIMENSIONEN, auswahl, strict=True))
        variante = variante_aus(*auswahl)
        if nummer > HOECHSTE_KOMBINATIONEN:
            grund = f"nicht besucht: mehr als {HOECHSTE_KOMBINATIONEN} Kombinationen"
            return Kombiergebnis(variante, NICHT_ERFASST, grund)
        fehlend = [d for d in DIMENSIONEN if ziel[d] is None]
        if fehlend:
            self.lauf.struktur.knopf(False)
            return Kombiergebnis(variante, NICHT_ERFASST, self._fehlen(fehlend[0]))
        if variante.laufzeit is None:
            grund = f"Laufzeit „{ziel[LAUFZEIT]}“ nicht lesbar"
            return Kombiergebnis(variante, NICHT_ERFASST, grund)
        for dimension in DIMENSIONEN:
            ergebnis = self._waehle(dimension, str(ziel[dimension]), variante)
            if ergebnis is not None:
                return ergebnis
        return self._lies(variante, ziel)

    def _fehlen(self, dimension: str) -> str:
        selektor = self.karte.knoepfe[dimension].selektor
        return f"Knöpfe für {dimension} nicht gefunden ({selektor})"

    def _waehle(
        self, dimension: str, wert: str, variante: Variante
    ) -> Kombiergebnis | None:
        optionen = self._optionen(dimension)
        self.lauf.struktur.knopf(bool(optionen))
        if not optionen:
            return Kombiergebnis(variante, NICHT_ERFASST, self._fehlen(dimension))
        stelle = next((i for i, o in enumerate(optionen) if o.wert == wert), None)
        if stelle is None:
            grund = f"Seite zeigt {dimension} {wert} in diesem Zustand nicht"
            return Kombiergebnis(variante, NICHT_ERFASST, grund)
        if optionen[stelle].deaktiviert:
            grund = f"Seite bietet {dimension} {wert} nicht an"
            return Kombiergebnis(variante, NICHT_ANGEBOTEN, grund)
        if optionen[stelle].gewaehlt:
            return None
        return self._klicke(dimension, stelle, variante)

    def _klicke(
        self, dimension: str, stelle: int, variante: Variante
    ) -> Kombiergebnis | None:
        if not self._warte(lambda: not self.mitschnitt.offen):
            grund = f"Preisantwort nach {self.frist_ms} ms noch offen"
            raise _Abbruch(LAUF_GESTOERT, grund)
        seit, seit_verworfen = self.mitschnitt.stand(), len(self.lauf.verworfen)
        knopf = self.seite.locator(self.karte.knoepfe[dimension].selektor).nth(stelle)
        try:
            self._druecke(knopf)
        except _Klickfehler as fehler:
            grund = f"Knopf für {dimension} nicht klickbar: {fehler}"
            return Kombiergebnis(variante, NICHT_ERFASST, grund)
        self.geklickt = True
        self._nimm_antwort(self._antwort_seit(seit), seit_verworfen)
        return None

    def _druecke(self, knopf: Locator) -> None:
        try:
            knopf.click(timeout=self.frist_ms)
        except PlaywrightFehler as fehler:
            raise _Klickfehler(kurz(fehler)) from fehler

    def _lies(self, variante: Variante, ziel: dict[str, str | None]) -> Kombiergebnis:
        """Liest Antwort, dann Text: der Antwortkörper ist da, bevor die Seite malt."""
        bereich = self.seite.locator(self.karte.zusammenfassung).first
        lesung, unlesbar = self._lies_antwort()
        url = self.antwort.url if self.antwort is not None else None
        self.seite.evaluate(_ZWEI_BILDER_JS)
        text = self._text(bereich)
        if not text:
            self.lauf.struktur.felder(0)
            ort = self.karte.zusammenfassung
            grund = f"Preiszusammenfassung nicht gefunden ({ort})"
            return Kombiergebnis(variante, NICHT_ERFASST, grund, antwort_url=url)
        im_text = lies_zusammenfassung(text)
        gefunden = sum(getattr(im_text, f) is not None for f in WERTFELDER)
        self.lauf.struktur.felder(gefunden)
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
            variante, status, erster, echo.werte, befunde, echo.luecken, bild, url
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

    def _text(self, bereich: Locator) -> str:
        try:
            return bereich.first.inner_text(timeout=self.frist_ms)
        except PlaywrightZeitueberschreitung:
            return ""

    def _gewaehlt(self, dimension: str) -> str | None:
        gewaehlt = [o.wert for o in self._optionen(dimension) if o.gewaehlt]
        return gewaehlt[0] if len(gewaehlt) == 1 else None

    def _lies_antwort(self) -> tuple[Antwortlesung | None, Befund | None]:
        if self.antwort is None:
            return None, None
        try:
            nutzlast = self.antwort.json()
        except (PlaywrightFehler, ValueError) as fehler:
            return None, Befund("antwort", f"Antwort nicht lesbar: {kurz(fehler)}")
        return lies_antwort(nutzlast, self.karte.antwort, self.antwort.url), None

    def _screenshot(self, bereich: Locator) -> tuple[bytes | None, tuple[Befund, ...]]:
        try:
            return bereich.screenshot(type="png", timeout=self.frist_ms), ()
        except PlaywrightFehler as fehler:
            return None, (Befund("screenshot", f"Screenshot fehlt: {kurz(fehler)}"),)
