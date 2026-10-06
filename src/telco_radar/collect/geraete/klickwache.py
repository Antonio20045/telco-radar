"""Wache des Klick-Crawlers: wartet auf Antworten und Ruhe und hört auf das Tor.

``Wache`` gehört zu einem Lauf (``klickcrawler``) und wartet in Takten von
``klicktor.WARTE_TAKT_MS``: Zeit, in der das Tor den Crawl-delay abwartet, zählt so
nicht gegen die Frist. In jedem Takt fragt sie das Tor: zeigte eine Hauptseite
Bot-Schutz (``Tor.stoerung``) oder leitet die Hauptseite nach dem Öffnen um, endet der
Lauf sofort als gestört (CLAUDE.md Regel 4). Eine Antwort gehört nur zu dem Klick, nach
dem ihre Anfrage hinausging (``klickmitschnitt``); sieht sie nach Bot-Schutz aus
(``klicklauf.bot_schutz``, auch HTML statt JSON), ist der Lauf gestört. Bleibt sie über
die Frist offen, heißt die Kombination ``nicht_erfasst`` (``ausstehend``), und vor dem
nächsten Klick wie am Ende des Laufs wartet die Wache sie ab oder bricht den Lauf als
gestört ab. Ruhe heißt: keine Anfrage der Seite läuft, und zwei Lesungen im Abstand
``RUHE_MS`` zeigen dieselben Knöpfe und keine neue Anfrage.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import TYPE_CHECKING

from playwright.sync_api import Error as PlaywrightFehler

from .klicklauf import LAUF_GESPERRT, LAUF_GESTOERT, Klicklauf, bot_schutz
from .klickmitschnitt import Mitschnitt
from .klicktor import WARTE_TAKT_MS, Tor, kurz

if TYPE_CHECKING:
    from playwright.sync_api import Page, Response

    from .klickkarte import Klickkarte
    from .klickoptionen import Option

log = logging.getLogger(__name__)

RUHE_MS = 500
MINDESTE_RUHELESUNGEN = 3

Marke = tuple[int, int, int]


class Abbruch(Exception):
    """Beendet einen Lauf mit Status und Grund."""

    def __init__(self, status: str, grund: str) -> None:
        super().__init__(grund)
        self.status = status
        self.grund = grund


class Wache:
    """Warten eines Laufs: Tor, Mitschnitt, aktuelle und ausstehende Antwort."""

    def __init__(
        self, seite: Page, karte: Klickkarte, tor: Tor, lauf: Klicklauf, frist_ms: int
    ) -> None:
        self.seite, self.tor, self.lauf = seite, tor, lauf
        self.passt = karte.antwort.passt
        self.frist_ms = frist_ms
        self.mitschnitt = Mitschnitt(self.passt)
        self.mitschnitt.binde(seite)
        self.antwort: Response | None = None
        self.ausstehend: str | None = None
        self.geoeffnet = False

    def pruefe_tor(self) -> None:
        """Bricht ab, wenn die Hauptseite Bot-Schutz zeigte oder im Lauf umleitet."""
        if self.tor.stoerung is not None:
            raise Abbruch(LAUF_GESTOERT, self.tor.stoerung)
        if self.geoeffnet and self.tor.umleitung is not None:
            grund = f"Hauptseite im Lauf umgeleitet ({self.tor.umleitung})"
            raise Abbruch(LAUF_GESTOERT, grund)

    def warte(self, bedingung: Callable[[], bool], frist_ms: int | None = None) -> bool:
        """Wartet in Takten, bis ``bedingung`` gilt; fragt in jedem Takt das Tor."""
        takte = (self.frist_ms if frist_ms is None else frist_ms) // WARTE_TAKT_MS
        for _ in range(max(1, takte)):
            self.pruefe_tor()
            if bedingung():
                return True
            self.seite.wait_for_timeout(WARTE_TAKT_MS)
        self.pruefe_tor()
        return bedingung()

    def marke(self) -> Marke:
        """Stand von Mitschnitt, ``verworfen`` und ``gescheitert`` vor einem Schritt."""
        return (
            self.mitschnitt.stand(),
            len(self.lauf.verworfen),
            len(self.lauf.gescheitert),
        )

    def nimm_antwort(self, marke: Marke) -> None:
        """Wartet auf die Antwort seit ``marke`` und prüft sie, bevor sie gilt."""
        seit = marke[0]
        self.ausstehend = None
        antwort = None
        if self.warte(lambda: self.mitschnitt.fertig_seit(seit)):
            antwort = self.mitschnitt.letzte_seit(seit)
        elif self.mitschnitt.offen_seit(seit):
            self.ausstehend = f"Preisantwort nach {self.frist_ms} ms noch offen"
        if antwort is None:
            self._ohne_antwort(marke)
        else:
            self._pruefe(antwort)
        self.antwort = antwort

    def warte_offen(self) -> None:
        """Wartet offene Preisanfragen ab; bleibt eine offen, ist der Lauf gestört."""
        if not self.warte(lambda: not self.mitschnitt.offen):
            grund = f"Preisantwort nach weiteren {self.frist_ms} ms noch offen"
            raise Abbruch(LAUF_GESTOERT, grund)

    def in_ruhe(self, lies: Callable[[], list[Option]]) -> list[Option] | None:
        """Die Knöpfe, sobald die Seite ruht; ``None`` nach Ablauf der Frist."""
        vorher: tuple[int, list[Option]] | None = None
        for _ in range(max(MINDESTE_RUHELESUNGEN, self.frist_ms // RUHE_MS)):
            self.pruefe_tor()
            gestartet = self.mitschnitt.ruhe()
            jetzt = None if gestartet is None else (gestartet, lies())
            if jetzt is not None and jetzt == vorher:
                return jetzt[1]
            vorher = jetzt
            self.seite.wait_for_timeout(RUHE_MS)
        return None

    def _ohne_antwort(self, marke: Marke) -> None:
        verworfen = self.lauf.verworfen[marke[1] :]
        gesperrt = [v for v in verworfen if self.passt(v.anfrage)]
        if gesperrt:
            raise Abbruch(LAUF_GESPERRT, f"Preisantwort {gesperrt[0].grund}")
        gescheitert = self.lauf.gescheitert[marke[2] :]
        ohne = [g for g in gescheitert if self.passt(g.anfrage)]
        if ohne:
            raise Abbruch(LAUF_GESTOERT, f"Preisantwort gescheitert: {ohne[0].grund}")

    def _pruefe(self, antwort: Response) -> None:
        typ = antwort.headers.get("content-type", "")
        try:
            koerper = antwort.text()
        except PlaywrightFehler as fehler:
            log.info(
                "Klick-Crawler: Körper von %s fehlt: %s", antwort.url, kurz(fehler)
            )
            koerper = ""
        stoerung = bot_schutz(antwort.status, typ, koerper, json_erwartet=True)
        if stoerung is not None:
            raise Abbruch(LAUF_GESTOERT, f"Preisantwort: {stoerung}")
