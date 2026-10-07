"""Weiter-Schritt der Klick-Karte: Startseite wählen, einmal weiter, Kacheln lesen.

Manche Anbieter zeigen eine Dimension erst in der Bestellstrecke (1&1: 24 oder „24+12“
Monate nach „Weiter zur Tarifauswahl“, Erkundung 07.10.2026, Commit c8ce1f77, Seiten 3
und 4). Trägt die Klick-Karte ``weiter`` (``klickkarte.Weiterschritt``), geht der
Klick-Crawler (``klickcrawler``) je Kombination der übrigen Dimensionen so vor:

1. Ab der zweiten Kombination öffnet ``Kontexte`` einen frischen Browserkontext (neue
   Cookies, leerer Warenkorb) am selben Tor und lädt die Startseite neu, mit Kanarie,
   Einwilligung und Vorbereitung wie jede Seite.
2. Er wählt die Optionen auf der Startseite und liest dort Seitenwerte, zweite Lesung
   und Markierung (``klicklesung.Leser.vorlesung``); sie gelten für jede Kachel.
3. Er klickt genau einen Weiter-Knopf: den einen sichtbaren Treffer mit dem erwarteten
   Text, ein ``a`` oder ``button`` ohne neues Fenster und ohne Kauf-, Kassen- oder
   Anmeldewort (``klickstrecke``). Nur dieser Klick darf schreiben (Warenkorb): das Tor
   lässt bis zur Navigation der Hauptseite jede Methode durch, danach nur GET und HEAD
   (``klicktor.GRUND_NUR_LESEN``), bis der Kontext schließt. Umleitungen prüft das Tor
   wie jede Adresse; robots.txt gilt für jede.
4. Zeigt die Folgeseite Anmeldung, Checkout oder Zahlung (``streckenende``), nach dem
   Laden, nach der Ruhe oder nach der Lesung, ist der Lauf gestört und endet.
5. Er liest jede Kachel (``knoepfe.<kacheln>``): Wert wie bei Knöpfen, nie geklickt;
   die Zusammenfassung ist die Kachel an derselben Stelle.

Scheitert der Weiter-Klick (Knopf fehlt, nicht eindeutig, verboten, nicht klickbar,
keine neue Adresse), heißt die Kombination ``nicht_erfasst`` mit Grund; Bot-Schutz,
eine Sperre durch robots.txt oder das Ende der Strecke beenden den Lauf.
"""

from __future__ import annotations

import itertools
from collections.abc import Callable
from dataclasses import replace
from typing import TYPE_CHECKING, Protocol
from urllib.parse import urlsplit

from playwright.sync_api import Error as PlaywrightFehler

from .klickecho import LAUFZEIT, Variante, variante_aus
from .klickkarte import DIMENSIONEN
from .klickkontext import Sitzung, cookie_werte, schliesse
from .klicklauf import (
    BEFUND,
    ERFASST,
    LAUF_GESPERRT,
    LAUF_GESTOERT,
    NICHT_ERFASST,
    Kombiergebnis,
)
from .klickstrecke import (
    FELDER_JS,
    KNOPF_JS,
    WEBSCHEMATA,
    kein_weiter,
    knapp,
    ohne_anker,
    streckenende,
)
from .klicktor import (
    GRUND_NUR_LESEN,
    GRUND_ZU_VIELE,
    HOECHSTE_UMLEITUNGEN,
    SEITEN_FRIST_MS,
    kurz,
)
from .klickwache import Abbruch

if TYPE_CHECKING:
    from playwright.sync_api import Locator, Page

    from .klickbedienung import Bedienung
    from .klickkarte import Klickkarte, Weiterschritt
    from .klicklauf import Klicklauf
    from .klicklesung import Leser, Vorlesung
    from .klicktor import Tor
    from .klickwache import Wache

GRUND_NICHT_BESUCHT = "nicht besucht"
GRUND_KNOPF = "Weiter-Knopf"
WEITER_FRIST_MS = 20_000
HOECHSTE_TREFFER = 20
_GELADEN_JS = "() => document.readyState === 'complete'"


