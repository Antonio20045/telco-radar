"""Klick-Crawler: klickt jede angebotene Variante einer Produktseite, liest zweifach.

Gerüst aus Schritt 4 des Datenkonzepts Geräteradar (Abschnitt 8); noch ruft es kein
Tageslauf. Je Produktseite und Klick-Karte (``klickkarte``):

1. Die Schleuse (robots.txt, Crawl-delay, Besuchszeit) lässt die Seite zu, dann lädt
   der Browser sie. Jede Adresse, die die Seite dabei oder nach einem Klick lädt, geht
   durch ``RobotsWaechter.darf``; gesperrte Anfragen bricht der Crawler ab, bevor sie
   hinausgehen, und führt sie in ``verworfen``. Bilder, Medien und Schriften lädt er
   nicht.
2. Antwortet die Seite mit 202 (Challenge), 4xx oder 5xx oder fehlt der Kanarienwert,
   ist der Abruf gestört: kein zweiter Versuch, keine Umgehung (CLAUDE.md Regel 4).
   Sperrt robots.txt die Seite oder ihre Preisantwort, ist der Lauf gesperrt.
3. Er liest die angebotenen Optionen je Dimension und klickt jede Kombination; vor
   jedem Klick wartet die Schleuse den Crawl-delay ab, ``expect_response`` schneidet
   die Antwort zum Klick mit. Danach liest er die Preiszusammenfassung, prüft das Echo
   (``klickecho``) und macht einen Screenshot des Preisbereichs.
4. Je Kombination: erfasst, nicht_angeboten, nicht_erfasst oder befund; dazu der
   Strukturwächter je Lauf (beides in ``klicklauf``, hier mit ausgeführt).

Den Browser startet der Aufrufer und reicht eine Seite herein; dieses Modul setzt keine
Tarnung, keinen Proxy und keine fremde Kennung.
"""

from __future__ import annotations

import itertools
import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Protocol

from playwright.sync_api import Error as PlaywrightFehler
from playwright.sync_api import TimeoutError as PlaywrightZeitueberschreitung

from . import Abrufschleuse
from .basis import GeraeteAbrufFehler
from .klickecho import (
    Antwortlesung,
    Befund,
    Variante,
    lies_antwort,
    lies_zusammenfassung,
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
    Strukturbilanz,
    Verworfen,
    abruf_gestoert,
    strukturbruch,
)
from .robots import RobotsWaechter

if TYPE_CHECKING:
    from playwright.sync_api import Locator, Page, Response, Route


log = logging.getLogger(__name__)

ANTWORT_FRIST_MS = 15000
SEITEN_FRIST_MS = 30000
BLOCKIERTE_ARTEN = frozenset({"image", "media", "font"})
ABBRUCH_CODE = "blockedbyclient"
_OPTIONEN_JS = """(knoepfe, art) => knoepfe.map((k) => [
  art.wert ? k.getAttribute(art.wert) : k.innerText,
  k.disabled === true || k.getAttribute("aria-disabled") === "true",
  k.getAttribute(art.marke) === art.markenwert,
])"""
_ZWEI_BILDER_JS = (
    "() => new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r)))"
)


@dataclass(frozen=True)
class Option:
    """Ein Optionsknopf: Wert, deaktiviert, gewählt."""

    wert: str | None
    deaktiviert: bool
    gewaehlt: bool


class Schleuse(Protocol):
    """Das robots-Tor vor einem Abruf; ``Abrufschleuse`` erfüllt es."""

    def passiere(self, url: str) -> None:
        """Wartet den Abstand ab oder wirft ``GeraeteAbrufFehler``."""


