"""Browserkontext des Klick-Crawlers: Nebenwege und Vorabladen zu, sauber schließen.

``oeffne_sitzung`` legt je Lauf einen eigenen Kontext an: ohne Service Worker, jede
Anfrage und jeder WebSocket am ``klicktor.Tor``. Was der Browser an ``route`` vorbei
anfragt, geht nicht hinaus (nur Chromium, über das DevTools-Protokoll):
``sperre_beiwege`` bricht Anfragen der Art „Other“ ab (Favicons), und
``sperre_vorabladen`` bricht auf Browserebene jede Vorab-Anfrage ab (Kopfzeile
``Sec-Purpose`` mit prefetch oder prerender, etwa ``<link rel=prerender>``), solange der
Lauf dauert, auch in anderen Kontexten desselben Browsers. Speculation Rules holt
Chromium an beiden vorbei; die entfernt das Tor aus jeder Antwort und ``OHNE_VORAB_JS``
aus nachgeladenen Elementen, auch in Shadow Roots, bevor der Browser sie liest.
``schliesse`` verlässt die Seite, schließt den Kontext und gibt das Vorabladen frei.
HAR-Belege in ``wiedergabe`` beantworten ihre Anfragen ohne Netz und vor dem Tor; was
sie nicht kennen, geht an das Tor.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from playwright.sync_api import Error as PlaywrightFehler

from .klicktor import Tor, kurz

if TYPE_CHECKING:
    from playwright.sync_api import (
        Browser,
        BrowserContext,
        CDPSession,
        Page,
        ViewportSize,
    )


log = logging.getLogger(__name__)

BEIWEG_ARTEN = ("Other",)
BEIWEG_GRUND = "BlockedByClient"
LEER = "about:blank"
VORAB_ZWECK = re.compile(r"prefetch|prerender", re.I)
OHNE_VORAB_JS = """(() => {
  const vorab = /\\b(?:prerender|prefetch)\\b/i;
  const weg = (k) => (k instanceof HTMLScriptElement
      && k.type.trim().toLowerCase() === "speculationrules")
    || (k instanceof HTMLLinkElement && vorab.test(k.rel));
  const beobachter = new MutationObserver((liste) => {
    for (const m of liste) {
      pruefe(m.target, false);
      for (const k of m.addedNodes) pruefe(k, true);
    }
  });
  const beobachte = (wurzel) => beobachter.observe(wurzel, {childList: true,
    subtree: true, attributes: true, attributeFilter: ["type", "rel"]});
  const pruefe = (k, tief) => {
    if (weg(k)) { k.remove(); return; }
    if (!tief || !k.querySelectorAll) return;
    for (const e of k.querySelectorAll("*")) {
      if (weg(e)) e.remove();
      else if (e.shadowRoot) { beobachte(e.shadowRoot); pruefe(e.shadowRoot, true); }
    }
    if (k.shadowRoot) { beobachte(k.shadowRoot); pruefe(k.shadowRoot, true); }
  };
  const haenge = Element.prototype.attachShadow;
  Element.prototype.attachShadow = function (...art) {
    const wurzel = haenge.apply(this, art);
    beobachte(wurzel);
    return wurzel;
  };
  beobachte(document);
})();"""


@dataclass(frozen=True)
class Sitzung:
    """Kontext, Seite und Vorab-Sperre eines Laufs."""

    kontext: BrowserContext
    seite: Page
    wache: CDPSession


def oeffne_sitzung(
    browser: Browser,
    tor: Tor,
    fenster: ViewportSize,
    kennung: str | None = None,
    *,
    wiedergabe: tuple[Path, ...] = (),
) -> Sitzung:
    """Eigener Kontext ohne Service Worker und ohne Vorabladen, alles am Tor.

    ``kennung`` ist der User-Agent aus ``geraete_quellen.yaml``, sonst der des Browsers;
    eine andere Kopfzeile setzt der Kontext nicht. Die HAR-Dateien in ``wiedergabe``
    stehen vor dem Tor.
    """
    wache = sperre_vorabladen(browser)
    kontext: BrowserContext | None = None
    try:
        kontext = browser.new_context(
            service_workers="block", viewport=fenster, user_agent=kennung
        )
        kontext.add_init_script(script=OHNE_VORAB_JS)
        kontext.route_web_socket("**/*", tor.websocket)
        kontext.route("**/*", tor)
        for har in wiedergabe:
            kontext.route_from_har(har, not_found="fallback")
        seite = kontext.new_page()
        sperre_beiwege(kontext, seite)
    except PlaywrightFehler:
        _schliesse_kontext(kontext, None)
        _gib_frei(wache)
        raise
    tor.warte = seite.wait_for_timeout
    return Sitzung(kontext, seite, wache)


def schliesse(sitzung: Sitzung | None) -> None:
    """Schließt Seite und Kontext und gibt das Vorabladen frei; wirft nie."""
    if sitzung is not None:
        _schliesse_kontext(sitzung.kontext, sitzung.seite)
        _gib_frei(sitzung.wache)


def sperre_vorabladen(browser: Browser) -> CDPSession:
    """Bricht auf Browserebene jede Anfrage mit Vorab-Zweck ab; andere gehen weiter."""
    wache = browser.new_browser_cdp_session()

    def pruefe(ereignis: dict) -> None:
        kopf = {k.lower(): v for k, v in ereignis["request"]["headers"].items()}
        zweck = kopf.get("sec-purpose", kopf.get("purpose", ""))
        frage = {"requestId": ereignis["requestId"]}
        befehl = "Fetch.continueRequest"
        if VORAB_ZWECK.search(zweck):
            log.info(
                "Klick-Crawler: Vorabladen %s abgebrochen", ereignis["request"]["url"]
            )
            befehl, frage["errorReason"] = "Fetch.failRequest", BEIWEG_GRUND
        try:
            wache.send(befehl, frage)
        except PlaywrightFehler as fehler:
            log.info("Klick-Crawler: Anfrage nicht weitergegeben: %s", kurz(fehler))

    wache.on("Fetch.requestPaused", pruefe)
    wache.send("Fetch.enable", {"patterns": [{"urlPattern": "*"}]})
    return wache


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


def _schliesse_kontext(kontext: BrowserContext | None, seite: Page | None) -> None:
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


def _gib_frei(wache: CDPSession) -> None:
    try:
        wache.send("Fetch.disable")
        wache.detach()
    except PlaywrightFehler as fehler:
        log.info("Klick-Crawler: Vorab-Sperre nicht gelöst: %s", kurz(fehler))
