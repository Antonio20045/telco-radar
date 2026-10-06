"""Tor des Klick-Crawlers: robots.txt, Crawl-delay je Host, Umleitungen und Nebenwege.

Der Klick-Crawler öffnet seinen Kontext über ``klickkontext.oeffne_kontext``; jede
Anfrage der Seite geht durch das ``Tor``, bevor sie hinausgeht. Bilder, Medien,
Schriften und Datenkanäle ohne Nutzen für die Lesung (EventSource, Beacon, Prefetch,
Manifest) bricht das Tor ab. Jede andere Adresse prüft ``RobotsWaechter.darf`` und
passiert die Schleuse ihres Hosts, die den Crawl-delay abwartet: je Host ist höchstens
eine Anfrage unterwegs, und der Abstand zählt ab dem Ende der letzten Antwort. Das Tor
holt die Antwort selbst und folgt keiner Umleitung blind: jedes Ziel prüft es wie eine
neue Anfrage, ein gesperrtes Ziel geht nie hinaus. Leitet die Hauptseite um, merkt es
das erlaubte Ziel, beantwortet die Umleitung mit einer leeren Seite, und der Crawler
öffnet das Ziel als neue Seite. Bekommt eine Anfrage keine Antwort, steht sie mit Grund
in ``Klicklauf.gescheitert``.

Ein WebSocket verbindet nie (sperrt robots.txt ihn, steht er in ``verworfen``), und
Speculation Rules entfernt das Tor aus Kopf und Dokument jeder Antwort; was sonst an
``route`` vorbeiginge, schließt ``klickkontext`` aus.
"""

from __future__ import annotations

import logging
import re
import time
from collections.abc import Callable
from datetime import datetime
from typing import TYPE_CHECKING, Protocol
from urllib.parse import urljoin

from playwright.sync_api import Error as PlaywrightFehler

from . import Abrufschleuse
from .basis import GeraeteAbrufFehler
from .klicklauf import Gescheitert, Klicklauf, Verworfen
from .robots import RobotsWaechter, host_von

if TYPE_CHECKING:
    from playwright.sync_api import (
        APIResponse,
        Request,
        Route,
        WebSocketRoute,
    )


log = logging.getLogger(__name__)

ABGEBROCHENE_ARTEN = frozenset(
    {
        "image",
        "media",
        "font",
        "eventsource",
        "websocket",
        "ping",
        "prefetch",
        "manifest",
        "texttrack",
        "cspviolationreport",
    }
)
ABBRUCH_CODE = "blockedbyclient"
FEHLER_CODE = "failed"
HOECHSTE_UMLEITUNGEN = 5
UMLEITUNG_AB = 300
UMLEITUNG_BIS = 399
SIEHE_ANDERE = 303
SEITEN_FRIST_MS = 30000
ABRUF_FRIST_MS = SEITEN_FRIST_MS
WARTE_TAKT_MS = 50
GRUND_ZU_VIELE = f"mehr als {HOECHSTE_UMLEITUNGEN} Umleitungen"
LEERE_SEITE = 200
SPEKULATIONSKOPF = "speculation-rules"
NEU_BERECHNET = frozenset({SPEKULATIONSKOPF, "content-length", "content-encoding"})
WEB_SCHEMA = {"ws": "http", "wss": "https"}
_SPEKULATIONSSKRIPT = re.compile(
    rb"<script\b[^>]*?\btype\s*=\s*[\"']?\s*speculationrules\b[^>]*>.*?</script\s*>",
    re.I | re.S,
)


class Schleuse(Protocol):
    """Das robots-Tor vor einem Abruf; hält den Abstand je Host über Läufe hinweg."""

    def passiere(self, url: str) -> None:
        """Wartet den Abstand ab oder wirft ``GeraeteAbrufFehler``."""

    def erledigt(self, url: str) -> None:
        """Merkt das Ende der Antwort; ab hier zählt der Abstand."""

    def abstand(self, url: str) -> float:
        """Der Abstand in Sekunden, den ``passiere`` für ``url`` höchstens wartet."""