class Kontexte:
    """Die Browserkontexte eines Laufs; ``neu`` schließt den alten und öffnet einen.

    Beim Schließen gilt das Tor als geschlossen (was dann scheitert, zählt nicht), und
    die Cookie-Werte gehen in ``cookies`` zum Schwärzen.
    """

    def __init__(
        self, oeffne: Callable[[], Sitzung], tor: Tor, cookies: set[str] | None
    ) -> None:
        self._oeffne, self.tor, self.cookies = oeffne, tor, cookies
        self.aktuell: Sitzung | None = None

    def neu(self) -> Page:
        """Ein frischer Kontext am selben Tor; Weiter-Klick und Nur-Lesen zurück."""
        if self.aktuell is not None:
            self.schliesse()
            self.tor.geschlossen = False
        self.tor.weiter_klick = self.tor.nur_lesen = False
        self.aktuell = self._oeffne()
        return self.aktuell.seite

    def schliesse(self) -> None:
        """Schließt den aktuellen Kontext; wirft nie."""
        self.tor.geschlossen = True
        if self.cookies is not None:
            self.cookies.update(cookie_werte(self.aktuell))
        schliesse(self.aktuell)
        self.aktuell = None


class Gang(Protocol):
    """Was der Weiter-Schritt vom Lauf des Klick-Crawlers braucht."""

    seite: Page
    karte: Klickkarte
    tor: Tor
    lauf: Klicklauf
    wache: Wache
    leser: Leser
    bedienung: Bedienung
    kontexte: Kontexte
    frist_ms: int
    hoechste: int
    unberuehrt: bool

    def _binde(self, seite: Page) -> None: ...

    def _oeffne_vor_frist(self, ziel: str) -> None: ...

    def _angebotene_werte(self, dimension: str) -> list[str | None]: ...

    def _waehle(
        self, dimension: str, wert: str, variante: Variante
    ) -> Kombiergebnis | None: ...

    def _zeit_um(self) -> bool: ...

    def _nicht_besucht(self, variante: Variante) -> Kombiergebnis: ...

    def _fehlen(self, dimension: str) -> str: ...


def je_weiter(gang: Gang, weiter: Weiterschritt) -> None:
    """Je Kombination der Startseite: wählen, vorlesen, weiterklicken, Kacheln lesen."""
    vorn = [d for d in DIMENSIONEN if d != weiter.kacheln]
    angeboten = [gang._angebotene_werte(d) for d in vorn]
    starts = [dict(zip(vorn, w, strict=True)) for w in itertools.product(*angeboten)]
    ziele = [{**s, weiter.kacheln: None} for s in starts]
    unlesbar = [gang.leser.unlesbar_in(z) for z in ziele]
    for nummer, (ziel, grund) in enumerate(zip(ziele, unlesbar, strict=True)):
        gang.wache.pruefe_tor()
        variante = variante_aus(*(ziel[d] for d in DIMENSIONEN))
        if grund is not None:
            ergebnisse = [Kombiergebnis(variante, NICHT_ERFASST, grund)]
        elif len(gang.lauf.ergebnisse) >= gang.hoechste:
            ergebnisse = [_zu_viele(gang, variante)]
        elif gang._zeit_um():
            ergebnisse = [gang._nicht_besucht(variante)]
        else:
            if nummer:
                gang._binde(gang.kontexte.neu())
                gang._oeffne_vor_frist(gang.lauf.adresse)
            ergebnisse = _start(gang, weiter, ziel, variante)
        auswahl = tuple(ziel[d] for d in DIMENSIONEN)
        for ergebnis in ergebnisse:
            gang.lauf.ergebnisse.append(
                ergebnis if ergebnis.auswahl else replace(ergebnis, auswahl=auswahl)
            )


