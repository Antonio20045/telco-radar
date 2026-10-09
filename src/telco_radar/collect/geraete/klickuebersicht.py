"""Übersicht eines Anbieters im Klick-Tageslauf: alle Geräte einer Tarifstufe.

Die Übersicht (``uebersichten:`` in ``config/klick_tageslauf.yaml``) nennt jedes Gerät
mit Anzahlung, Rate, Tarifpreis und Produktlink. Wie sie zu lesen ist, sagt die
``Lesart`` des Anbieters (``LESARTEN``, Schlüssel ``Klickkarte.anbieter``): Sätze aus
dem Seitentext, Folgelink, Bereitschaft der Seite. Telekom: ``telekom.lies_buendel``
auf ``window.__INITIAL_STATE__.productList``, Folgelink ``<link rel="next">``, sonst
der Link ``WEITER_TEXT``; bereit, sobald der Zustand im Hauptdokument steht, ohne auf
``load`` zu warten. ``lies_uebersicht`` öffnet jede Seite wie eine Produktseite:
eigener Kontext (``klickkontext.oeffne_sitzung``), jede Anfrage am ``klicktor.Tor``
(robots.txt samt Crawl-delay, Abstand je Host, Sperrerkennung), Laden und
JavaScript-Prüfung über ``klickwache.Wache.lade``. Geklickt wird nichts; gelesen wird
``page.content()``. Eine Seite ohne lesbaren Zustand, ohne Gerät, mit Bot-Schutz,
Umleitung oder ohne Lesart ist ``gestoert`` mit Grund und trägt keinen Satz;
robots.txt-Sperre heißt ``gesperrt``.

Danach folgt sie dem gelesenen Folgelink, aufgelöst gegen die Seitenadresse, nur auf
demselben Host und mit Erlaubnis von robots.txt, höchstens ``HOECHSTE_SEITEN`` Seiten;
zusammengesetzt oder hochgezählt wird keine Adresse. Zwischen zwei Seiten wartet sie
``abstand_s``. Jede Seite steht mit Status und eigenem Beleg unter ``seiten``;
``saetze`` hält jedes Gerät einmal. ``vollstaendig`` ist wahr nur, wenn die letzte
Seite keinen Folgelink trägt; sonst nennt ``unvollstaendig`` den Grund (``GRUND_*``,
gestörte Seite). Das Ergebnis ist ein Eintrag von ``uebersichten[]`` der
Ergebnisdatei; ``klickrohsatz.ausbeute`` macht daraus Rohsätze. Wirft nie.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from html.parser import HTMLParser
from typing import TYPE_CHECKING
from urllib.parse import urljoin, urlsplit

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
HOECHSTE_SEITEN = 6
GRUND_OHNE_LESART = "keine Lesart für die Übersicht dieses Anbieters"
WEITER_TEXT = "Weitere Geräte anzeigen"
TELEKOM_BEREIT_JS = (
    "() => window.__INITIAL_STATE__ !== undefined || document.readyState === 'complete'"
)
GRUND_OBERGRENZE = f"Obergrenze von {HOECHSTE_SEITEN} Seiten erreicht"
GRUND_FREMDER_HOST = "Folgelink auf fremden Host"
GRUND_GESPERRT = "Folgeseite von robots.txt gesperrt"
GRUND_KREIS = "Folgelink auf schon gelesene Seite"


@dataclass(frozen=True)
class Lesart:
    """Wie die Übersicht eines Anbieters gelesen wird (``LESARTEN``): ``saetze``
    macht aus Seitentext und Adresse die Sätze und wirft ``GeraeteAbrufFehler``,
    ``folgelink`` gibt das gelesene ``href`` der Folgeseite oder ``None``, ``bereit``
    ersetzt das Warten auf ``load`` (``Wache.lade``), ``None`` wartet darauf."""

    saetze: Callable[[str, str], list[dict]]
    folgelink: Callable[[str], str | None]
    bereit: str | None = None


def lies_uebersicht(
    browser: Browser,
    adresse: str,
    karte: Klickkarte,
    waechter: RobotsWaechter,
    uhr: Callable[[], datetime],
    *,
    schleuse: Schleuse,
    kennung: str | None = None,
    abstand_s: float = 0.0,
    schlafe: Callable[[float], None] = time.sleep,
) -> dict:
    """Liest die Übersicht ``adresse`` samt Folgeseiten; der Eintrag für
    ``uebersichten[]``."""
    lesart = LESARTEN.get(karte.anbieter)
    seiten: list[dict] = []
    saetze: dict[tuple, dict] = {}
    gelesen: list[str] = []
    ziel: str | None = adresse
    fehlt: str | None = None
    while ziel is not None:
        if gelesen and abstand_s > 0:
            schlafe(abstand_s)
        seite, neu = _lies_seite(
            browser, ziel, karte, lesart, waechter, uhr, schleuse, kennung
        )
        gelesen.append(ziel)
        frisch = {_schluessel(s): s for s in neu if _schluessel(s) not in saetze}
        saetze.update(frisch)
        href = seite.pop("folgelink")
        seiten.append({**seite, "saetze_neu": len(frisch)})
        ziel, fehlt = _folge(seite, href, gelesen, waechter, uhr)
    erste = seiten[0]
    return {
        **{k: erste[k] for k in ("adresse", "status", "grund", "stoerung")},
        "http_status": erste["http_status"],
        "saetze": list(saetze.values()) if erste["status"] == LAUF_GELESEN else [],
        "beleg": erste["beleg"],
        "seiten": seiten,
        "vollstaendig": fehlt is None,
        "unvollstaendig": fehlt,
    }


def _folge(
    seite: dict,
    href: str | None,
    gelesen: list[str],
    waechter: RobotsWaechter,
    uhr: Callable[[], datetime],
) -> tuple[str | None, str | None]:
    """Die nächste Adresse oder der Grund, warum die Übersicht hier endet."""
    if seite["status"] != LAUF_GELESEN:
        return None, f"{seite['status']}: {seite['grund']}"
    if href is None:
        return None, None
    if len(gelesen) >= HOECHSTE_SEITEN:
        return None, GRUND_OBERGRENZE
    neu = urljoin(gelesen[-1], href)
    if urlsplit(neu).netloc != urlsplit(gelesen[-1]).netloc:
        return None, f"{GRUND_FREMDER_HOST} ({ohne_geheimnisse(neu)})"
    darf, grund = waechter.darf(neu, uhr())
    if not darf:
        return None, f"{GRUND_GESPERRT}: {grund}"
    if neu in gelesen:
        return None, GRUND_KREIS
    return neu, None


def _lies_seite(
    browser: Browser,
    adresse: str,
    karte: Klickkarte,
    lesart: Lesart | None,
    waechter: RobotsWaechter,
    uhr: Callable[[], datetime],
    schleuse: Schleuse,
    kennung: str | None,
) -> tuple[dict, list[dict]]:
    """Eine Seite der Übersicht: ihr Eintrag unter ``seiten`` und ihre Sätze."""
    lauf = Klicklauf(anbieter=karte.anbieter, adresse=adresse)
    tor = Tor(waechter, uhr, schleuse, lauf)
    sitzung: Sitzung | None = None
    text = ""
    try:
        if lesart is None:
            raise Abbruch(LAUF_GESTOERT, f"{GRUND_OHNE_LESART} ({karte.anbieter})")
        sitzung = oeffne_sitzung(browser, tor, FENSTER, kennung)
        wache = Wache(sitzung.seite, karte, tor, lauf, ANTWORT_FRIST_MS)
        wache.lade(adresse, bereit=lesart.bereit)
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
    saetze: list[dict] = []
    folge: str | None = None
    if lesart is not None and lauf.status == LAUF_GELESEN:
        saetze, folge = _saetze(lesart, lauf, text, adresse), lesart.folgelink(text)
    if lauf.status != LAUF_GELESEN:
        log.warning("Klick-Übersicht %s: %s", ohne_geheimnisse(adresse), lauf.grund)
    seite = ohne_geheimnisse(adresse)
    zeitpunkt = uhr().astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    eintrag = {
        "adresse": seite,
        "status": lauf.status,
        "grund": lauf.grund,
        "stoerung": lauf.stoerung,
        "http_status": lauf.http_status,
        "beleg": {"seite": seite, "zeitpunkt": zeitpunkt},
        "folgelink": folge,
    }
    return eintrag, saetze


def _saetze(lesart: Lesart, lauf: Klicklauf, text: str, adresse: str) -> list[dict]:
    """Die Sätze aus ``text``; ohne lesbaren Zustand oder Gerät ist der Lauf gestört."""
    try:
        saetze = lesart.saetze(text, adresse)
    except GeraeteAbrufFehler as fehler:
        lauf.status, lauf.grund = LAUF_GESTOERT, str(fehler)
        return []
    if not saetze:
        lauf.status, lauf.grund = LAUF_GESTOERT, GRUND_LEER
    return saetze


def _schluessel(satz: dict) -> tuple:
    """Ein Gerät der Übersicht: Produktlink, Titel und Speicher."""
    return (satz.get("url"), satz.get("titel"), satz.get("speicher_gb"))


def telekom_folgelink(text: str) -> str | None:
    """Telekom: ``href`` von ``<link rel="next">``, sonst des Links ``WEITER_TEXT``."""
    leser = _Folgelink()
    leser.feed(text)
    leser.close()
    return leser.naechste or leser.knopf


class _Folgelink(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.naechste: str | None = None
        self.knopf: str | None = None
        self._href: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        werte = dict(attrs)
        rel = (werte.get("rel") or "").lower().split()
        if tag == "link" and "next" in rel and self.naechste is None:
            self.naechste = werte.get("href") or None
        elif tag == "a":
            self._href = werte.get("href") or None

    def handle_endtag(self, tag: str) -> None:
        if tag == "a":
            self._href = None

    def handle_data(self, data: str) -> None:
        if self._href is not None and self.knopf is None and WEITER_TEXT in data:
            self.knopf = self._href


LESARTEN: dict[str, Lesart] = {
    "Telekom": Lesart(lies_buendel, telekom_folgelink, TELEKOM_BEREIT_JS),
}
"""Lesart je Anbieter (``Klickkarte.anbieter``); ohne Eintrag ist die Übersicht
gestört mit ``GRUND_OHNE_LESART``."""
