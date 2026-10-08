"""Laden der Hauptseite: Warten am Fortschritt statt an fester Frist, mit Diagnose.

Das Tor lässt je Host nur eine Anfrage hinaus und wartet davor den Crawl-delay ab
(``klicktor``); die Wache zählt ihre Takte auch, während das Tor eine Antwort holt. Eine
feste Frist bis ``load`` misst so die Summe der Abrufzeiten aller Anfragen desselben
Hosts. Vodafone stellt beim Laden rund 95 Anfragen an www.vodafone.de; im Tageslauf vom
08.10.2026 (Actions-Lauf 37740022815, iphone-17-pro.html, HTTP 200) standen nach
30 000 ms noch rund 43 davon im Tor, darunter das Skript der Geräteseite.

``Ladung`` zählt darum die Anfragen der Seite und ihre Enden je Host. Das Warten auf
``document.readyState === 'complete'`` (``WARTET_AUF``) endet erst nach
``SEITEN_FRIST_MS`` ohne eine neue beendete Anfrage oder nach ``LADE_HOECHSTENS_MS``
Takten; dann ist die Seite gestört mit ``klicklauf.STOERUNG_ZEIT``, kein Bot-Schutz
(CLAUDE.md Regel 10). ``diagnose`` hält für das Ergebnis fest, worauf und wie lange
gewartet wurde und welche Hosts noch offene Anfragen hatten: nur Hostnamen und Zahlen,
keine Adresse, kein Seitentext.
"""

from __future__ import annotations

import time
from collections import Counter
from collections.abc import Callable
from typing import TYPE_CHECKING
from urllib.parse import urlsplit

from playwright.sync_api import Error as PlaywrightFehler

from .klicktor import SEITEN_FRIST_MS, WARTE_TAKT_MS

if TYPE_CHECKING:
    from playwright.sync_api import Page, Request

WARTET_AUF = "load"
LADE_HOECHSTENS_MS = 5 * SEITEN_FRIST_MS
OFFENE_HOSTS = 3
_GELADEN_JS = "() => document.readyState === 'complete'"
_ZUSTAND_JS = "() => document.readyState"


class Ladung:
    """Anfragen und beendete Anfragen der Seite je Host seit dem letzten ``beginne``."""

    def __init__(self, seite: Page) -> None:
        self.seite = seite
        self.gestellt: Counter[str] = Counter()
        self.beendet: Counter[str] = Counter()
        self.takte = 0
        self.ohne = 0
        self.beginn = time.monotonic()
        seite.on("request", self._gestellt)
        seite.on("requestfinished", self._beendet)
        seite.on("requestfailed", self._beendet)

    def beginne(self) -> None:
        """Ein neues Laden: Zähler und Takte auf null."""
        self.gestellt.clear()
        self.beendet.clear()
        self.takte = self.ohne = 0
        self.beginn = time.monotonic()

    def warte(self, pruefe: Callable[[], None]) -> bool:
        """Wartet in Takten auf ``load``; ``pruefe`` fragt in jedem Takt das Tor."""
        stand = self.beendet.total()
        while (
            self.ohne * WARTE_TAKT_MS < SEITEN_FRIST_MS
            and self.takte * WARTE_TAKT_MS < LADE_HOECHSTENS_MS
        ):
            pruefe()
            if self._geladen():
                return True
            self.seite.wait_for_timeout(WARTE_TAKT_MS)
            self.takte += 1
            jetzt = self.beendet.total()
            self.ohne = 0 if jetzt != stand else self.ohne + 1
            stand = jetzt
        pruefe()
        return self._geladen()

    def grund(self) -> str:
        """Der Grund der Zeitüberschreitung mit beiden Fristen."""
        return (
            f"Seite nach {self.takte * WARTE_TAKT_MS} ms nicht geladen "
            f"({self.ohne * WARTE_TAKT_MS} ms ohne neue Antwort)"
        )

    def diagnose(self, geladen: bool, abstand_s: float) -> dict[str, object]:
        """Worauf, wie lange gewartet wurde; offene Anfragen der ersten drei Hosts."""
        offen = self.gestellt - self.beendet
        return {
            "wartet_auf": WARTET_AUF,
            "geladen": geladen,
            "dokument": self._zustand(),
            "takte_ms": self.takte * WARTE_TAKT_MS,
            "ohne_antwort_ms": self.ohne * WARTE_TAKT_MS,
            "sekunden": round(time.monotonic() - self.beginn, 1),
            "anfragen": self.gestellt.total(),
            "beendet": self.beendet.total(),
            "offen": dict(offen.most_common(OFFENE_HOSTS)),
            "abstand_s": abstand_s,
        }

    def _geladen(self) -> bool:
        try:
            return self.seite.evaluate(_GELADEN_JS) is True
        except PlaywrightFehler:
            return False

    def _zustand(self) -> str | None:
        try:
            zustand = self.seite.evaluate(_ZUSTAND_JS)
        except PlaywrightFehler:
            return None
        return zustand if isinstance(zustand, str) else None

    def _gestellt(self, anfrage: Request) -> None:
        self.gestellt[_host(anfrage.url)] += 1

    def _beendet(self, anfrage: Request) -> None:
        self.beendet[_host(anfrage.url)] += 1


def _host(url: str) -> str:
    teile = urlsplit(url)
    return teile.hostname or teile.scheme