def _start(
    gang: Gang,
    weiter: Weiterschritt,
    ziel: dict[str, str | None],
    variante: Variante,
) -> list[Kombiergebnis]:
    """Wählt die Startseite, liest vor, klickt weiter und liest die Kacheln."""
    vorn = [d for d in DIMENSIONEN if d != weiter.kacheln]
    fehlend = [d for d in vorn if ziel[d] is None]
    if fehlend:
        gang.lauf.struktur.knopf(False)
        return [Kombiergebnis(variante, NICHT_ERFASST, gang._fehlen(fehlend[0]))]
    for dimension in vorn:
        ergebnis = gang._waehle(dimension, str(ziel[dimension]), variante)
        if ergebnis is not None:
            return [ergebnis]
    if gang.bedienung.bereite_vor():
        gang.unberuehrt = False
    if gang.wache.ausstehend is not None:
        return [Kombiergebnis(variante, NICHT_ERFASST, gang.wache.ausstehend)]
    vorab = gang.leser.vorlesung(ziel, gang.unberuehrt)
    grund = _klicke_weiter(gang, weiter)
    if grund is not None:
        return [Kombiergebnis(variante, NICHT_ERFASST, grund)]
    ergebnisse = _kacheln(gang, weiter.kacheln, ziel, vorab)
    _pruefe_strecke(gang.seite)
    return ergebnisse


def _klicke_weiter(gang: Gang, weiter: Weiterschritt) -> str | None:
    """Klickt den einen Weiter-Knopf und lädt die Folgeseite; sonst der Grund."""
    seite, tor, wache = gang.seite, gang.tor, gang.wache
    knopf, grund = _knopf(seite, weiter)
    if knopf is None:
        return grund
    wache.warte_offen()
    adresse = ohne_anker(seite.url)
    marke = len(gang.lauf.verworfen)
    wache.geoeffnet = False
    tor.weiter_klick = True
    try:
        knopf.click(timeout=gang.frist_ms, no_wait_after=True)
        gewechselt = wache.warte(
            lambda: ohne_anker(seite.url) != adresse, WEITER_FRIST_MS
        )
    except PlaywrightFehler as fehler:
        return f"{GRUND_KNOPF} nicht klickbar: {kurz(fehler)}"
    finally:
        tor.nur_lesen = True
    gesperrt = _gesperrt(gang, marke)
    if gesperrt is not None and not (gewechselt and _im_netz(seite.url)):
        raise Abbruch(LAUF_GESPERRT, f"{GRUND_KNOPF}: {gesperrt}")
    if not gewechselt:
        sekunden = WEITER_FRIST_MS // 1000
        return f"{GRUND_KNOPF} führt nirgends hin: Adresse nach {sekunden} s gleich"
    _folge(gang)
    _pruefe_strecke(seite)
    wache.warte_ruhe()
    _pruefe_strecke(seite)
    return None


def _knopf(seite: Page, weiter: Weiterschritt) -> tuple[Locator | None, str | None]:
    """Der eine sichtbare Treffer mit dem erwarteten Text; sonst der Grund."""
    treffer = seite.locator(weiter.selektor)
    try:
        anzahl = treffer.count()
        sichtbar = [
            treffer.nth(i)
            for i in range(min(anzahl, HOECHSTE_TREFFER))
            if treffer.nth(i).is_visible()
        ]
        passend = [(k, k.evaluate(KNOPF_JS)) for k in sichtbar]
    except PlaywrightFehler as fehler:
        return None, f"{GRUND_KNOPF}: Selektor nicht lesbar ({kurz(fehler)})"
    gesucht = knapp(weiter.text)
    passend = [(k, d) for k, d in passend if gesucht in knapp(d["text"])]
    if len(passend) != 1:
        wie = "nicht gefunden" if not passend else "nicht eindeutig"
        grund = (
            f"{GRUND_KNOPF} {wie}: {anzahl} Treffer, {len(sichtbar)} sichtbar,"
            f" {len(passend)} passend"
        )
        return None, grund
    knopf, daten = passend[0]
    mangel = kein_weiter(daten)
    if mangel is not None:
        return None, f"{GRUND_KNOPF} „{daten['text']}“ {mangel}"
    return knopf, None


def _folge(gang: Gang) -> None:
    """Folgt geprüften Umleitungen und wartet, bis die Folgeseite geladen ist.

    Erst wenn die leere Seite einer Umleitung geladen ist, lädt er ihr Ziel; sonst
    unterbräche ihre Navigation das Laden des Ziels.
    """
    for _ in range(HOECHSTE_UMLEITUNGEN + 1):
        if not gang.wache.warte(lambda: _geladen(gang.seite), SEITEN_FRIST_MS):
            grund = f"Folgeseite nach {SEITEN_FRIST_MS} ms nicht geladen"
            raise Abbruch(LAUF_GESTOERT, grund)
        ziel = gang.tor.umleitung
        if ziel is None:
            break
        darf, grund = gang.tor.darf(ziel)
        if not darf:
            raise Abbruch(LAUF_GESPERRT, grund)
        gang.wache.lade(ziel)
    else:
        raise Abbruch(LAUF_GESTOERT, f"Abruf gestört ({GRUND_ZU_VIELE})")
    if not _im_netz(gang.seite.url):
        grund = f"Folgeseite nicht geladen ({gang.seite.url})"
        raise Abbruch(LAUF_GESTOERT, grund)
    darf, grund = gang.tor.darf(gang.seite.url)
    if not darf:
        raise Abbruch(LAUF_GESPERRT, grund)
    gang.wache.geoeffnet = True


