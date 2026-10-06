"""Browserkontext des Klick-Crawlers: Nebenwege zu, Antworten mitschneiden, schließen.

``oeffne_kontext`` legt je Lauf einen eigenen Kontext an: ohne Service Worker, jede
Anfrage und jeder WebSocket am ``klicktor.Tor``, ein Init-Skript entfernt nachgeladene
Speculation Rules, bevor der Browser sie liest, und ``sperre_beiwege`` bricht über das
DevTools-Protokoll ab, was der Browser an ``route`` vorbei anfragt (Favicons, Art
„Other“; nur Chromium). ``schliesse`` verlässt die Seite und schließt den Kontext.

``Mitschnitt`` merkt die Anfragen, die zum Antwortmuster der Karte passen, und ihre
Antworten; so gehört eine Antwort nur zu dem Klick, nach dem ihre Anfrage hinausging.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import TYPE_CHECKING

from playwright.sync_api import Error as PlaywrightFehler

from .klicktor import Tor, kurz

if TYPE_CHECKING:
    from playwright.sync_api import (
        Browser,
        BrowserContext,
        Page,
        Request,
        Response,
        ViewportSize,
    )


log = logging.getLogger(__name__)

BEIWEG_ARTEN = ("Other",)
BEIWEG_GRUND = "BlockedByClient"
LEER = "about:blank"
OHNE_SPEKULATION_JS = """(() => {
  const istRegel = (k) => k instanceof HTMLScriptElement
    && k.type.trim().toLowerCase() === "speculationrules";
  const entferne = (k) => {
    if (istRegel(k)) { k.remove(); return; }
    if (!k.querySelectorAll) return;
    for (const s of k.querySelectorAll("script")) if (istRegel(s)) s.remove();
  };
  new MutationObserver((liste) => {
    for (const m of liste) {
      if (istRegel(m.target)) m.target.remove();
      for (const k of m.addedNodes) entferne(k);
    }
  }).observe(document, {childList: true, subtree: true, attributes: true,
                        attributeFilter: ["type"]});
})();"""


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


def oeffne_kontext(
    browser: Browser, tor: Tor, fenster: ViewportSize
) -> tuple[BrowserContext, Page]:
    """Eigener Kontext ohne Service Worker; jede Anfrage und jeder WebSocket am Tor."""
    kontext = browser.new_context(service_workers="block", viewport=fenster)
    try:
        kontext.add_init_script(script=OHNE_SPEKULATION_JS)
        kontext.route_web_socket("**/*", tor.websocket)
        kontext.route("**/*", tor)
        seite = kontext.new_page()
        sperre_beiwege(kontext, seite)
    except PlaywrightFehler:
        schliesse(kontext, None)
        raise
    tor.warte = seite.wait_for_timeout
    return kontext, seite


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


def _unter(anfrage: Request, anfragen: list[Request]) -> bool:
    return any(anfrage is a for a in anfragen)
