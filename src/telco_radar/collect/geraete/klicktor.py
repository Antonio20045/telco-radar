"""Tor des Klick-Crawlers: robots.txt, Crawl-delay je Host und Umleitungen.

Der Klick-Crawler hängt ``Tor`` an seinen Browserkontext (``context.route``); jede
Anfrage der Seite geht hindurch, bevor sie hinausgeht. Bilder, Medien und Schriften
bricht das Tor ab. Jede andere Adresse prüft ``RobotsWaechter.darf``; Seiten, XHR und
Fetch passieren zusätzlich die Schleuse ihres Hosts, die den Crawl-delay abwartet. Das
Tor holt die Antwort selbst und folgt keiner Umleitung blind: jedes Ziel prüft es wie
eine neue Anfrage, ein gesperrtes Ziel geht nie hinaus. Leitet die Hauptseite um, merkt
es das erlaubte Ziel, beantwortet die Umleitung mit einer leeren Seite, und der Crawler
öffnet das Ziel als neue Seite. Service Worker sperrt der Kontext, weil ihre Anfragen an
``route`` vorbeigehen; was der Browser selbst an ``route`` vorbei anfragt (Favicons,
Art „Other“), bricht ``sperre_beiwege`` über das DevTools-Protokoll ab (nur Chromium).

``Mitschnitt`` merkt die Anfragen, die zum Antwortmuster der Karte passen, und ihre
Antworten; so gehört eine Antwort nur zu dem Klick, nach dem ihre Anfrage hinausging.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import datetime
from typing import TYPE_CHECKING, Protocol
from urllib.parse import urljoin

from playwright.sync_api import Error as PlaywrightFehler

from . import Abrufschleuse
from .basis import GeraeteAbrufFehler
from .klicklauf import Verworfen
from .robots import RobotsWaechter, host_von

if TYPE_CHECKING:
    from playwright.sync_api import BrowserContext, Page, Request, Response, Route


log = logging.getLogger(__name__)

GETAKTETE_ARTEN = frozenset({"document", "xhr", "fetch"})
BLOCKIERTE_ARTEN = frozenset({"image", "media", "font"})
ABBRUCH_CODE = "blockedbyclient"
FEHLER_CODE = "failed"
HOECHSTE_UMLEITUNGEN = 5
UMLEITUNG_AB = 300
UMLEITUNG_BIS = 399
SIEHE_ANDERE = 303
SEITEN_FRIST_MS = 30000
GRUND_ZU_VIELE = f"mehr als {HOECHSTE_UMLEITUNGEN} Umleitungen"
LEERE_SEITE = 200
BEIWEG_ARTEN = ("Other",)
BEIWEG_GRUND = "BlockedByClient"
LEER = "about:blank"


class Schleuse(Protocol):
    """Das robots-Tor vor einem Abruf; hält den Abstand je Host über Läufe hinweg."""

    def passiere(self, url: str) -> None:
        """Wartet den Abstand ab oder wirft ``GeraeteAbrufFehler``."""


class Hostschleuse:
    """Je Host eine ``Abrufschleuse``: Crawl-delay und Besuchszeit des Zielhosts.

    Eine Hostschleuse gilt für einen ganzen Anbieterlauf, damit der Abstand auch
    zwischen zwei Produktseiten desselben Hosts gilt; Hosts warten nicht aufeinander.
    """

    def __init__(
        self,
        waechter: RobotsWaechter,
        uhr: Callable[[], datetime],
        rate_limit_sekunden: float = 0.0,
    ) -> None:
        self._waechter, self._uhr = waechter, uhr
        self._rate_limit = rate_limit_sekunden
        self._je_host: dict[str, Abrufschleuse] = {}

    def passiere(self, url: str) -> None:
        """Wartet den Abstand des Hosts von ``url`` ab; eine Sperre wirft."""
        host = host_von(url)
        if host not in self._je_host:
            schleuse = Abrufschleuse(self._waechter, self._uhr, self._rate_limit)
            self._je_host[host] = schleuse
        self._je_host[host].passiere(url)


class Tor:
    """Route-Handler des Browserkontexts: robots.txt, Schleuse und Umleitungen."""

    def __init__(
        self,
        waechter: RobotsWaechter,
        uhr: Callable[[], datetime],
        schleuse: Schleuse,
        verworfen: list[Verworfen],
        frist_ms: int,
    ) -> None:
        self.waechter, self.uhr, self.schleuse = waechter, uhr, schleuse
        self.verworfen = verworfen
        self.frist_ms = frist_ms
        self.umleitung: str | None = None

    def darf(self, url: str) -> tuple[bool, str]:
        """Ob robots.txt ``url`` jetzt erlaubt, und der Grund, wenn nicht."""
        return self.waechter.darf(url, self.uhr())

    def __call__(self, route: Route) -> None:
        """Lässt eine Anfrage durch, leitet sie geprüft um oder bricht sie ab."""
        anfrage = route.request
        if anfrage.resource_type in BLOCKIERTE_ARTEN:
            _schliesse(route, ABBRUCH_CODE)
            return
        try:
            self._leite(route, anfrage)
        except PlaywrightFehler as fehler:
            log.warning("Klick-Crawler: %s gescheitert: %s", anfrage.url, kurz(fehler))
            _schliesse(route, FEHLER_CODE)

    def _leite(self, route: Route, anfrage: Request) -> None:
        ziel, methode, art = anfrage.url, anfrage.method, anfrage.resource_type
        frist = SEITEN_FRIST_MS if art == "document" else self.frist_ms
        for _ in range(HOECHSTE_UMLEITUNGEN + 1):
            grund = self._sperre(ziel, art)
            if grund is not None:
                self._verwirf(route, ziel, grund, anfrage.url)
                return
            antwort = route.fetch(
                url=ziel, method=methode, max_redirects=0, timeout=frist
            )
            ort = antwort.headers.get("location")
            if ort is None or not UMLEITUNG_AB <= antwort.status <= UMLEITUNG_BIS:
                route.fulfill(response=antwort)
                return
            ziel = urljoin(ziel, ort)
            methode = "GET" if antwort.status == SIEHE_ANDERE else methode
            if anfrage.is_navigation_request() and anfrage.frame.parent_frame is None:
                self._leite_hauptseite_um(route, ziel, anfrage.url)
                return
        log.warning("Klick-Crawler: %s, %s", anfrage.url, GRUND_ZU_VIELE)
        _schliesse(route, FEHLER_CODE)

    def _sperre(self, url: str, art: str) -> str | None:
        darf, grund = self.darf(url)
        if not darf:
            return grund
        if art not in GETAKTETE_ARTEN:
            return None
        try:
            self.schleuse.passiere(url)
        except GeraeteAbrufFehler as fehler:
            return str(fehler)
        return None

    def _leite_hauptseite_um(self, route: Route, ziel: str, anfrage: str) -> None:
        darf, grund = self.darf(ziel)
        if not darf:
            self._verwirf(route, ziel, grund, anfrage)
            return
        self.umleitung = ziel
        route.fulfill(status=LEERE_SEITE, content_type="text/html", body="")

    def _verwirf(self, route: Route, url: str, grund: str, anfrage: str) -> None:
        self.verworfen.append(Verworfen(url, grund, anfrage))
        _schliesse(route, ABBRUCH_CODE)


class Mitschnitt:
    """Anfragen zum Antwortmuster der Karte und ihre Antworten, in Reihenfolge."""

    def __init__(self, passt: Callable[[str], bool]) -> None:
        self._passt = passt
        self.anfragen: list[Request] = []
        self.offen: list[Request] = []
        self.antworten: list[Response] = []

    def anfrage(self, anfrage: Request) -> None:
        """Merkt eine passende Anfrage als offen."""
        if self._passt(anfrage.url):
            self.anfragen.append(anfrage)
            self.offen.append(anfrage)

    def antwort(self, antwort: Response) -> None:
        """Merkt eine passende Antwort; ihre Anfrage ist nicht mehr offen."""
        if self._passt(antwort.url):
            self.antworten.append(antwort)
            self._schliesse(antwort.request)

    def gescheitert(self, anfrage: Request) -> None:
        """Eine abgebrochene Anfrage ist nicht mehr offen."""
        self._schliesse(anfrage)

    def stand(self) -> int:
        """Zahl der bisher gemerkten Anfragen, die Marke vor einem Klick."""
        return len(self.anfragen)

    def fertig_seit(self, seit: int) -> bool:
        """Wahr, wenn seit der Marke eine Anfrage hinausging und keine offen ist."""
        neue = self.anfragen[seit:]
        return bool(neue) and not any(_unter(a, self.offen) for a in neue)

    def letzte_seit(self, seit: int) -> Response | None:
        """Die letzte Antwort auf eine Anfrage seit der Marke, sonst ``None``."""
        neue = self.anfragen[seit:]
        eigene = [a for a in self.antworten if _unter(a.request, neue)]
        return eigene[-1] if eigene else None

    def _schliesse(self, anfrage: Request) -> None:
        self.offen = [a for a in self.offen if a is not anfrage]


def sperre_beiwege(kontext: BrowserContext, seite: Page) -> None:
    """Bricht Anfragen der Seite ab, die der Browser an ``route`` vorbei stellt."""
    sitzung = kontext.new_cdp_session(seite)

    def verwirf(ereignis: dict) -> None:
        log.info("Klick-Crawler: %s abgebrochen", ereignis["request"]["url"])
        try:
            frage = {"requestId": ereignis["requestId"], "errorReason": BEIWEG_GRUND}
            sitzung.send("Fetch.failRequest", frage)
        except PlaywrightFehler as fehler:
            log.info("Klick-Crawler: Beiweg nicht abgebrochen: %s", kurz(fehler))

    sitzung.on("Fetch.requestPaused", verwirf)
    muster = [{"urlPattern": "*", "resourceType": a} for a in BEIWEG_ARTEN]
    sitzung.send("Fetch.enable", {"patterns": muster})


def schliesse(kontext: BrowserContext | None, seite: Page | None) -> None:
    """Verlässt die Seite, dann schließt der Kontext; wirft nie.

    Erst ``about:blank``: so bricht ``sperre_beiwege`` angehaltene Beiwege noch ab,
    bevor das Schließen sie freigäbe, und die Seite fragt danach nichts mehr an.
    """
    if kontext is None:
        return
    try:
        if seite is not None:
            seite.goto(LEER)
    except PlaywrightFehler as fehler:
        log.info("Klick-Crawler: Seite nicht verlassen: %s", kurz(fehler))
    try:
        kontext.close()
    except PlaywrightFehler as fehler:
        log.warning("Klick-Crawler: Kontext nicht geschlossen: %s", kurz(fehler))


def kurz(fehler: BaseException) -> str:
    """Erste Zeile einer Fehlermeldung, sonst der Name der Ausnahme."""
    zeilen = str(fehler).strip().splitlines()
    return zeilen[0] if zeilen else type(fehler).__name__


def _unter(anfrage: Request, anfragen: list[Request]) -> bool:
    return any(anfrage is a for a in anfragen)


def _schliesse(route: Route, code: str) -> None:
    try:
        route.abort(code)
    except PlaywrightFehler as fehler:
        log.info("Klick-Crawler: Anfrage nicht abgebrochen: %s", kurz(fehler))