def klicke_durch(
    seite: Page,
    adresse: str,
    karte: Klickkarte,
    waechter: RobotsWaechter,
    uhr: Callable[[], datetime],
    *,
    rate_limit_sekunden: float = 0.0,
    schleuse: Schleuse | None = None,
    vorlauf: Strukturbilanz | None = None,
    frist_ms: int = ANTWORT_FRIST_MS,
) -> Klicklauf:
    """Klickt alle angebotenen Kombinationen auf ``adresse``; wirft nie.

    ``uhr`` liefert die Zeit des nächsten Abrufs für robots.txt; ohne ``schleuse``
    entsteht eine ``Abrufschleuse`` mit ``rate_limit_sekunden``. Ein Abbruch steht
    als Status und Grund im Lauf, die Kombinationen bis dahin bleiben erhalten.
    """
    lauf = Klicklauf(anbieter=karte.anbieter, adresse=adresse)
    tor = schleuse or Abrufschleuse(waechter, uhr, rate_limit_sekunden)
    gang = _Gang(seite, karte, waechter, uhr, tor, frist_ms, lauf)
    try:
        gang.laufe()
    except _Abbruch as abbruch:
        lauf.status, lauf.grund = abbruch.status, abbruch.grund
    except PlaywrightFehler as fehler:
        lauf.status, lauf.grund = LAUF_GESTOERT, f"Browserfehler: {_kurz(fehler)}"
    finally:
        gang.raeume_auf()
    bruch = strukturbruch(lauf.struktur, vorlauf) if vorlauf is not None else None
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
    """Zustand eines Laufs: Seite, Karte, Tor und die Antwort zum aktuellen Stand."""

    def __init__(
        self,
        seite: Page,
        karte: Klickkarte,
        waechter: RobotsWaechter,
        uhr: Callable[[], datetime],
        schleuse: Schleuse,
        frist_ms: int,
        lauf: Klicklauf,
    ) -> None:
        self.seite, self.karte, self.lauf = seite, karte, lauf
        self.waechter, self.uhr, self.schleuse = waechter, uhr, schleuse
        self.frist_ms = frist_ms
        self.antwort: Response | None = None
        self.mitschnitt: list[Response] = []
        self.tor = self._tor
        self.schneide_mit = self._schneide_mit
        self.eingerichtet = False

    def raeume_auf(self) -> None:
        if not self.eingerichtet:
            return
        try:
            self.seite.remove_listener("response", self.schneide_mit)
            self.seite.unroute("**/*", self.tor)
        except PlaywrightFehler as fehler:
            log.warning("Klick-Crawler: Tor nicht entfernt: %s", _kurz(fehler))

    def laufe(self) -> None:
        self.seite.route("**/*", self.tor)
        self.seite.on("response", self.schneide_mit)
        self.eingerichtet = True
        self._oeffne()
        werte = {d: self._angebotene_werte(d) for d in DIMENSIONEN}
        for kombination in itertools.product(*(werte[d] for d in DIMENSIONEN)):
            ziel = dict(zip(DIMENSIONEN, kombination, strict=True))
            self.lauf.ergebnisse.append(self._kombination(ziel))

    def _tor(self, route: Route) -> None:
        anfrage = route.request
        if anfrage.resource_type in BLOCKIERTE_ARTEN:
            route.abort(ABBRUCH_CODE)
            return
        darf, grund = self.waechter.darf(anfrage.url, self.uhr())
        if not darf:
            self.lauf.verworfen.append(Verworfen(anfrage.url, grund))
            route.abort(ABBRUCH_CODE)
            return
        route.fallback()

    def _passt(self, antwort: Response) -> bool:
        return self.karte.antwort.passt(antwort.url)

    def _schneide_mit(self, antwort: Response) -> None:
        if self._passt(antwort):
            self.mitschnitt.append(antwort)

    def _passiere(self) -> None:
        try:
            self.schleuse.passiere(self.lauf.adresse)
        except GeraeteAbrufFehler as fehler:
            raise _Abbruch(LAUF_GESPERRT, str(fehler)) from fehler

    def _oeffne(self) -> None:
        self._passiere()
        haupt = self.seite.goto(self.lauf.adresse, timeout=SEITEN_FRIST_MS)
        self.lauf.http_status = haupt.status if haupt is not None else None
        stoerung = abruf_gestoert(self.lauf.http_status)
        if stoerung is not None:
            raise _Abbruch(LAUF_GESTOERT, stoerung)
        kanarie = self.karte.kanarie
        if kanarie.enthaelt not in self._text(self.seite.locator(kanarie.selektor)):
            grund = f"Kanarienwert fehlt: {kanarie.selektor} ohne „{kanarie.enthaelt}“"
            raise _Abbruch(LAUF_GESTOERT, grund)
        if not self.mitschnitt:
            self._warte_auf_mitschnitt()
        self._nimm_antwort(self.mitschnitt[-1] if self.mitschnitt else None, 0)

    def _warte_auf_mitschnitt(self) -> None:
        try:
            self.seite.wait_for_event("response", self._passt, timeout=self.frist_ms)
        except PlaywrightZeitueberschreitung:
            log.info(
                "Klick-Crawler %s: keine Preisantwort beim Laden", self.lauf.adresse
            )

    def _nimm_antwort(self, antwort: Response | None, seit: int) -> None:
        if antwort is None:
            verworfen = self.lauf.verworfen[seit:]
            gesperrt = [v for v in verworfen if self.karte.antwort.passt(v.url)]
            if gesperrt:
                raise _Abbruch(LAUF_GESPERRT, f"Preisantwort {gesperrt[0].grund}")
        else:
            stoerung = abruf_gestoert(antwort.status)
            if stoerung is not None:
                raise _Abbruch(LAUF_GESTOERT, f"Preisantwort: {stoerung}")
        self.antwort = antwort

    def _optionen(self, dimension: str) -> list[Option]:
        knopf = self.karte.knoepfe[dimension]
        art = {
            "wert": knopf.wert_attribut,
            "marke": self.karte.gewaehlt.attribut,
            "markenwert": self.karte.gewaehlt.wert,
        }
        roh = self.seite.locator(knopf.selektor).evaluate_all(_OPTIONEN_JS, art)
        return [Option(_wert(w), bool(aus), bool(an)) for w, aus, an in roh]

    def _angebotene_werte(self, dimension: str) -> list[str | None]:
        optionen = self._optionen(dimension)
        self.lauf.struktur.knopf(bool(optionen))
        werte: list[str | None] = list(
            dict.fromkeys(o.wert for o in optionen if o.wert is not None)
        )
        return werte or [None]

    def _kombination(self, ziel: dict[str, str | None]) -> Kombiergebnis:
        variante = variante_aus(*(ziel[d] for d in DIMENSIONEN))
        fehlend = [d for d in DIMENSIONEN if ziel[d] is None]
        if fehlend:
            self.lauf.struktur.knopf(False)
            return Kombiergebnis(variante, NICHT_ERFASST, self._fehlen(fehlend[0]))
        for dimension in DIMENSIONEN:
            ergebnis = self._waehle(dimension, str(ziel[dimension]), variante)
            if ergebnis is not None:
                return ergebnis
        return self._lies(variante)

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
        if stelle is None or optionen[stelle].deaktiviert:
            grund = f"Seite bietet {dimension} {wert} nicht an"
            return Kombiergebnis(variante, NICHT_ANGEBOTEN, grund)
        if optionen[stelle].gewaehlt:
            return None
        return self._klicke(dimension, stelle, variante)

    def _klicke(
        self, dimension: str, stelle: int, variante: Variante
    ) -> Kombiergebnis | None:
        self._passiere()
        seit = len(self.lauf.verworfen)
        knopf = self.seite.locator(self.karte.knoepfe[dimension].selektor).nth(stelle)
        try:
            with self.seite.expect_response(
                self._passt, timeout=self.frist_ms
            ) as klick:
                self._druecke(knopf)
            antwort: Response | None = klick.value
        except _Klickfehler as fehler:
            grund = f"Knopf für {dimension} nicht klickbar: {fehler}"
            return Kombiergebnis(variante, NICHT_ERFASST, grund)
        except PlaywrightZeitueberschreitung:
            antwort = None
        self._nimm_antwort(antwort, seit)
        return None

    def _druecke(self, knopf: Locator) -> None:
        try:
            knopf.click(timeout=self.frist_ms)
        except PlaywrightFehler as fehler:
            raise _Klickfehler(_kurz(fehler)) from fehler

    def _lies(self, variante: Variante) -> Kombiergebnis:
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
        angezeigt = variante_aus(*(self._gewaehlt(d) for d in DIMENSIONEN))
        echo = pruefe_echo(variante, angezeigt, im_text, lesung)
        bild, bildbefunde = self._screenshot(bereich)
        befunde = echo.befunde + bildbefunde
        erster: str | None = befunde[0].grund if befunde else None
        status = BEFUND if befunde else ERFASST
        return Kombiergebnis(
            variante, status, erster, echo.werte, befunde, echo.luecken, bild, url
        )

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
            return None, Befund("antwort", f"Antwort nicht lesbar: {_kurz(fehler)}")
        return lies_antwort(nutzlast, self.karte.antwort), None

    def _screenshot(self, bereich: Locator) -> tuple[bytes | None, tuple[Befund, ...]]:
        try:
            return bereich.screenshot(type="png", timeout=self.frist_ms), ()
        except PlaywrightFehler as fehler:
            return None, (Befund("screenshot", f"Screenshot fehlt: {_kurz(fehler)}"),)


def _wert(roh: object) -> str | None:
    text = " ".join(roh.split()) if isinstance(roh, str) else ""
    return text or None


def _kurz(fehler: BaseException) -> str:
    zeilen = str(fehler).strip().splitlines()
    return zeilen[0] if zeilen else type(fehler).__name__
