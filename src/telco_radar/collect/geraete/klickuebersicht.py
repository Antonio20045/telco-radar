"""Übersicht eines Anbieters im Klick-Tageslauf: alle Geräte einer Tarifstufe.

Die Übersicht (``uebersichten:`` in ``config/klick_tageslauf.yaml``) nennt jedes Gerät
mit Anzahlung, Rate, Tarifpreis und Produktlink. Wie sie zu lesen ist, sagt die
``Lesart`` des Anbieters (``LESARTEN``, Schlüssel ``Klickkarte.anbieter``): Sätze aus
dem Seitentext und Folgelink oder Datenantworten (``klickliste``), Bereitschaft der
Seite. Telekom (``TELEKOM_LISTE``): Datenantwort ``productOfferings/listing`` nach dem
Ausschalten des Rückgabedeals, „Weitere Geräte anzeigen“ in der Seite, gelesen von
``telekom_liste.lies_listing``; ``telekom_folgelink`` liest den Folgelink der
serverseitigen Übersicht bis September 2026. 1&1: Tarifdetail-Seiten und Geräteraster
(``klickraster``), ohne Folgeseite. ``lies_uebersicht`` öffnet jede Seite wie
eine Produktseite: eigener Kontext (``klickkontext.oeffne_sitzung``), jede Anfrage am
``klicktor.Tor`` (robots.txt samt Crawl-delay, Abstand je Host, Sperrerkennung), Laden
und JavaScript-Prüfung über ``klickwache.Wache.lade``; gelesen wird
``page.content()``. Eine Seite ohne Gerät ist ``leer``; mit Bot-Schutz, Umleitung oder
ohne Lesart ist sie ``gestoert`` mit Grund und trägt keinen Satz; robots.txt-Sperre
heißt ``gesperrt``.

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
from .klickanschluss import kein_folgelink
from .klickcrawler import ANTWORT_FRIST_MS, FENSTER
from .klickergebnis import LAUF_LEER
from .klickkontext import Sitzung, oeffne_sitzung, schliesse
from .klicklauf import LAUF_GELESEN, LAUF_GESTOERT, Klicklauf
from .klickliste import Datenliste, Listenlauf
from .klickraster import BEREIT_JS, einsundeins_saetze
from .klickspur import ohne_geheimnisse
from .klicktor import Schleuse, Tor, kurz
from .klickwache import Abbruch, Wache
from .robots import RobotsWaechter
from .telekom_liste import lies_listing

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
    ersetzt das Warten auf ``load`` (``Wache.lade``), ``None`` wartet darauf. Mit
    ``liste`` kommen die Sätze aus Datenantworten (``klickliste``) und die Seite
    blättert selbst; ``saetze`` und ``folgelink`` sind dann ``None``."""

    saetze: Callable[[str, str], list[dict]] | None
    folgelink: Callable[[str], str | None] | None
    bereit: str | None = None
    liste: Datenliste | None = None


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
        if fehlt is None and "liste" in seite:
            fehlt = seite["liste"]["unvollstaendig"]
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
    liste: Listenlauf | None = None
    text = ""
    try:
        if lesart is None:
            raise Abbruch(LAUF_GESTOERT, f"{GRUND_OHNE_LESART} ({karte.anbieter})")
        sitzung = oeffne_sitzung(browser, tor, FENSTER, kennung)
        wache = Wache(sitzung.seite, karte, tor, lauf, ANTWORT_FRIST_MS)
        if lesart.liste is not None:
            liste = Listenlauf(sitzung.seite, wache, lesart.liste)
        wache.lade(adresse, bereit=lesart.bereit)
        if tor.umleitung is not None:
            raise Abbruch(LAUF_GESTOERT, f"{GRUND_UMLEITUNG} ({tor.umleitung})")
        wache.pruefe_tor()
        if liste is not None:
            liste.bediene()
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
    saetze, folge = _lies_saetze(lesart, liste, lauf, text, adresse)
    if lauf.status != LAUF_GELESEN:
        log.warning("Klick-Übersicht %s: %s", ohne_geheimnisse(adresse), lauf.grund)
    seite = ohne_geheimnisse(adresse)
    zeitpunkt = uhr().astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    eintrag: dict[str, object] = {
        "adresse": seite,
        "status": lauf.status,
        "grund": lauf.grund,
        "stoerung": lauf.stoerung,
        "http_status": lauf.http_status,
        "beleg": {"seite": seite, "zeitpunkt": zeitpunkt},
        "folgelink": folge,
    }
    if liste is not None:
        eintrag["liste"] = liste.diagnose
    return eintrag, saetze


