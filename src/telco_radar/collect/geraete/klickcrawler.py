"""Klick-Crawler: klickt jede angebotene Variante einer Produktseite, liest zweifach.

Gerüst aus Schritt 4 des Datenkonzepts Geräteradar (Abschnitt 8); noch ruft es kein
Tageslauf. Je Produktseite und Klick-Karte (``klickkarte``):

1. Der Crawler legt einen eigenen Browserkontext an (``klickkontext``). Jede Anfrage
   geht durch das Tor (``klicktor``): robots.txt für jede Adresse und jedes Ziel einer
   Umleitung, Crawl-delay je Host für jede Anfrage. Gesperrte Adressen gehen nicht
   hinaus und stehen in ``verworfen``, gescheiterte in ``gescheitert``. Die Seite
   lädt ohne Frist für die Wartezeit des Crawl-delays: die Frist zählt nur Zeit, in
   der niemand wartet. Nach dem Lauf verlässt er die Seite und schließt den Kontext.
2. Antwortet die Seite mit 202 (Challenge), 4xx oder 5xx oder fehlt der Kanarienwert,
   ist der Abruf gestört: kein zweiter Versuch, keine Umgehung (CLAUDE.md Regel 4).
   Sperrt robots.txt die Seite oder ihre Preisantwort, ist der Lauf gesperrt; scheitert
   die Preisanfrage, ist er gestört.
3. Er liest die angebotenen Optionen je Dimension und klickt jede Kombination; nach
   jedem Klick liest er die Optionen neu und führt neu erschienene Werte mit. Eine
   gewählte Option klickt er nicht; eine gesperrte heißt erst ``nicht_angeboten``,
   wenn die Seite ruht (keine Preisanfrage offen, zwei gleiche Lesungen). Eine
   Antwort gehört nur zu dem Klick, nach dem ihre Anfrage hinausging; bleibt eine
   Anfrage über die Frist offen, wartet er sie vor dem nächsten Klick ab oder bricht
   den Lauf als gestört ab. Dann liest ``klicklesung`` Antwort, Text, Markierung und
   Echo und macht einen Screenshot.
4. Je Kombination: erfasst, nicht_angeboten, nicht_erfasst oder befund; dazu der
   Strukturwächter je Lauf (beides in ``klicklauf``). Ist keine Kombination
   angeboten, ist der Lauf gestört.

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

from .klickecho import LAUFZEIT, Variante, variante_aus
from .klickkarte import DIMENSIONEN, Klickkarte
from .klickkontext import Mitschnitt, oeffne_kontext, schliesse
from .klicklauf import (
    LAUF_GELESEN,
    LAUF_GESPERRT,
    LAUF_GESTOERT,
    NICHT_ANGEBOTEN,
    NICHT_ERFASST,
    Klicklauf,
    Kombiergebnis,
    abruf_gestoert,
    ergebnisgrund,
    pruefe_struktur,
)
from .klicklesung import Leser
from .klickoptionen import Auswahl, Option, angebotene_werte, naechste, vereinige
from .klicktor import (
    GRUND_ZU_VIELE,
    HOECHSTE_UMLEITUNGEN,
    SEITEN_FRIST_MS,
    WARTE_TAKT_MS,
    Schleuse,
    Tor,
    kurz,
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
RUHE_MS = 500
MINDESTE_RUHELESUNGEN = 3
HOECHSTE_KOMBINATIONEN = 200
FENSTER: ViewportSize = {"width": 1280, "height": 900}
_GELADEN_JS = "() => document.readyState === 'complete'"

Marke = tuple[int, int]


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
    Anbieterlauf). ``vorlauf`` ist der letzte Lauf derselben Seite; sein Bezug für den
    Strukturwächter wandert weiter (``klicklauf.pruefe_struktur``). Ein Abbruch steht
    als Status und Grund im Lauf, die Kombinationen bis dahin bleiben erhalten.
    """
    lauf = Klicklauf(anbieter=karte.anbieter, adresse=adresse)
    tor = Tor(waechter, uhr, schleuse, lauf)
    kontext: BrowserContext | None = None
    seite: Page | None = None
    try:
        kontext, seite = oeffne_kontext(browser, tor, FENSTER)
        _Gang(seite, karte, tor, frist_ms, lauf).laufe()
    except _Abbruch as abbruch:
        lauf.status, lauf.grund = abbruch.status, abbruch.grund
    except PlaywrightFehler as fehler:
        lauf.status, lauf.grund = LAUF_GESTOERT, f"Browserfehler: {kurz(fehler)}"
    finally:
        tor.geschlossen = True
        schliesse(kontext, seite)
    bruch = pruefe_struktur(lauf, vorlauf)
    leer = ergebnisgrund(lauf.ergebnisse)
    for grund in (bruch, leer):
        if lauf.status == LAUF_GELESEN and grund is not None:
            lauf.status, lauf.grund = LAUF_GESTOERT, grund
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
        self.leser = Leser(seite, karte, frist_ms)
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
        if kanarie.enthaelt not in self.leser.text(
            self.seite.locator(kanarie.selektor)
        ):
            grund = f"Kanarienwert fehlt: {kanarie.selektor} ohne „{kanarie.enthaelt}“"
            raise _Abbruch(LAUF_GESTOERT, grund)
        self._nimm_antwort(self._antwort_seit(0), (0, 0))

    def _lade(self, ziel: str) -> Response | None:
        """Öffnet ``ziel``; die Frist bis zur Antwort trägt den Crawl-delay mit."""
        self.tor.umleitung = None
        verworfen, gescheitert = self._marke()
        frist = SEITEN_FRIST_MS + round(1000 * self.tor.schleuse.abstand(ziel))
        try:
            haupt = self.seite.goto(ziel, wait_until="commit", timeout=frist)
        except PlaywrightFehler as fehler:
            if self.tor.umleitung is not None:
                return None
            gesperrt = self.lauf.verworfen[verworfen:]
            if gesperrt:
                raise _Abbruch(LAUF_GESPERRT, gesperrt[0].grund) from fehler
            ohne = self.lauf.gescheitert[gescheitert:]
            if ohne:
                raise _Abbruch(
                    LAUF_GESTOERT, f"Abruf gestört ({ohne[0].grund})"
                ) from fehler
            raise
        if self.tor.umleitung is None and not self._warte(
            self._geladen, SEITEN_FRIST_MS
        ):
            raise _Abbruch(
                LAUF_GESTOERT, f"Seite nach {SEITEN_FRIST_MS} ms nicht geladen"
            )
        return haupt

    def _geladen(self) -> bool:
        try:
            return self.seite.evaluate(_GELADEN_JS) is True
        except PlaywrightFehler:
            return False

    def _warte(
        self, bedingung: Callable[[], bool], frist_ms: int | None = None
    ) -> bool:
        """Wartet in Takten; Wartezeit des Tors auf den Crawl-delay zählt nicht."""
        takte = (self.frist_ms if frist_ms is None else frist_ms) // WARTE_TAKT_MS
        for _ in range(max(1, takte)):
            if bedingung():
                return True
            self.seite.wait_for_timeout(WARTE_TAKT_MS)
        return bedingung()

    def _marke(self) -> Marke:
        return len(self.lauf.verworfen), len(self.lauf.gescheitert)

    def _antwort_seit(self, seit: int) -> Response | None:
        if not self._warte(lambda: self.mitschnitt.fertig_seit(seit)):
            return None
        return self.mitschnitt.letzte_seit(seit)

    def _nimm_antwort(self, antwort: Response | None, marke: Marke) -> None:
        passt = self.karte.antwort.passt
        if antwort is None:
            verworfen = self.lauf.verworfen[marke[0] :]
            gesperrt = [v for v in verworfen if passt(v.anfrage)]
            if gesperrt:
                raise _Abbruch(LAUF_GESPERRT, f"Preisantwort {gesperrt[0].grund}")
            gescheitert = self.lauf.gescheitert[marke[1] :]
            ohne = [g for g in gescheitert if passt(g.anfrage)]
            if ohne:
                grund = f"Preisantwort gescheitert: {ohne[0].grund}"
                raise _Abbruch(LAUF_GESTOERT, grund)
        else:
            stoerung = abruf_gestoert(antwort.status)
            if stoerung is not None:
                raise _Abbruch(LAUF_GESTOERT, f"Preisantwort: {stoerung}")
        self.antwort = antwort

    def _angebotene_werte(self, dimension: str) -> list[str | None]:
        optionen = self.leser.optionen(dimension)
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
        return self.leser.lies(variante, ziel, self.antwort, self.lauf.struktur)

    def _fehlen(self, dimension: str) -> str:
        selektor = self.karte.knoepfe[dimension].selektor
        return f"Knöpfe für {dimension} nicht gefunden ({selektor})"

    def _waehle(
        self, dimension: str, wert: str, variante: Variante
    ) -> Kombiergebnis | None:
        """Klickt ``wert``, wenn nötig; sonst das Ergebnis, das den Weg beendet.

        Eine gewählte Option bleibt, auch wenn die Seite sie sperrt. Eine gesperrte
        heißt erst ``nicht_angeboten``, wenn die Seite ruht; kommt sie nicht zur Ruhe,
        heißt die Kombination ``nicht_erfasst``.
        """
        optionen: list[Option] | None = self.leser.optionen(dimension)
        self.lauf.struktur.knopf(bool(optionen))
        if not optionen:
            return Kombiergebnis(variante, NICHT_ERFASST, self._fehlen(dimension))
        option = _option(optionen, wert)
        if option is not None and option.deaktiviert and not option.gewaehlt:
            optionen = self._in_ruhe(dimension)
            if optionen is None:
                grund = f"Seite kam für {dimension} {wert} nicht zur Ruhe"
                return Kombiergebnis(variante, NICHT_ERFASST, grund)
            option = _option(optionen, wert)
        if option is None:
            grund = f"Seite zeigt {dimension} {wert} in diesem Zustand nicht"
            return Kombiergebnis(variante, NICHT_ERFASST, grund)
        if option.gewaehlt:
            return None
        if option.deaktiviert:
            grund = f"Seite bietet {dimension} {wert} nicht an"
            return Kombiergebnis(variante, NICHT_ANGEBOTEN, grund)
        return self._klicke(dimension, optionen.index(option), variante)

    def _in_ruhe(self, dimension: str) -> list[Option] | None:
        """Die Knöpfe, sobald keine Preisanfrage offen ist und zwei Lesungen im Abstand
        ``RUHE_MS`` gleich sind; ``None``, wenn die Frist vorher abläuft."""
        vorher: list[Option] | None = None
        for _ in range(max(MINDESTE_RUHELESUNGEN, self.frist_ms // RUHE_MS)):
            jetzt = None if self.mitschnitt.offen else self.leser.optionen(dimension)
            if jetzt is not None and jetzt == vorher:
                return jetzt
            vorher = jetzt
            self.seite.wait_for_timeout(RUHE_MS)
        return None

    def _klicke(
        self, dimension: str, stelle: int, variante: Variante
    ) -> Kombiergebnis | None:
        if not self._warte(lambda: not self.mitschnitt.offen):
            grund = f"Preisantwort nach {self.frist_ms} ms noch offen"
            raise _Abbruch(LAUF_GESTOERT, grund)
        seit, marke = self.mitschnitt.stand(), self._marke()
        knopf = self.seite.locator(self.karte.knoepfe[dimension].selektor).nth(stelle)
        try:
            self._druecke(knopf)
        except _Klickfehler as fehler:
            grund = f"Knopf für {dimension} nicht klickbar: {fehler}"
            return Kombiergebnis(variante, NICHT_ERFASST, grund)
        self.geklickt = True
        self._nimm_antwort(self._antwort_seit(seit), marke)
        return None

    def _druecke(self, knopf: Locator) -> None:
        try:
            knopf.click(timeout=self.frist_ms)
        except PlaywrightFehler as fehler:
            raise _Klickfehler(kurz(fehler)) from fehler


def _option(optionen: list[Option], wert: str) -> Option | None:
    return next((o for o in optionen if o.wert == wert), None)
