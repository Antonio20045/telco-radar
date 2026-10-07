"""Tor des Klick-Crawlers: robots.txt, Crawl-delay je Host, Umleitungen und Nebenwege.

Der Klick-Crawler öffnet seinen Kontext über ``klickkontext.oeffne_sitzung``; jede
Anfrage der Seite geht durch das ``Tor``, bevor sie hinausgeht. Bilder, Medien,
Schriften und Datenkanäle ohne Nutzen für die Lesung (EventSource, Beacon, Prefetch,
Manifest) bricht das Tor ab. Jede andere Adresse prüft ``RobotsWaechter.darf`` und
passiert die Schleuse ihres Hosts, die den Crawl-delay abwartet: je Host ist höchstens
eine Anfrage unterwegs, und der Abstand zählt ab dem Ende der letzten Antwort.
Skripte und Stylesheets eines Hosts, dessen robots.txt mit 401 oder 403 antwortet,
passieren die Schleuse ohne Regeln, mit dem eigenen Abstand (``klickhilfe``,
Entscheidung Antonio 07.10.2026); in den Browser kommen davon nur JavaScript und CSS,
alles andere verwirft das Tor. Das Tor
holt die Antwort selbst und folgt keiner Umleitung blind: jedes Ziel prüft es wie eine
neue Anfrage, ein gesperrtes Ziel geht nie hinaus. Leitet die Hauptseite um, merkt es
das erlaubte Ziel, beantwortet die Umleitung mit einer leeren Seite, und der Crawler
öffnet das Ziel als neue Seite. Bekommt eine Anfrage keine Antwort, steht sie mit Grund
in ``Klicklauf.gescheitert``.

Antwortet die Hauptseite mit Bot-Schutz (``klicklauf.bot_schutz``), beim Öffnen wie
mitten im Lauf, kommt die Seite nie im Browser an, und danach geht nichts mehr hinaus.
Ein WebSocket verbindet nie (sperrt robots.txt ihn, steht er in ``verworfen``), und
Vorabladen (Speculation Rules, ``<link rel=prerender|prefetch>``, Kopfzeile ``Link``)
entfernt das Tor aus Kopf und Dokument jeder Antwort; was sonst an ``route``
vorbeiginge, schließt ``klickkontext`` aus.

Für die Folgeseite (``klickfolgeseite``) darf genau ein Klick schreiben: Solange
``weiter_klick`` gilt, lässt das Tor jede Methode durch; die erste Anfrage der
Hauptseite danach (die Navigation des Klicks) setzt ``nur_lesen``, und ab dann
verwirft es jede Anfrage außer GET und HEAD mit ``GRUND_NUR_LESEN``.
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
from .klickhilfe import Ausnahmeweg
from .klicklauf import Gescheitert, Klicklauf, Verworfen, antworttext, bot_schutz
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
LESENDE_METHODEN = frozenset({"GET", "HEAD"})
GRUND_NUR_LESEN = "nach dem Weiter-Klick nur GET und HEAD"
LEERE_SEITE = 200
SPEKULATIONSKOPF = "speculation-rules"
LINKKOPF = "link"
NEU_BERECHNET = frozenset(
    {SPEKULATIONSKOPF, LINKKOPF, "content-length", "content-encoding"}
)
WEB_SCHEMA = {"ws": "http", "wss": "https"}
_VORABLADEN = re.compile(
    rb"<script\b[^>]*?\btype\s*=\s*[\"']?\s*speculationrules\b[^>]*>.*?</script\s*>"
    rb"|<link\b[^>]*?\brel\s*=\s*[\"']?[^\"'>]*?\b(?:prerender|prefetch)\b[^>]*>",
    re.I | re.S,
)
_VORAB_REL = re.compile(r"\brel\s*=\s*\"?[^\";,]*?\b(?:prerender|prefetch)\b", re.I)


class Schleuse(Protocol):
    """Das robots-Tor vor einem Abruf; hält den Abstand je Host über Läufe hinweg."""

    def passiere(self, url: str) -> None:
        """Wartet den Abstand ab oder wirft ``GeraeteAbrufFehler``."""

    def passiere_ohne_regeln(self, url: str) -> None:
        """Wie ``passiere``, ohne robots.txt zu fragen: nur für eine Hilfsdatei."""

    def erledigt(self, url: str) -> None:
        """Merkt das Ende der Antwort; ab hier zählt der Abstand."""

    def abstand(self, url: str) -> float:
        """Der Abstand in Sekunden, den ``passiere`` für ``url`` höchstens wartet."""


class _Hostabruf(Abrufschleuse):
    """Eine ``Abrufschleuse``, deren Abstand ab dem Ende der letzten Antwort zählt."""

    def passiere_ohne_regeln(self, url: str) -> None:
        """Wartet den Abstand ab (``RobotsWaechter.abstand``), ohne ``darf``."""
        abstand = self._waechter.abstand(url, self._rate_limit)
        if self._letzter_abruf:
            time.sleep(max(0.0, abstand + self._letzter_abruf - time.monotonic()))
        self._letzter_abruf = time.monotonic()

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

    def passiere_ohne_regeln(self, url: str) -> None:
        """Wartet den Abstand des Hosts von ``url`` ab, ohne robots.txt zu fragen."""
        self._fuer(url).passiere_ohne_regeln(url)

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
    ``klickkontext.oeffne_sitzung`` setzt es, sobald die Seite steht. Jede Anfrage
    darf ``ABRUF_FRIST_MS`` dauern; eine Antwort nach der Frist des Crawlers ist spät,
    nicht gescheitert. Was nach ``geschlossen`` scheitert, zählt nicht als gescheitert.
    Sieht eine Antwort auf die Hauptseite nach Bot-Schutz aus (``bot_schutz``), kommt
    sie nie im Browser an: ``stoerung`` nennt den Grund, ``haupt_status`` den Status,
    und keine weitere Anfrage geht hinaus; geprüft wird beim Eintritt und noch einmal
    nach jedem Warten auf Host und Abstand, unmittelbar vor dem Abruf. ``beobachter``
    sieht jede geholte Antwort, bevor sie in den Browser geht; nennt er einen Grund,
    ist das eine Störung, außer bei der Hauptseite (dort gilt ``bot_schutz``).
    ``weiter_klick`` und ``nur_lesen`` setzt die Folgeseite (siehe oben).
    """

    def __init__(
        self,
        waechter: RobotsWaechter,
        uhr: Callable[[], datetime],
        schleuse: Schleuse,
        lauf: Klicklauf,
    ) -> None:
        self.waechter, self.uhr, self.schleuse = waechter, uhr, schleuse
        self.lauf, self.ausnahme = lauf, Ausnahmeweg(waechter, lauf)
        self.geschlossen = False
        self.stoerung: str | None = None
        self.haupt_status: int | None = None
        self.umleitung: str | None = None
        self.warte: Callable[[float], None] | None = None
        self.beobachter: Callable[[Request, APIResponse], str | None] | None = None
        self.weiter_klick = False
        self.nur_lesen = False
        self._unterwegs: set[str] = set()

    def darf(self, url: str) -> tuple[bool, str]:
        """Ob robots.txt ``url`` jetzt erlaubt, und der Grund, wenn nicht."""
        return self.waechter.darf(url, self.uhr())

    def __call__(self, route: Route) -> None:
        """Lässt eine Anfrage durch, leitet sie geprüft um oder bricht sie ab."""
        anfrage = route.request
        if anfrage.resource_type in ABGEBROCHENE_ARTEN or self.stoerung is not None:
            _schliesse(route, ABBRUCH_CODE)
            return
        if self.nur_lesen and anfrage.method not in LESENDE_METHODEN:
            self._verwirf(route, anfrage.url, GRUND_NUR_LESEN, anfrage.url)
            return
        if self.weiter_klick and _hauptseite(anfrage):
            self.nur_lesen = True
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
            hauptseite = _hauptseite(anfrage)
            self._beobachte(anfrage, antwort, hauptseite)
            ort = antwort.headers.get("location")
            if ort is None or not UMLEITUNG_AB <= antwort.status <= UMLEITUNG_BIS:
                grund = self.ausnahme.pruefe(ziel, anfrage, antwort)
                if grund is not None:
                    self._verwirf(route, ziel, grund, anfrage.url)
                elif not hauptseite or self._pruefe_hauptseite(route, antwort):
                    _gib_weiter(route, antwort)
                return
            ziel = urljoin(ziel, ort)
            methode = "GET" if antwort.status == SIEHE_ANDERE else methode
            if hauptseite:
                self._leite_hauptseite_um(route, ziel, anfrage.url)
                return
        self._scheitere(route, anfrage.url, GRUND_ZU_VIELE)

    def _belege(self, route: Route, ziel: str, anfrage: str) -> bool:
        """Prüft robots.txt, wartet auf den freien Host und den Crawl-delay.

        Wahr, wenn ``ziel`` hinaus darf; der Host bleibt belegt, bis ``_hole`` ihn
        freigibt. Sonst ist die Anfrage verworfen oder gescheitert und abgebrochen.
        Eine Hilfsdatei (``Ausnahmeweg.darf``) passiert die Schleuse ohne Regeln.
        """
        darf, grund = self.darf(ziel)
        hilfe = not darf and self.ausnahme.darf(route.request.resource_type, ziel)
        if darf or hilfe:
            host = host_von(ziel)
            if not self._frei(host):
                belegt = f"Host {host} nach {SEITEN_FRIST_MS} ms noch belegt"
                self._scheitere(route, ziel, belegt)
                return False
            self._unterwegs.add(host)
            schleuse = self.schleuse
            passiere = schleuse.passiere_ohne_regeln if hilfe else schleuse.passiere
            try:
                passiere(ziel)
            except GeraeteAbrufFehler as fehler:
                self._unterwegs.discard(host)
                grund = str(fehler)
            else:
                if self.stoerung is None:
                    return True
                self._unterwegs.discard(host)
                _schliesse(route, ABBRUCH_CODE)
                return False
        self._verwirf(route, ziel, grund, anfrage)
        return False

    def _frei(self, host: str) -> bool:
        for _ in range(SEITEN_FRIST_MS // WARTE_TAKT_MS):
            if host not in self._unterwegs or self.warte is None:
                break
            self.warte(WARTE_TAKT_MS)
        return host not in self._unterwegs

    def _beobachte(
        self, anfrage: Request, antwort: APIResponse, hauptseite: bool
    ) -> None:
        grund = None if self.beobachter is None else self.beobachter(anfrage, antwort)
        if grund is not None and not hauptseite and self.stoerung is None:
            log.warning("Klick-Crawler: %s; Lauf endet", grund)
            self.stoerung = grund

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

    def _pruefe_hauptseite(self, route: Route, antwort: APIResponse) -> bool:
        """Wahr, wenn die Hauptseite in den Browser darf; Bot-Schutz bricht sie ab."""
        self.haupt_status = antwort.status
        typ = antwort.headers.get("content-type", "")
        text = antworttext(antwort.body(), typ) if "html" in typ.lower() else ""
        grund = bot_schutz(antwort.status, typ, text)
        if grund is None:
            return True
        log.warning("Klick-Crawler: %s, %s; Lauf endet", antwort.url, grund)
        if self.stoerung is None:
            self.stoerung = grund
        _schliesse(route, ABBRUCH_CODE)
        return False

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


def _hauptseite(anfrage: Request) -> bool:
    return anfrage.is_navigation_request() and anfrage.frame.parent_frame is None


def _gib_weiter(route: Route, antwort: APIResponse) -> None:
    """Reicht die Antwort durch, ohne Vorabladen in Kopf und Dokument.

    Entfernt Speculation Rules, ``<link rel=prerender|prefetch>`` und solche Einträge
    der Kopfzeile ``Link``.
    """
    kopf = antwort.headers
    html = "html" in kopf.get("content-type", "").lower()
    koerper = antwort.body() if html else b""
    ohne = _VORABLADEN.sub(b"", koerper)
    link = kopf.get(LINKKOPF)
    links = (
        [] if link is None else [e for e in link.split(",") if not _VORAB_REL.search(e)]
    )
    link_neu = None if link is None else ",".join(links)
    if SPEKULATIONSKOPF not in kopf and ohne == koerper and link == link_neu:
        route.fulfill(response=antwort)
        return
    log.info("Klick-Crawler: Vorabladen aus %s entfernt", antwort.url)
    neu = {k: v for k, v in kopf.items() if k not in NEU_BERECHNET}
    if links:
        neu[LINKKOPF] = ",".join(links)
    route.fulfill(response=antwort, headers=neu, body=ohne if html else antwort.body())


def _schliesse(route: Route, code: str) -> None:
    try:
        route.abort(code)
    except PlaywrightFehler as fehler:
        log.info("Klick-Crawler: Anfrage nicht abgebrochen: %s", kurz(fehler))