def _saetze(
    lies: Callable[[str, str], list[dict]], lauf: Klicklauf, text: str, adresse: str
) -> list[dict]:
    """Die Sätze aus ``text``; ohne lesbaren Zustand oder Gerät ist die Übersicht leer.

    Leer, nicht gestört: die Seite kam ohne Bot-Schutz, nur unsere Lesart fand nichts
    (Telekom lädt die Liste seit Oktober 2026 per Datenantwort nach, Klick-Tageslauf
    09.10.2026). Darum hält das den Anbieter nicht an; die Produktseiten laufen weiter.
    """
    try:
        saetze = lies(text, adresse)
    except GeraeteAbrufFehler as fehler:
        lauf.status, lauf.grund = LAUF_LEER, str(fehler)
        return []
    if not saetze:
        lauf.status, lauf.grund = LAUF_LEER, GRUND_LEER
    return saetze


def _lies_saetze(
    lesart: Lesart | None,
    liste: Listenlauf | None,
    lauf: Klicklauf,
    text: str,
    adresse: str,
) -> tuple[list[dict], str | None]:
    """Die Sätze einer gelesenen Seite und ihr Folgelink."""
    if lesart is None or lauf.status != LAUF_GELESEN:
        return [], None
    saetze: list[dict] = []
    if liste is not None:
        saetze = _listensaetze(liste, lauf, text, adresse)
    elif lesart.saetze is not None:
        saetze = _saetze(lesart.saetze, lauf, text, adresse)
    if lauf.status != LAUF_GELESEN or lesart.folgelink is None:
        return saetze, None
    return saetze, lesart.folgelink(text)


def _listensaetze(
    liste: Listenlauf, lauf: Klicklauf, text: str, adresse: str
) -> list[dict]:
    """Die Sätze aus den Datenantworten; die Zahlen dazu gehen in die Diagnose."""
    lesung = liste.liste.saetze(liste.nutzlasten, text, adresse)
    liste.diagnose.update(lesung.zahlen())
    if not lesung.saetze:
        lauf.status = LAUF_LEER
        lauf.grund = f"{GRUND_LEER} ({lesung.mit_rueckgabedeal} mit Rückgabedeal)"
    return lesung.saetze


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


TELEKOM_LISTE = Datenliste(
    url_teil="/shop/api/eshop/bff-de/productOfferings/listing",
    schalter="span.dt_switch.forwardTradeInSwitch",
    aus='[aria-checked="false"]',
    weiter_text=WEITER_TEXT,
    saetze=lies_listing,
)
"""Telekom seit Oktober 2026 (Zweig klick-erkundung, Commit b335c6ec): Liste per
Datenantwort, beim Laden mit „Telekom Rückgabedeal“ (bedienelemente-1.json Element 52),
Schalter wie in ``vorbereitung`` der Klick-Karte."""

LESARTEN: dict[str, Lesart] = {
    "Telekom": Lesart(None, None, TELEKOM_BEREIT_JS, TELEKOM_LISTE),
    "1&1": Lesart(einsundeins_saetze, kein_folgelink, BEREIT_JS),
}
"""Lesart je Anbieter (``Klickkarte.anbieter``); ohne Eintrag ist die Übersicht
gestört mit ``GRUND_OHNE_LESART``."""