def _kacheln(
    gang: Gang, kachel: str, ziel: dict[str, str | None], vorab: Vorlesung
) -> list[Kombiergebnis]:
    """Liest jede Kachel der Folgeseite als eigene Kombination."""
    optionen = gang.leser.optionen(kachel)
    gang.lauf.struktur.knopf(bool(optionen))
    if not optionen:
        variante = variante_aus(*(ziel[d] for d in DIMENSIONEN))
        return [Kombiergebnis(variante, NICHT_ERFASST, gang._fehlen(kachel))]
    ergebnisse: list[Kombiergebnis] = []
    for stelle, option in enumerate(optionen):
        wert = option.unlesbar if option.wert is None else option.wert
        kombi = {**ziel, kachel: wert}
        variante = variante_aus(*(kombi[d] for d in DIMENSIONEN))
        if option.wert is None:
            gang.lauf.struktur.knopf(False)
            grund = (
                f"Option „{option.unlesbar}“ für {kachel} passt nicht auf das Muster"
            )
            ergebnis = Kombiergebnis(variante, NICHT_ERFASST, grund)
        elif variante.laufzeit is None:
            grund = f"Laufzeit „{kombi[LAUFZEIT]}“ nicht lesbar"
            ergebnis = Kombiergebnis(variante, NICHT_ERFASST, grund)
        elif len(gang.lauf.ergebnisse) + len(ergebnisse) >= gang.hoechste:
            ergebnis = _zu_viele(gang, variante)
        else:
            ergebnis = _lies(gang, variante, kombi, vorab, stelle)
        auswahl = tuple(kombi[d] for d in DIMENSIONEN)
        ergebnisse.append(replace(ergebnis, auswahl=auswahl))
    return ergebnisse


def _lies(
    gang: Gang,
    variante: Variante,
    kombi: dict[str, str | None],
    vorab: Vorlesung,
    stelle: int,
) -> Kombiergebnis:
    struktur = gang.lauf.struktur
    ergebnis = gang.leser.lies(variante, kombi, struktur, vorab=vorab, stelle=stelle)
    if ergebnis.status not in (ERFASST, BEFUND):
        return ergebnis
    return gang.leser.belege(ergebnis, variante, gang.lauf, gang.tor.uhr())


def _zu_viele(gang: Gang, variante: Variante) -> Kombiergebnis:
    grund = f"{GRUND_NICHT_BESUCHT}: mehr als {gang.hoechste} Kombinationen"
    return Kombiergebnis(variante, NICHT_ERFASST, grund)


def _pruefe_strecke(seite: Page) -> None:
    """Beendet den Lauf, wenn Adresse oder Seite Anmeldung, Checkout oder Zahlung
    zeigen."""
    ende = streckenende(seite.url, seite.evaluate(FELDER_JS))
    if ende is not None:
        raise Abbruch(LAUF_GESTOERT, f"Folgeseite zeigt {ende}")


def _gesperrt(gang: Gang, marke: int) -> str | None:
    """Was das Tor seit ``marke`` verwarf, nicht wegen ``GRUND_NUR_LESEN``."""
    for verworfen in gang.lauf.verworfen[marke:]:
        if verworfen.grund != GRUND_NUR_LESEN:
            return f"{verworfen.url} {verworfen.grund}"
    return None


def _im_netz(adresse: str) -> bool:
    return urlsplit(adresse).scheme in WEBSCHEMATA


def _geladen(seite: Page) -> bool:
    try:
        return seite.evaluate(_GELADEN_JS) is True
    except PlaywrightFehler:
        return False
