"""Eine Seite der Klick-Erkundung: öffnen, lesen, probieren, mit Zeitgrenze.

``Seitenlauf`` öffnet die Produktseite in einem Kontext wie der Klick-Crawler
(``klickkontext.oeffne_sitzung``) mit dem Tor (``klicktor.Tor``), folgt Umleitungen
geprüft wie der Crawler, wartet auf Laden und Ruhe (Takte von ``RUHE_MS``; Zeit, in der
das Tor den Crawl-delay abwartet, zählt nicht) und lehnt eine Einwilligungsabfrage ab.
Dann hält er Seite, Screenshot und Inventar fest und probiert Klicks (``klickproben``).
Jede Antwort sieht der Lauf schon im Tor (``Tor.beobachter``): eine 403 oder 429 der
eigenen Website auf eine Daten- oder Dokumentanfrage (``klickspur.bot_verdacht``) ist
sofort eine Störung, vor jeder weiteren Anfrage, und jeder Set-Cookie-Wert kommt auf die
Liste zum Schwärzen. In jedem Takt fragt ``pruefe`` die Spur nach Challenge-Mustern und
das Tor nach Störung; dann geht keine Anfrage mehr hinaus und ``Seitenergebnis.bot`` ist
wahr, außer die Hauptseite war tot (404, 410). Die ``Fristschleuse`` hält die
Zeitgrenze: ``offen`` ist die eine Definition, ob ein Abruf samt Abstand noch vor der
Grenze hinausginge; danach verwirft das Tor jede Anfrage, und der Lauf endet mit
``GRUND_FRIST``. ``beobachte`` ist die Beobachtung des Tors, die auch die Kartenprobe
nutzt. Eine Seite ohne Bedienelement oder ohne Preis-Kandidat heißt
``LAUF_LEER`` mit Grund, nie „gelesen“. Alles, was die Ablage braucht, steht danach im
``Seitenergebnis``.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING

from playwright.sync_api import Error as PlaywrightFehler

from .basis import GeraeteAbrufFehler
from .klickinventar import Inventar, lies_inventar
from .klickkontext import Sitzung, oeffne_sitzung, schliesse
from .klicklauf import LAUF_GELESEN, LAUF_GESPERRT, LAUF_GESTOERT, Klicklauf
from .klickproben import lehne_einwilligung_ab, probiere
from .klickspur import Eintrag, Spur, als_daten, bot_verdacht, ohne_geheimnisse
from .klicktor import (
    GRUND_ZU_VIELE,
    HOECHSTE_UMLEITUNGEN,
    SEITEN_FRIST_MS,
    WARTE_TAKT_MS,
    Hostschleuse,
    Tor,
    kurz,
)
from .klickwache import MINDESTE_RUHELESUNGEN, RUHE_MS, Abbruch
from .klickziele import Erkundungsziel, Seitenziel
from .robots import RobotsWaechter

if TYPE_CHECKING:
    from playwright.sync_api import APIResponse, Browser, Page, Request, ViewportSize

log = logging.getLogger(__name__)

RUHE_FRIST_MS = 20_000
FENSTER: ViewportSize = {"width": 1280, "height": 900}
ABGELAUFEN = "zeitgrenze"
GRUND_FRIST = "Zeitgrenze erreicht"
TOTE_STATUS = frozenset({404, 410})
LAUF_LEER = "leer"
SET_COOKIE = "set-cookie"
_GELADEN_JS = "() => document.readyState === 'complete'"


class Fristschleuse:
    """Eine Hostschleuse mit Zeitgrenze: nach ``ende`` geht keine Anfrage hinaus."""

    def __init__(self, innen: Hostschleuse, ende: float) -> None:
        self.innen, self.ende = innen, ende
        self.abgelaufen = False

    def setze(self, ende: float) -> None:
        """Neue Grenze für die nächste Seite."""
        self.ende, self.abgelaufen = ende, False

    def offen(self, url: str) -> bool:
        """Wahr, solange ein Abruf von ``url`` samt Abstand vor der Grenze hinausgeht.

        Dieselbe Grenze gilt für ``passiere`` und für den Klick-Crawler (``frist``).
        """
        return time.monotonic() + self.innen.abstand(url) < self.ende

    def passiere(self, url: str) -> None:
        """Wirft ``GeraeteAbrufFehler``, wenn der Abstand über die Grenze reicht."""
        if not self.offen(url):
            self.abgelaufen = True
            raise GeraeteAbrufFehler(f"{GRUND_FRIST}, nicht abgerufen")
        self.innen.passiere(url)

    def erledigt(self, url: str) -> None:
        """Die Antwort ist da; der Abstand zählt ab jetzt."""
        self.innen.erledigt(url)

    def abstand(self, url: str) -> float:
        """Crawl-delay oder eigener Abstand des Hosts."""
        return self.innen.abstand(url)


@dataclass
class Seitenergebnis:
    """Was eine Seite ergab: Status, Grund, Bot-Schutz und das Festgehaltene."""

    status: str = LAUF_GELESEN
    grund: str | None = None
    bot: bool = False
    ruhe: bool | None = None
    endadresse: str | None = None
    inventar: Inventar | None = None
    html: str | None = None
    bild: bytes | None = None
    einwilligung: dict | None = None
    klicks: list[dict] = field(default_factory=list)
    klick_vermerk: str | None = None
    cookies: set[str] = field(default_factory=set)
    http_status: int | None = None
    anfragen: list[dict] = field(default_factory=list)
    mitschnitt: list[dict] = field(default_factory=list)
    verworfen: list[dict] = field(default_factory=list)
    gescheitert: list[dict] = field(default_factory=list)


class Seitenlauf:
    """Eine Seite: Tor, Spur, Lauf für Verworfenes und Gescheitertes, Zeitgrenze."""

    seite: Page

    def __init__(
        self,
        browser: Browser,
        ziel: Erkundungsziel,
        seite: Seitenziel,
        waechter: RobotsWaechter,
        uhr: Callable[[], datetime],
        schleuse: Fristschleuse,
    ) -> None:
        self.browser, self.ziel, self.adresse = browser, ziel, seite.adresse
        self.lauf = Klicklauf(anbieter=ziel.name, adresse=seite.adresse)
        self.tor = Tor(waechter, uhr, schleuse, self.lauf)
        self.tor.beobachter = self._beobachte
        self.schleuse = schleuse
        self.spur = Spur()
        self.ergebnis = Seitenergebnis()
        self.geoeffnet = False

    def laufe(self) -> Seitenergebnis:
        """Öffnet, liest und probiert die Seite; wirft nie."""
        sitzung: Sitzung | None = None
        try:
            sitzung = oeffne_sitzung(self.browser, self.tor, FENSTER, self.ziel.kennung)
            self.seite = sitzung.seite
            self.spur.binde(self.seite)
            self._lies()
        except PlaywrightFehler as fehler:
            grund = self.tor.stoerung or f"Browserfehler: {kurz(fehler)}"
            self.ergebnis.status, self.ergebnis.grund = LAUF_GESTOERT, grund
        finally:
            self.tor.geschlossen = True
            self._raeume(sitzung)
            schliesse(sitzung)
        self._uebernimm()
        return self.ergebnis

    def pruefe(self) -> None:
        """Wirft ``Abbruch`` bei Bot-Schutz oder erreichter Zeitgrenze."""
        verdacht = self.spur.sammle(self.seite.url)
        if verdacht is not None and self.tor.stoerung is None:
            log.warning("Klick-Erkundung %s: %s", self.adresse, verdacht)
            self.tor.stoerung = verdacht
        if self.tor.stoerung is not None:
            self.ergebnis.bot = self.tor.haupt_status not in TOTE_STATUS
            raise Abbruch(LAUF_GESTOERT, self.tor.stoerung)
        if self.schleuse.abgelaufen or time.monotonic() >= self.schleuse.ende:
            raise Abbruch(ABGELAUFEN, GRUND_FRIST)

    def ruhe(self) -> bool:
        """Wartet, bis keine Anfrage läuft und zwei Lesungen gleich sind."""
        vorher: int | None = None
        for _ in range(max(MINDESTE_RUHELESUNGEN, RUHE_FRIST_MS // RUHE_MS)):
            self.pruefe()
            jetzt = self.spur.ruhe()
            if jetzt is not None and jetzt == vorher:
                return True
            vorher = jetzt
            self.seite.wait_for_timeout(RUHE_MS)
        return False

    def umgeleitet(self) -> str | None:
        """Ziel einer Umleitung der Hauptseite nach dem Öffnen, sonst ``None``."""
        return self.tor.umleitung if self.geoeffnet else None

    def _lies(self) -> None:
        try:
            self._oeffne()
            self.ergebnis.ruhe = self.ruhe()
            self.ergebnis.einwilligung = lehne_einwilligung_ab(self)
        except Abbruch as abbruch:
            self._halte_an(abbruch)
            if not self.geoeffnet:
                return
        self.ergebnis.endadresse = ohne_geheimnisse(self.seite.url)
        self.ergebnis.html = self.seite.content()
        self.ergebnis.bild = self.seite.screenshot(type="png")
        self.ergebnis.inventar = lies_inventar(self.seite)
        if self.ergebnis.status != LAUF_GELESEN:
            return
        try:
            probiere(self, self.ergebnis.inventar, self.ergebnis.klicks)
        except Abbruch as abbruch:
            self.ergebnis.klick_vermerk = abbruch.grund
            if abbruch.status != ABGELAUFEN:
                self._halte_an(abbruch)
        luecke = leer(self.ergebnis.inventar)
        if luecke is not None and self.ergebnis.status == LAUF_GELESEN:
            self.ergebnis.status, self.ergebnis.grund = LAUF_LEER, luecke

    def _halte_an(self, abbruch: Abbruch) -> None:
        status = LAUF_GESTOERT if abbruch.status == ABGELAUFEN else abbruch.status
        self.ergebnis.status, self.ergebnis.grund = status, abbruch.grund

    def _oeffne(self) -> None:
        ziel = self.adresse
        for _ in range(HOECHSTE_UMLEITUNGEN + 1):
            darf, grund = self.tor.darf(ziel)
            if not darf:
                raise Abbruch(LAUF_GESPERRT, grund)
            self._lade(ziel)
            if self.tor.umleitung is None:
                break
            ziel = self.tor.umleitung
        else:
            raise Abbruch(LAUF_GESTOERT, f"Abruf gestört ({GRUND_ZU_VIELE})")
        self.geoeffnet = True
        if not self._warte_geladen():
            raise Abbruch(
                LAUF_GESTOERT, f"Seite nach {SEITEN_FRIST_MS} ms nicht geladen"
            )
        darf, grund = self.tor.darf(self.seite.url)
        if not darf:
            raise Abbruch(LAUF_GESPERRT, grund)

    def _lade(self, ziel: str) -> None:
        self.tor.umleitung = None
        verworfen, gescheitert = len(self.lauf.verworfen), len(self.lauf.gescheitert)
        frist = SEITEN_FRIST_MS + round(1000 * self.schleuse.abstand(ziel))
        try:
            self.seite.goto(ziel, wait_until="commit", timeout=frist)
        except PlaywrightFehler as fehler:
            self.pruefe()
            if self.tor.umleitung is not None:
                return
            gesperrt = self.lauf.verworfen[verworfen:]
            if gesperrt:
                raise Abbruch(LAUF_GESPERRT, gesperrt[0].grund) from fehler
            ohne = self.lauf.gescheitert[gescheitert:]
            if ohne:
                grund = f"Abruf gestört ({ohne[0].grund})"
                raise Abbruch(LAUF_GESTOERT, grund) from fehler
            raise

    def _warte_geladen(self) -> bool:
        for _ in range(SEITEN_FRIST_MS // WARTE_TAKT_MS):
            self.pruefe()
            if self.seite.evaluate(_GELADEN_JS) is True:
                return True
            self.seite.wait_for_timeout(WARTE_TAKT_MS)
        return False

    def _beobachte(self, anfrage: Request, antwort: APIResponse) -> str | None:
        return beobachte(anfrage, antwort, self.adresse, self.ergebnis.cookies)

    def _uebernimm(self) -> None:
        """Was Tor, Spur und Lauf festhielten, als Daten ins Ergebnis."""
        self.ergebnis.http_status = self.tor.haupt_status
        self.ergebnis.anfragen = als_daten(self.spur.eintraege)
        self.ergebnis.mitschnitt = self.spur.mitschnitt
        self.ergebnis.verworfen = [
            {"url": ohne_geheimnisse(v.url), "grund": v.grund}
            for v in self.lauf.verworfen
        ]
        self.ergebnis.gescheitert = [
            {"url": ohne_geheimnisse(g.url), "grund": g.grund}
            for g in self.lauf.gescheitert
        ]

    def _raeume(self, sitzung: Sitzung | None) -> None:
        """Letzte Antworten in den Mitschnitt, Cookie-Werte zum Schwärzen merken."""
        if sitzung is None:
            return
        try:
            verdacht = self.spur.sammle(sitzung.seite.url)
            self.ergebnis.cookies.update(c["value"] for c in sitzung.kontext.cookies())
        except PlaywrightFehler as fehler:
            log.warning(
                "Klick-Erkundung %s: nicht aufgeräumt: %s", self.adresse, kurz(fehler)
            )
            return
        if verdacht is not None and self.ergebnis.status == LAUF_GELESEN:
            self.ergebnis.status, self.ergebnis.grund = LAUF_GESTOERT, verdacht
            self.ergebnis.bot = True


def leer(inventar: Inventar | None) -> str | None:
    """Grund, wenn die Seite kein Bedienelement oder keinen Preis-Kandidaten zeigt."""
    if inventar is None:
        return None
    fehlt = []
    if inventar.gesamt == 0:
        fehlt.append("kein Bedienelement")
    if inventar.preise_gesamt == 0:
        fehlt.append("kein Preis-Kandidat")
    return " und ".join(fehlt) if fehlt else None


def beobachte(
    anfrage: Request, antwort: APIResponse, adresse: str, cookies: set[str]
) -> str | None:
    """Merkt Set-Cookie-Werte in ``cookies``; Grund, wenn die Antwort nach Bot-Schutz
    aussieht (``klickspur.bot_verdacht`` gegen die Website von ``adresse``)."""
    for kopf in antwort.headers_array:
        if kopf["name"].lower() == SET_COOKIE:
            cookies.add(cookie_wert(kopf["value"]))
    art, url = anfrage.resource_type, ohne_geheimnisse(antwort.url)
    eintrag = Eintrag(0, anfrage.method, url, art, antwort.status)
    return bot_verdacht(eintrag, "", adresse)


def cookie_wert(set_cookie: str) -> str:
    """Der Wert aus einer Set-Cookie-Zeile ``name=wert; Attribute``."""
    paar = set_cookie.split(";", 1)[0]
    return paar.partition("=")[2].strip().strip('"')
