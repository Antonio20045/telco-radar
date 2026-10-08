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
Crawler nennt den Rest ``nicht besucht``.

Rotation: Einheit ist die Produktseite, denn der Crawler klickt alle Varianten einer
Seite in einem Gang. Zuerst kommen nie gelesene Seiten, dann die am längsten nicht
gelesenen (Lesestand, ``klickergebnis.lies_stand``); bei Gleichstand gilt die
Reihenfolge der Konfiguration. Seiten, die heute nicht ganz gelesen wurden (eine an der
Zeitgrenze abgeschnittene zählt nicht, ``klickergebnis.ROTATION_GELESEN``) und deren
letzte Lesung ``FRISCHEGRENZE_TAGE`` oder älter ist, stehen unter ``ueberfaellig``.
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
    ROTATION_GELESEN,
    laufstatus,
    nicht_besucht,
    seite_als_daten,
)
from .klicklauf import LAUF_GESTOERT, STOERUNG_ZEIT, Klicklauf
from .klickparallel import Laufpruefung
from .klickseite import GRUND_FRIST, Fristschleuse, beobachte
from .klickspur import ohne_geheimnisse
from .klicktor import Hostschleuse
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
    """Adressen ohne Geheimnisse, heute ungelesen und älter als die Frischegrenze."""
    tag = date.fromisoformat(heute)
    adressen = [ohne_geheimnisse(s.adresse) for s in seiten]
    return [
        a
        for a in adressen
        if a not in heute_gelesen
        and (
            a not in gelesen
            or (tag - date.fromisoformat(gelesen[a])).days >= FRISCHEGRENZE_TAGE
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
) -> dict:
    """Liest die Seiten eines Anbieters in Rotation; gibt die Ergebnisdatei zurück.

    ``laeufe`` ist die Parallellauf-Prüfung; ``None`` nur für Läufe ohne Actions.
    """
    start = uhr()
    seiten: list[dict] = []
    stopp: str | None = None
    zeit = 0
    for seite in reihenfolge(ziel.seiten, gelesen):
        rest = ende - uhr()
        if stopp is None and rest < MINDESTZEIT_SEITE_S:
            stopp = f"{GRUND_BUDGET}: noch {max(0, round(rest))} s"
        if stopp is None and laeufe is not None:
            anderer = laeufe()
            stopp = None if anderer is None else f"{GRUND_PARALLEL}: {anderer}"
        if stopp is not None:
            seiten.append(nicht_besucht(seite, stopp))
            continue
        lauf = crawle(seite, min(ende, uhr() + ZEIT_JE_SEITE_S))
        seiten.append(seite_als_daten(seite, lauf))
        if lauf.status == LAUF_GESTOERT and lauf.stoerung == STOERUNG_ZEIT:
            zeit += 1
            if zeit >= HOECHSTE_ZEITUEBERSCHREITUNGEN:
                stopp = f"{zeit} {GRUND_ZEITUEBERSCHREITUNGEN}: {lauf.grund}"
        elif lauf.status == LAUF_GESTOERT:
            stopp = f"{GRUND_NACH_STOERUNG}: {lauf.grund}"
    status, grund = laufstatus(seiten)
    heute_gelesen = {s["adresse"] for s in seiten if s["status"] in ROTATION_GELESEN}
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
        "zeitbudget_sekunden": round(max(0.0, ende - start)),
        "dauer_sekunden": round(uhr() - start, 1),
        "seiten": seiten,
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

    return crawle
