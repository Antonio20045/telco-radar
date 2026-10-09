"""Klick-Tageslauf je Anbieter (Datenkonzept Geräteradar §8 „Betrieb“).

Ein Job je Anbieter (Matrix im eigenen Workflow ``klick.yml``) arbeitet die Klick-Karte
``config/klickkarten/<schluessel>.yaml`` über die Produktseiten aus
``config/klick_tageslauf.yaml`` ab (Format und Prüfung wie ``klickziele``). Jede Seite
läuft durch den Klick-Crawler (``klickcrawler.klicke_durch``) mit demselben Tor wie die
Erkundung: robots.txt samt Crawl-delay und Visit-time je Anfrage, eigener Abstand des
Anbieters, User-Agent aus ``geraete_quellen.yaml``, keine Tarnung. Endet eine Seite
gestört (Bot-Schutz, Challenge, Kanarienwert, Strukturbruch), geht für den Anbieter
keine Anfrage mehr hinaus (CLAUDE.md Regel 4); die übrigen Seiten heißen
``nicht_besucht`` mit Grund. Lud eine Seite nur nicht (``klicklauf.STOERUNG_ZEIT``,
kein Bot-Schutz, CLAUDE.md Regel 10), folgt die nächste Seite unter derselben
Hostschleuse samt Crawl-delay; nach ``HOECHSTE_ZEITUEBERSCHREITUNGEN`` solchen Seiten
endet er. Ebenso endet der Lauf, sobald die Parallellauf-Prüfung (``klickparallel``,
vor jeder Seite) einen anderen Lauf auf denselben Hosts meldet.

Zeitbudget (CLAUDE.md Regel 8): ``budget_ende`` rechnet gegen die Restzeit des Jobs,
``job_frist_s`` (Vorgabe ``JOB_FRIST_S``, gleich ``timeout-minutes`` des Matrix-Jobs)
minus der schon verstrichenen Jobzeit minus ``RESERVE_S`` für Schreiben und Hochladen.
Eine Seite beginnt nur mit mindestens ``MINDESTZEIT_SEITE_S`` Rest und bekommt höchstens
``ZEIT_JE_SEITE_S``; danach lässt die Fristschleuse keine Anfrage mehr hinaus und der
Crawler nennt den Rest ``nicht besucht``. Zwischen zwei besuchten Seiten wartet der
Lauf ``Erkundungsziel.seitenabstand_sekunden`` (ruhiges Tempo, keine Anpassung an
eine Sperre); vor der ersten und nach dem Ende wartet er nicht. Die Übersichten des
Anbieters (``Erkundungsziel.uebersichten``, ``klickuebersicht``) liest der Lauf vor den
Produktseiten, unter denselben Grenzen, Abständen und Stopps; sie stehen unter
``uebersichten`` in der Ergebnisdatei und zählen für den Laufstatus mit. Eine Übersicht
samt Folgeseiten hat eine Grenze; jede gestörte Folgeseite hält den Anbieter an.
Telekom (Pitch 4, Schnitt 3): 5 Tarife × ~3 Seiten × ~100 s plus 14 × 60 s Abstand
≈ 39 min von 67 min Budget; der Rest reicht für etwa 4 der 7 Produktseiten (je ~280 s),
die übrigen bleiben ``nicht besucht`` und kommen in der Rotation am nächsten Tag.

Rotation: Einheit ist die Produktseite, denn der Crawler klickt alle Varianten einer
Seite in einem Gang. Zuerst kommen nie gelesene Seiten, dann die am längsten nicht
gelesenen (Lesestand, ``klickergebnis.lies_stand``); bei Gleichstand gilt die
Reihenfolge der Konfiguration. Seiten, die heute nicht ganz gelesen wurden (eine an der
Zeitgrenze abgeschnittene zählt nicht, ``klickergebnis.ganz_gelesen``) und deren
letzte Lesung ``LESEFRIST_TAGE`` oder älter ist, stehen unter ``ueberfaellig``: jede
Seite soll jeden Tag gelesen sein.
Kein LLM.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable, Mapping
from datetime import date, datetime
from typing import TYPE_CHECKING

from .basis import GeraeteAbrufFehler
from .klickcrawler import klicke_durch
from .klickergebnis import (
    FORMAT,
    FRISCHEGRENZE_TAGE,
    LESEFRIST_TAGE,
    SEITE_NICHT_BESUCHT,
    ganz_gelesen,
    laufstatus,
    nicht_besucht,
    seite_als_daten,
)
from .klicklauf import ERFASST, LAUF_GESTOERT, STOERUNG_ZEIT, Klicklauf
from .klickparallel import Laufpruefung
from .klickseite import GRUND_FRIST, Fristschleuse, beobachte
from .klickspur import ohne_geheimnisse
from .klicktor import Hostschleuse
from .klickuebersicht import lies_uebersicht
from .robots import RobotsWaechter

if TYPE_CHECKING:
    from playwright.sync_api import APIResponse, Browser, Request

    from .klickkarte import Klickkarte
    from .klickziele import Erkundungsziel, Seitenziel

log = logging.getLogger(__name__)

JOB_FRIST_S = 75 * 60
RESERVE_S = 8 * 60
MINDESTZEIT_SEITE_S = 3 * 60
ZEIT_JE_SEITE_S = 25 * 60
GRUND_BUDGET = "Zeitbudget des Jobs erschöpft"
GRUND_NACH_STOERUNG = "nach Störung keine weitere Anfrage (CLAUDE.md Regel 4)"
GRUND_PARALLEL = "verschoben"
HOECHSTE_ZEITUEBERSCHREITUNGEN = 2
GRUND_ZEITUEBERSCHREITUNGEN = "Seiten luden nicht"

Crawler = Callable[["Seitenziel", float], Klicklauf]
"""Liest eine Seite bis zur monotonen Grenze ``ende``; wirft nie."""
Uebersichtsleser = Callable[[str, float], dict]
"""Liest eine Übersicht bis zur Grenze ``ende`` (``klickuebersicht``); wirft nie."""


class _Gang:
    """Abstand, Zeitbudget, Parallellauf und Stopp über alle Seiten eines Anbieters."""

    def __init__(
        self,
        ziel: Erkundungsziel,
        ende: float,
        laeufe: Laufpruefung | None,
        uhr: Callable[[], float],
        schlafe: Callable[[float], None],
    ) -> None:
        self.ziel, self.ende, self.laeufe = ziel, ende, laeufe
        self.uhr, self.schlafe = uhr, schlafe
        self.stopp: str | None = None
        self.zeit = 0
        self.besucht = False

    def vor(self) -> str | None:
        """Wartet den Seitenabstand; gibt den Grund, wenn keine Seite mehr beginnt."""
        abstand = self.ziel.seitenabstand_sekunden
        if self.stopp is None and self.besucht and abstand > 0:
            self.schlafe(abstand)
        rest = self.ende - self.uhr()
        if self.stopp is None and rest < MINDESTZEIT_SEITE_S:
            self.stopp = f"{GRUND_BUDGET}: noch {max(0, round(rest))} s"
        if self.stopp is None and self.laeufe is not None:
            anderer = self.laeufe()
            self.stopp = None if anderer is None else f"{GRUND_PARALLEL}: {anderer}"
        return self.stopp

    def grenze(self) -> float:
        """Die Grenze der nächsten Seite; ab hier gilt sie als besucht."""
        self.besucht = True
        return min(self.ende, self.uhr() + ZEIT_JE_SEITE_S)

    def nach(self, status: str, stoerung: str | None, grund: str | None) -> None:
        """Nach Bot-Schutz oder zu vielen Zeitüberschreitungen geht nichts mehr."""
        if status == LAUF_GESTOERT and stoerung == STOERUNG_ZEIT:
            self.zeit += 1
            if self.zeit >= HOECHSTE_ZEITUEBERSCHREITUNGEN:
                self.stopp = f"{self.zeit} {GRUND_ZEITUEBERSCHREITUNGEN}: {grund}"
        elif status == LAUF_GESTOERT:
            self.stopp = f"{GRUND_NACH_STOERUNG}: {grund}"


def _uebersicht_nicht_besucht(adresse: str, grund: str) -> dict:
    return {
        "adresse": ohne_geheimnisse(adresse),
        "status": SEITE_NICHT_BESUCHT,
        "grund": grund,
        "saetze": [],
        "vollstaendig": False,
    }


def _als_seiten(uebersicht: dict) -> list[dict]:
    """Eine Übersicht in der Form, die ``laufstatus`` liest: jeder Satz erfasst,
    jede Folgeseite eine Seite ohne Kombination."""
    erfasst = [{"status": ERFASST} for _ in uebersicht.get("saetze") or []]
    folge = (uebersicht.get("seiten") or [])[1:]
    return [{**uebersicht, "kombinationen": erfasst}] + [
        {**s, "kombinationen": []} for s in folge
    ]


def budget_ende(job_frist_s: float, verstrichen_s: float, jetzt: float) -> float:
    """Monotone Grenze des Laufs: Restzeit des Jobs ohne ``RESERVE_S``."""
    return jetzt + job_frist_s - verstrichen_s - RESERVE_S


def reihenfolge(
    seiten: tuple[Seitenziel, ...], gelesen: Mapping[str, str]
) -> list[Seitenziel]:
    """Nie gelesene zuerst, dann nach dem ältesten Lesedatum; sonst Konfiguration.

    Der Lesestand kennt Adressen nur ohne Geheimnisse, wie die Ergebnisdatei.
    """
    return sorted(seiten, key=lambda s: gelesen.get(ohne_geheimnisse(s.adresse), ""))


def ueberfaellig(
    seiten: tuple[Seitenziel, ...],
    gelesen: Mapping[str, str],
    heute_gelesen: set[str],
    heute: str,
) -> list[str]:
    """Adressen ohne Geheimnisse, heute ungelesen und älter als die Lesefrist."""
    tag = date.fromisoformat(heute)
    adressen = [ohne_geheimnisse(s.adresse) for s in seiten]
    return [
        a
        for a in adressen
        if a not in heute_gelesen
        and (
            a not in gelesen
            or (tag - date.fromisoformat(gelesen[a])).days >= LESEFRIST_TAGE
        )
    ]


def fahre(
    ziel: Erkundungsziel,
    karte: Klickkarte,
    datei: str,
    crawle: Crawler,
    heute: str,
    ende: float,
    *,
    gelesen: Mapping[str, str],
    laeufe: Laufpruefung | None = None,
    uhr: Callable[[], float] = time.monotonic,
    schlafe: Callable[[float], None] = time.sleep,
    lies_uebersicht: Uebersichtsleser | None = None,
) -> dict:
    """Liest die Seiten eines Anbieters in Rotation; gibt die Ergebnisdatei zurück.

    ``laeufe`` ist die Parallellauf-Prüfung; ``None`` nur für Läufe ohne Actions.
    ``schlafe`` wartet den Seitenabstand ab. ``lies_uebersicht`` liest die Übersichten
    des Anbieters vor den Produktseiten, mit denselben Grenzen und Stopps.
    """
    start = uhr()
    seiten: list[dict] = []
    uebersichten: list[dict] = []
    gang = _Gang(ziel, ende, laeufe, uhr, schlafe)
    for adresse in ziel.uebersichten:
        if lies_uebersicht is None:
            break
        stopp = gang.vor()
        if stopp is not None:
            uebersichten.append(_uebersicht_nicht_besucht(adresse, stopp))
            continue
        ergebnis = lies_uebersicht(adresse, gang.grenze())
        uebersichten.append(ergebnis)
        for teil in ergebnis.get("seiten") or [ergebnis]:
            gang.nach(teil["status"], teil.get("stoerung"), teil["grund"])
    for seite in reihenfolge(ziel.seiten, gelesen):
        stopp = gang.vor()
        if stopp is not None:
            seiten.append(nicht_besucht(seite, stopp))
            continue
        lauf = crawle(seite, gang.grenze())
        seiten.append(seite_als_daten(seite, lauf))
        gang.nach(lauf.status, lauf.stoerung, lauf.grund)
    status, grund = laufstatus(
        seiten + [s for u in uebersichten for s in _als_seiten(u)]
    )
    heute_gelesen = {s["adresse"] for s in ganz_gelesen(seiten)}
    faellig = ueberfaellig(ziel.seiten, gelesen, heute_gelesen, heute)
    daten = {
        "format": FORMAT,
        "anbieter": ziel.schluessel,
        "name": ziel.name,
        "datum": heute,
        "karte": datei,
        "vertragsform": karte.vertragsform,
        "laufstatus": status,
        "grund": grund,
        "frischegrenze_tage": FRISCHEGRENZE_TAGE,
        "lesefrist_tage": LESEFRIST_TAGE,
        "zeitbudget_sekunden": round(max(0.0, ende - start)),
        "dauer_sekunden": round(uhr() - start, 1),
        "seiten": seiten,
        "uebersichten": uebersichten,
        "ueberfaellig": faellig,
    }
    log.info(
        "Klick-Tageslauf %s: %s %s, %d Seiten, %d überfällig",
        ziel.schluessel,
        status,
        grund or "",
        len(heute_gelesen),
        len(faellig),
    )
    return daten


def crawler_im_browser(
    browser: Browser,
    ziel: Erkundungsziel,
    karte: Klickkarte,
    uhr: Callable[[], datetime],
    hole_robots: Callable[[str], tuple[int, str]],
) -> Crawler:
    """Der echte Crawler: ein Tor, eine Schleuse samt Frist je Anbieter."""
    return leser_im_browser(browser, ziel, karte, uhr, hole_robots)[0]


def leser_im_browser(
    browser: Browser,
    ziel: Erkundungsziel,
    karte: Klickkarte,
    uhr: Callable[[], datetime],
    hole_robots: Callable[[str], tuple[int, str]],
) -> tuple[Crawler, Uebersichtsleser]:
    """Crawler und Übersichtsleser eines Anbieters an derselben Schleuse samt Frist."""

    def hole_mit_frist(url: str) -> tuple[int, str]:
        if time.monotonic() >= schleuse.ende:
            raise GeraeteAbrufFehler(f"{GRUND_FRIST}, robots.txt nicht abgerufen")
        return hole_robots(url)

    waechter = RobotsWaechter(hole=hole_mit_frist)
    schleuse = Fristschleuse(Hostschleuse(waechter, uhr, ziel.rate_limit_sekunden), 0.0)

    def crawle(seite: Seitenziel, ende: float) -> Klicklauf:
        schleuse.setze(ende)
        cookies: set[str] = set()

        def beobachter(anfrage: Request, antwort: APIResponse) -> str | None:
            return beobachte(anfrage, antwort, seite.adresse, cookies)

        return klicke_durch(
            browser,
            seite.adresse,
            karte,
            waechter,
            uhr,
            schleuse=schleuse,
            kennung=ziel.kennung,
            frist=schleuse.offen,
            beobachter=beobachter,
            cookies=cookies,
            modell=seite.modell,
        )

    def lies(adresse: str, ende: float) -> dict:
        schleuse.setze(ende)
        kennung = ziel.kennung
        return lies_uebersicht(
            browser,
            adresse,
            karte,
            waechter,
            uhr,
            schleuse=schleuse,
            kennung=kennung,
            abstand_s=ziel.seitenabstand_sekunden,
        )

    return crawle, lies
