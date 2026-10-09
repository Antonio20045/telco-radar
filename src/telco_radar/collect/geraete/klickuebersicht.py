"""Übersicht eines Anbieters im Klick-Tageslauf: die Telekom-Smartphones je Tarif.

Die Übersicht (``uebersichten:`` in ``config/klick_tageslauf.yaml``) trägt in
``window.__INITIAL_STATE__.productList`` jedes Gerät mit Anzahlung, Rate, Tarifpreis
und Produktlink (``telekom.lies_buendel``). ``lies_uebersicht`` öffnet sie wie eine
Produktseite: eigener Kontext (``klickkontext.oeffne_sitzung``), jede Anfrage am
``klicktor.Tor`` (robots.txt samt Crawl-delay, Abstand je Host, Sperrerkennung), Laden
und JavaScript-Prüfung über ``klickwache.Wache.lade``. Geklickt wird nichts; gelesen
wird ``page.content()``. Eine Seite ohne lesbaren Zustand, ohne Gerät, mit Bot-Schutz
oder Umleitung ist ``gestoert`` mit Grund und trägt keinen Satz; robots.txt-Sperre
heißt ``gesperrt``. Das Ergebnis ist ein Eintrag von ``uebersichten[]`` der
Ergebnisdatei; ``klickrohsatz.ausbeute`` macht daraus Rohsätze. Wirft nie.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from playwright.sync_api import Error as PlaywrightFehler

from .basis import GeraeteAbrufFehler
from .klickcrawler import ANTWORT_FRIST_MS, FENSTER
from .klickkontext import Sitzung, oeffne_sitzung, schliesse
from .klicklauf import LAUF_GELESEN, LAUF_GESTOERT, Klicklauf
from .klickspur import ohne_geheimnisse
from .klicktor import Schleuse, Tor, kurz
from .klickwache import Abbruch, Wache
from .robots import RobotsWaechter
from .telekom import lies_buendel

if TYPE_CHECKING:
    from playwright.sync_api import Browser

    from .klickkarte import Klickkarte

log = logging.getLogger(__name__)

GRUND_UMLEITUNG = "Übersicht umgeleitet"
GRUND_LEER = "Übersicht ohne Gerät"


def lies_uebersicht(
    browser: Browser,
    adresse: str,
    karte: Klickkarte,
    waechter: RobotsWaechter,
    uhr: Callable[[], datetime],
    *,
    schleuse: Schleuse,
    kennung: str | None = None,
) -> dict:
    """Liest die Übersicht ``adresse``; gibt den Eintrag für ``uebersichten[]``."""
    lauf = Klicklauf(anbieter=karte.anbieter, adresse=adresse)
    tor = Tor(waechter, uhr, schleuse, lauf)
    sitzung: Sitzung | None = None
    text = ""
    try:
        sitzung = oeffne_sitzung(browser, tor, FENSTER, kennung)
        wache = Wache(sitzung.seite, karte, tor, lauf, ANTWORT_FRIST_MS)
        wache.lade(adresse)
        if tor.umleitung is not None:
            raise Abbruch(LAUF_GESTOERT, f"{GRUND_UMLEITUNG} ({tor.umleitung})")
        wache.pruefe_tor()
        text = sitzung.seite.content()
    except Abbruch as abbruch:
        lauf.status, lauf.grund = abbruch.status, abbruch.grund
    except PlaywrightFehler as fehler:
        lauf.status, lauf.grund = LAUF_GESTOERT, f"Browserfehler: {kurz(fehler)}"
    finally:
        tor.geschlossen = True
        schliesse(sitzung)
    if lauf.status == LAUF_GELESEN and tor.stoerung is not None:
        lauf.status, lauf.grund = LAUF_GESTOERT, tor.stoerung
    saetze = _saetze(lauf, text, adresse) if lauf.status == LAUF_GELESEN else []
    if lauf.status != LAUF_GELESEN:
        log.warning("Klick-Übersicht %s: %s", ohne_geheimnisse(adresse), lauf.grund)
    seite = ohne_geheimnisse(adresse)
    zeitpunkt = uhr().astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    return {
        "adresse": seite,
        "status": lauf.status,
        "grund": lauf.grund,
        "stoerung": lauf.stoerung,
        "http_status": lauf.http_status,
        "saetze": saetze,
        "beleg": {"seite": seite, "zeitpunkt": zeitpunkt},
    }


def _saetze(lauf: Klicklauf, text: str, adresse: str) -> list[dict]:
    """Die Sätze aus ``text``; ohne lesbaren Zustand oder Gerät ist der Lauf gestört."""
    try:
        saetze = lies_buendel(text, adresse)
    except GeraeteAbrufFehler as fehler:
        lauf.status, lauf.grund = LAUF_GESTOERT, str(fehler)
        return []
    if not saetze:
        lauf.status, lauf.grund = LAUF_GESTOERT, GRUND_LEER
    return saetze
