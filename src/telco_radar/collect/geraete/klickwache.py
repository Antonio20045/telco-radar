"""Wache des Klick-Crawlers: wartet auf Antworten und Ruhe und hört auf das Tor.

``Wache`` gehört zu einem Lauf (``klickcrawler``) und wartet in Takten von
``klicktor.WARTE_TAKT_MS``: Zeit, in der das Tor den Crawl-delay abwartet, zählt so
nicht gegen die Frist, die Abrufzeit aber schon; das Laden der Hauptseite misst darum
``klickladung`` am Fortschritt. In jedem Takt fragt sie das Tor: zeigte eine Hauptseite
Bot-Schutz (``Tor.stoerung``) oder leitet die Hauptseite nach dem Öffnen um, endet der
Lauf sofort als gestört (CLAUDE.md Regel 4). Dasselbe gilt, wenn irgendeine andere
Antwort der eigenen Website nach Bot-Schutz aussieht (``klickspur.status_verdacht``:
HTTP 202 auf jede Anfrage, Telekom; 403 und 429 auf Daten- und Dokumentanfragen); die
Wache setzt dann ``Tor.stoerung``, sodass keine weitere Anfrage hinausgeht. Eine Antwort
gehört nur zu dem Klick, nach dem ihre Anfrage hinausging (``klickmitschnitt``); sieht
sie nach Bot-Schutz aus (``klicklauf.bot_schutz``, auch HTML statt JSON), ist der Lauf
gestört. Bleibt sie über die Frist offen, heißt die Kombination ``nicht_erfasst``
(``ausstehend``), und vor dem nächsten Klick wie am Ende des Laufs wartet die Wache sie
ab oder bricht den Lauf als gestört ab. Ruhe heißt: keine Anfrage der Seite läuft, und
zwei Lesungen im Abstand ``RUHE_MS`` zeigen dieselben Knöpfe und keine neue Anfrage.
Ließ das Tor eine JavaScript-Prüfung in den Browser (``klicksperre``), zählt ihre 202
nicht als Verdacht, und ``lade`` wartet höchstens ``PRUEFUNG_FRIST_MS``, bis die Seite
danach neu geladen ist; sonst ist der Lauf gestört. Mitgeschnitten wird jede Antwort,
die zu einer Quelle der Karte passt; erwartet keine Quelle eine Antwort je Klick
(congstar, Vodafone, 1&1), wartet die Wache nach einem Klick nur auf Ruhe.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import TYPE_CHECKING

from playwright.sync_api import Error as PlaywrightFehler

from .klickladung import Ladung
from .klicklauf import (
    CHALLENGE_STATUS,
    LAUF_GESPERRT,
    LAUF_GESTOERT,
    STOERUNG_ZEIT,
    Klicklauf,
    antworttext,
    bot_schutz,
)
from .klickmitschnitt import Mitschnitt
from .klickspur import ohne_geheimnisse, status_verdacht
from .klicktor import SEITEN_FRIST_MS, WARTE_TAKT_MS, Tor, kurz

if TYPE_CHECKING:
    from playwright.sync_api import Frame, Page, Response

    from .klickkarte import Klickkarte
    from .klickoptionen import Option

log = logging.getLogger(__name__)

RUHE_MS = 500
MINDESTE_RUHELESUNGEN = 3
PRUEFUNG_FRIST_MS = 2 * SEITEN_FRIST_MS
GRUND_PRUEFUNG = (
    f"Abruf gestört (JavaScript-Prüfung nach {PRUEFUNG_FRIST_MS} ms nicht bestanden,"
    f" HTTP {CHALLENGE_STATUS})"
)

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
        self.seite, self.tor, self.lauf, self.karte = seite, tor, lauf, karte
        self.passt: Callable[[str], bool] = lambda url: any(
            q.passt(url) for q in self.karte.lesequellen
        )
        self.frist_ms = frist_ms
        self.seit = 0
        self.geladen = 0
        self.mitschnitt = Mitschnitt(self.passt)
        self.mitschnitt.binde(seite)
        seite.on("response", self._beobachte)
        self.navigationen = 0
        seite.on("framenavigated", self._navigiert)
        self.ladung = Ladung(seite)
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

    def lade(self, ziel: str) -> None:
        """Öffnet ``ziel``; die Frist bis zur Antwort trägt den Crawl-delay mit.

        Antwort und Ausstehendes der vorigen Seite gelten danach nicht mehr. Bis
        ``load`` wartet ``klickladung`` am Fortschritt; lädt die Seite nicht, ist sie
        gestört mit ``STOERUNG_ZEIT``, und ``lauf.ladung`` nennt die Umstände.
        """
        self.tor.umleitung = None
        self.ladung.beginne()
        self.antwort, self.ausstehend = None, None
        _, verworfen, gescheitert = self.marke()
        frist = SEITEN_FRIST_MS + round(1000 * self.tor.schleuse.abstand(ziel))
        try:
            self.seite.goto(ziel, wait_until="commit", timeout=frist)
        except PlaywrightFehler as fehler:
            self.lauf.http_status = self.tor.haupt_status
            self.pruefe_tor()
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
        self.lauf.http_status = self.tor.haupt_status
        if self.tor.umleitung is not None:
            return
        self._warte_pruefung()
        geladen = self.ladung.warte(self.pruefe_tor)
        abstand = self.tor.schleuse.abstand(ziel)
        self.lauf.ladung = self.ladung.diagnose(geladen, abstand)
        self.pruefe_tor()
        if not geladen:
            self.lauf.stoerung = STOERUNG_ZEIT
            raise Abbruch(LAUF_GESTOERT, self.ladung.grund())

    def _warte_pruefung(self) -> None:
        """Wartet nach einer JavaScript-Prüfung, bis die Seite danach geladen hat."""
        if not self.tor.pruefung.offen:
            return
        stand = self.navigationen
        if not self.warte(
            lambda: not self.tor.pruefung.offen and self.navigationen > stand,
            PRUEFUNG_FRIST_MS,
        ):
            raise Abbruch(LAUF_GESTOERT, GRUND_PRUEFUNG)
        self.lauf.http_status = self.tor.haupt_status
        self.ladung.beginne()

    def _navigiert(self, rahmen: Frame) -> None:
        if rahmen.parent_frame is None:
            self.navigationen += 1

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
        seit = self.seit = marke[0]
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

    def nimm_angefragte(self, marke: Marke) -> None:
        """Nimmt die Antwort seit ``marke`` nur, wenn seitdem eine Preisanfrage ging."""
        if self.mitschnitt.stand() > marke[0]:
            self.nimm_antwort(marke)

    def warte_ruhe(self) -> None:
        """Wartet, bis keine Anfrage läuft und keine neue kommt, höchstens die Frist."""
        self.in_ruhe(lambda: [])

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

    def _beobachte(self, antwort: Response) -> None:
        """Setzt die Störung, wenn eine Antwort der eigenen Website Bot-Schutz zeigt.

        Auch jede Preisantwort, sobald sie ankommt, ob je Klick oder beim Laden;
        ``_pruefe`` prüft die genommene zusätzlich am Körper, die Hauptseite das Tor.
        """
        if self.tor.stoerung is not None:
            return
        if antwort.status == CHALLENGE_STATUS and antwort.url == self.tor.pruefung.url:
            return
        art = antwort.request.resource_type
        url = ohne_geheimnisse(antwort.url)
        grund = status_verdacht(url, antwort.status, art, self.lauf.adresse)
        if grund is not None:
            log.warning("Klick-Crawler: %s; Lauf endet", grund)
            self.tor.stoerung = grund

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
            koerper = antworttext(antwort.body(), typ)
        except PlaywrightFehler as fehler:
            log.info(
                "Klick-Crawler: Körper von %s fehlt: %s", antwort.url, kurz(fehler)
            )
            koerper = ""
        stoerung = bot_schutz(antwort.status, typ, koerper, json_erwartet=True)
        if stoerung is not None:
            raise Abbruch(LAUF_GESTOERT, f"Preisantwort: {stoerung}")
