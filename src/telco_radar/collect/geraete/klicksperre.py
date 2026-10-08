"""Art der Sperre einer Hauptseite und die eine JavaScript-Prüfung je Seite.

Entscheidung Antonio 08.10.2026: Eine reine JavaScript-Prüfung eines Bot-Schutzes
(HTTP 202 mit Kopfzeile ``WAF_KOPF: challenge``, AWS WAF bei Telekom) darf der
Browser so durchlaufen, wie jeder Browser es tut: mit der ehrlichen Kennung aus
``geraete_quellen.yaml``, ohne Tarnung, ohne Captcha-Löser; jede Anfrage ihres
Skripts geht durch das Tor (``klicktor``) mit robots.txt und Abstand. Ein Captcha
(Kopfzeile oder ``CAPTCHA_MUSTER`` im Körper), jede andere Sperre und jede zweite
Prüfung derselben Seite beenden den Lauf wie bisher (``klicklauf.bot_schutz``).

``sperrart`` nennt die Art (``SPERRE_*``), ``Pruefung`` hält sie je Seite in
``Klicklauf.sperre`` fest; kommt die Seite nach der Prüfung ohne Sperre, heißt sie
``SPERRE_BESTANDEN``. Kein Netz, kein Browser.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Mapping
from typing import TYPE_CHECKING

from .klicklauf import CHALLENGE_STATUS, Klicklauf, bot_schutz

if TYPE_CHECKING:
    from playwright.sync_api import APIResponse

log = logging.getLogger(__name__)

WAF_KOPF = "x-amzn-waf-action"
SPERRE_CHALLENGE = "challenge"
SPERRE_BESTANDEN = "challenge_bestanden"
SPERRE_CAPTCHA = "captcha"
SPERRE_UNBEKANNT = "unbekannt"
CAPTCHA_MUSTER = re.compile(
    r"/captcha\.js|captcha-container|awswafcaptcha"
    r"|g-recaptcha|recaptcha/api|hcaptcha\.com|captcha-delivery\.com|px-captcha",
    re.I,
)


def sperrart(status: int | None, kopf: Mapping[str, str], koerper: str) -> str | None:
    """Art der Sperre einer Hauptseite, ``None`` ohne Bot-Schutz (``bot_schutz``).

    ``captcha`` (Kopfzeile oder ``CAPTCHA_MUSTER`` im Körper) geht vor
    ``challenge`` (Kopfzeile ``WAF_KOPF: challenge`` unter HTTP 202); sonst
    ``unbekannt``. Eine offene Seite darf das Captcha-Modul laden (Telekom).
    """
    if bot_schutz(status, "", koerper) is None:
        return None
    aktion = {k.lower(): v for k, v in kopf.items()}.get(WAF_KOPF, "").strip().lower()
    if aktion == SPERRE_CAPTCHA or CAPTCHA_MUSTER.search(koerper):
        return SPERRE_CAPTCHA
    if status == CHALLENGE_STATUS and aktion == SPERRE_CHALLENGE:
        return SPERRE_CHALLENGE
    return SPERRE_UNBEKANNT


class Pruefung:
    """Die eine JavaScript-Prüfung einer Seite: ``url`` der durchgelassenen,
    ``offen`` bis die Hauptseite danach ohne Sperre kam."""

    def __init__(self, lauf: Klicklauf) -> None:
        self.lauf = lauf
        self.url: str | None = None
        self.offen = False

    def laesst_durch(self, antwort: APIResponse, text: str, grund: str | None) -> bool:
        """Wahr, wenn die Hauptseite in den Browser darf: ohne Bot-Schutz (``grund``
        ist ``None``) oder als erste JavaScript-Prüfung; setzt ``Klicklauf.sperre``."""
        if grund is None:
            if self.offen:
                self.offen, self.lauf.sperre = False, SPERRE_BESTANDEN
            return True
        self.lauf.sperre = sperrart(antwort.status, antwort.headers, text)
        if self.lauf.sperre != SPERRE_CHALLENGE or self.url is not None:
            return False
        log.info("Klick-Crawler: %s, JavaScript-Prüfung im Browser", antwort.url)
        self.url, self.offen = antwort.url, True
        return True