class _Hostabruf(Abrufschleuse):
    """Eine ``Abrufschleuse``, deren Abstand ab dem Ende der letzten Antwort zählt."""

    def erledigt(self) -> None:
        """Setzt den letzten Abruf auf jetzt, nach dem Ende der Antwort."""
        self._letzter_abruf = time.monotonic()


class Hostschleuse:
    """Je Host eine Abrufschleuse: Crawl-delay und Besuchszeit des Zielhosts.

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
        self._je_host: dict[str, _Hostabruf] = {}

    def passiere(self, url: str) -> None:
        """Wartet den Abstand des Hosts von ``url`` ab; eine Sperre wirft."""
        self._fuer(url).passiere(url)

    def erledigt(self, url: str) -> None:
        """Die Antwort von ``url`` ist da; der nächste Abruf wartet ab jetzt."""
        self._fuer(url).erledigt()

    def abstand(self, url: str) -> float:
        """Crawl-delay des Hosts oder eigenes Rate-Limit, der größere Wert."""
        return self._waechter.abstand(url, self._rate_limit)

    def _fuer(self, url: str) -> _Hostabruf:
        host = host_von(url)
        if host not in self._je_host:
            schleuse = _Hostabruf(self._waechter, self._uhr, self._rate_limit)
            self._je_host[host] = schleuse
        return self._je_host[host]


class Tor:
    """Route-Handler des Browserkontexts: robots.txt, Schleuse und Umleitungen.

    ``warte`` wartet, ohne den Browser anzuhalten (``Page.wait_for_timeout``);
    ``klickkontext.oeffne_kontext`` setzt es, sobald die Seite steht. Jede Anfrage
    darf ``ABRUF_FRIST_MS`` dauern; eine Antwort nach der Frist des Crawlers ist spät,
    nicht gescheitert. Was nach ``geschlossen`` scheitert, zählt nicht als gescheitert.
    """

    def __init__(
        self,
        waechter: RobotsWaechter,
        uhr: Callable[[], datetime],
        schleuse: Schleuse,
        lauf: Klicklauf,
    ) -> None:
        self.waechter, self.uhr, self.schleuse = waechter, uhr, schleuse
        self.lauf = lauf
        self.geschlossen = False
        self.umleitung: str | None = None
        self.warte: Callable[[float], None] | None = None
        self._unterwegs: set[str] = set()

    def darf(self, url: str) -> tuple[bool, str]:
        """Ob robots.txt ``url`` jetzt erlaubt, und der Grund, wenn nicht."""
        return self.waechter.darf(url, self.uhr())

    def __call__(self, route: Route) -> None:
        """Lässt eine Anfrage durch, leitet sie geprüft um oder bricht sie ab."""
        anfrage = route.request
        if anfrage.resource_type in ABGEBROCHENE_ARTEN:
            _schliesse(route, ABBRUCH_CODE)
            return
        try:
            self._leite(route, anfrage)
        except PlaywrightFehler as fehler:
            log.warning("Klick-Crawler: %s abgebrochen: %s", anfrage.url, kurz(fehler))
            _schliesse(route, FEHLER_CODE)

    def websocket(self, verbindung: WebSocketRoute) -> None:
        """Ein WebSocket verbindet nie; sperrt robots.txt ihn, steht er in verworfen."""
        schema, _, rest = verbindung.url.partition(":")
        darf, grund = self.darf(f"{WEB_SCHEMA.get(schema, schema)}:{rest}")
        if not darf:
            self.lauf.verworfen.append(Verworfen(verbindung.url, grund, verbindung.url))
        log.info("Klick-Crawler: WebSocket %s nicht verbunden", verbindung.url)

    def _leite(self, route: Route, anfrage: Request) -> None:
        ziel, methode = anfrage.url, anfrage.method
        for _ in range(HOECHSTE_UMLEITUNGEN + 1):
            if not self._belege(route, ziel, anfrage.url):
                return
            antwort = self._hole(route, ziel, methode)
            if antwort is None:
                return
            ort = antwort.headers.get("location")
            if ort is None or not UMLEITUNG_AB <= antwort.status <= UMLEITUNG_BIS:
                _gib_weiter(route, antwort)
                return
            ziel = urljoin(ziel, ort)
            methode = "GET" if antwort.status == SIEHE_ANDERE else methode
            if anfrage.is_navigation_request() and anfrage.frame.parent_frame is None:
                self._leite_hauptseite_um(route, ziel, anfrage.url)
                return
        self._scheitere(route, anfrage.url, GRUND_ZU_VIELE)

    def _belege(self, route: Route, ziel: str, anfrage: str) -> bool:
        """Prüft robots.txt, wartet auf den freien Host und den Crawl-delay.

        Wahr, wenn ``ziel`` hinaus darf; der Host bleibt belegt, bis ``_hole`` ihn
        freigibt. Sonst ist die Anfrage verworfen oder gescheitert und abgebrochen.
        """
        darf, grund = self.darf(ziel)
        if darf:
            host = host_von(ziel)
            if not self._frei(host):
                belegt = f"Host {host} nach {SEITEN_FRIST_MS} ms noch belegt"
                self._scheitere(route, ziel, belegt)
                return False
            self._unterwegs.add(host)
            try:
                self.schleuse.passiere(ziel)
                return True
            except GeraeteAbrufFehler as fehler:
                self._unterwegs.discard(host)
                grund = str(fehler)
        self._verwirf(route, ziel, grund, anfrage)
        return False

    def _frei(self, host: str) -> bool:
        for _ in range(SEITEN_FRIST_MS // WARTE_TAKT_MS):
            if host not in self._unterwegs or self.warte is None:
                break
            self.warte(WARTE_TAKT_MS)
        return host not in self._unterwegs

    def _hole(self, route: Route, ziel: str, methode: str) -> APIResponse | None:
        try:
            return route.fetch(
                url=ziel, method=methode, max_redirects=0, timeout=ABRUF_FRIST_MS
            )
        except PlaywrightFehler as fehler:
            self._scheitere(route, ziel, kurz(fehler))
            return None
        finally:
            self._unterwegs.discard(host_von(ziel))
            self.schleuse.erledigt(ziel)

    def _leite_hauptseite_um(self, route: Route, ziel: str, anfrage: str) -> None:
        darf, grund = self.darf(ziel)
        if not darf:
            self._verwirf(route, ziel, grund, anfrage)
            return
        self.umleitung = ziel
        route.fulfill(status=LEERE_SEITE, content_type="text/html", body="")

    def _verwirf(self, route: Route, url: str, grund: str, anfrage: str) -> None:
        self.lauf.verworfen.append(Verworfen(url, grund, anfrage))
        _schliesse(route, ABBRUCH_CODE)

    def _scheitere(self, route: Route, url: str, grund: str) -> None:
        if self.geschlossen:
            log.info("Klick-Crawler: %s beim Schließen abgebrochen: %s", url, grund)
        else:
            log.warning("Klick-Crawler: %s gescheitert: %s", url, grund)
            self.lauf.gescheitert.append(Gescheitert(url, grund, route.request.url))
        _schliesse(route, FEHLER_CODE)


def kurz(fehler: BaseException) -> str:
    """Erste Zeile einer Fehlermeldung, sonst der Name der Ausnahme."""
    zeilen = str(fehler).strip().splitlines()
    return zeilen[0] if zeilen else type(fehler).__name__


def _gib_weiter(route: Route, antwort: APIResponse) -> None:
    """Reicht die Antwort durch, ohne Speculation Rules in Kopf und Dokument."""
    kopf = antwort.headers
    html = "html" in kopf.get("content-type", "").lower()
    koerper = antwort.body() if html else b""
    ohne = _SPEKULATIONSSKRIPT.sub(b"", koerper)
    if SPEKULATIONSKOPF not in kopf and ohne == koerper:
        route.fulfill(response=antwort)
        return
    log.info("Klick-Crawler: Speculation Rules aus %s entfernt", antwort.url)
    neu = {k: v for k, v in kopf.items() if k not in NEU_BERECHNET}
    route.fulfill(response=antwort, headers=neu, body=ohne if html else antwort.body())


def _schliesse(route: Route, code: str) -> None:
    try:
        route.abort(code)
    except PlaywrightFehler as fehler:
        log.info("Klick-Crawler: Anfrage nicht abgebrochen: %s", kurz(fehler))
