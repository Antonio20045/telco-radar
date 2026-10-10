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
   die Zusammenfassung ist die Kachel an derselben Stelle. Einen zweiten Klick gibt
   es nicht: der Lader lehnt ``oeffnen``, ``schliessen`` und Textmuster mit eigenem
   Selektor ab. Jede gelesene Kachel trägt ihre ``klickdiagnose.Diagnose``; nennt die
   zweite Lesung eine andere Laufzeit, ist die Kachel eigene Quelle (``klickkachel``).

Scheitert der Weiter-Klick (Knopf fehlt, nicht eindeutig, verboten, nicht klickbar,
keine neue Adresse), heißt die Kombination ``nicht_erfasst`` mit Grund, und die
nächste wird versucht. Bot-Schutz, eine Sperre von Dokument oder POST des Klicks
(``klickstrecke.sperre_des_klicks``; eine fremde Sperre zählt nicht) oder das Ende der
Strecke beenden den Lauf. Ist dabei die Frist abgelaufen, heißt die Kombination wie
beim Klicken „nicht besucht“; gelesene Kacheln bleiben, der Lauf heißt ``zeitgrenze``.
"""

from __future__ import annotations

import itertools
from collections.abc import Callable
from dataclasses import replace
from typing import TYPE_CHECKING, Protocol
from urllib.parse import urlsplit

from playwright.sync_api import Error as PlaywrightFehler

from .klickdiagnose import diagnose
from .klickecho import LAUFZEIT, Variante, variante_aus
from .klickkarte import DIMENSIONEN
from .klickkontext import Browserzustand, Sitzung, cookie_werte, schliesse
from .klicklauf import (
    BEFUND,
    ERFASST,
    LAUF_GESPERRT,
    LAUF_GESTOERT,
    LAUF_ZEITGRENZE,
    NICHT_ERFASST,
    Kombiergebnis,
)
from .klickstrecke import (
    DOKUMENT,
    FELDER_JS,
    GRUND_KNOPF,
    POST,
    WEBSCHEMATA,
    hat_gewechselt,
    ohne_anker,
    sperre_des_klicks,
    streckenende,
    waehle_knopf,
)
from .klicktor import GRUND_ZU_VIELE, HOECHSTE_UMLEITUNGEN, SEITEN_FRIST_MS, kurz
from .klickwache import Abbruch

if TYPE_CHECKING:
    from playwright.sync_api import Page, Request

    from .klickbedienung import Bedienung
    from .klickkarte import Klickkarte, Weiterschritt
    from .klicklauf import Klicklauf
    from .klicklesung import Leser, Vorlesung
    from .klicktor import Tor
    from .klickwache import Wache

GRUND_NICHT_BESUCHT = "nicht besucht"
WEITER_FRIST_MS = 20_000
_GELADEN_JS = "() => document.readyState === 'complete'"


class Kontexte:
    """Die Browserkontexte eines Laufs; ``neu`` schließt den alten und öffnet einen.

    Beim Schließen gilt das Tor als geschlossen (was dann scheitert, zählt nicht), und
    die Cookie-Werte gehen in ``cookies`` zum Schwärzen; ``zustand`` merkt sich Cookies
    und Speicher für den nächsten Kontext.
    """

    def __init__(
        self,
        oeffne: Callable[[], Sitzung],
        tor: Tor,
        cookies: set[str] | None,
        zustand: Browserzustand | None = None,
    ) -> None:
        self._oeffne, self.tor, self.cookies = oeffne, tor, cookies
        self.zustand = zustand
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
        if self.zustand is not None:
            self.zustand.merke(self.aktuell)
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
    frist_ms: int
    hoechste: int
    unberuehrt: bool

    def oeffne_neu(self) -> None:
        """Ein frischer Kontext mit geladener Startseite."""

    def waehle(
        self, dimension: str, wert: str, variante: Variante
    ) -> Kombiergebnis | None:
        """Klickt ``wert``, wenn nötig; sonst das Ergebnis, das den Weg beendet."""

    def zeit_um(self) -> bool:
        """Ob die Frist des Laufs abgelaufen ist."""

    def nicht_besucht(self, variante: Variante) -> Kombiergebnis:
        """Die Kombination als „nicht besucht: Zeitgrenze erreicht“."""

    def nach_zeitgrenze(self, abbruch: Abbruch) -> Abbruch | None:
        """Eine Sperre bei geschlossener Frist als ``zeitgrenze``; sonst ``None``."""


def fehlen(karte: Klickkarte, dimension: str) -> str:
    """Der Grund, wenn die Knöpfe einer Dimension fehlen."""
    selektor = karte.knoepfe[dimension].selektor
    return f"Knöpfe für {dimension} nicht gefunden ({selektor})"


def je_weiter(gang: Gang, weiter: Weiterschritt) -> None:
    """Je Kombination der Startseite: wählen, vorlesen, weiterklicken, Kacheln lesen."""
    vorn = [d for d in DIMENSIONEN if d != weiter.kacheln]
    angeboten = [gang.leser.angebotene(d, gang.lauf.struktur) for d in vorn]
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
        elif gang.zeit_um():
            ergebnisse = [gang.nicht_besucht(variante)]
        else:
            ergebnisse = _versuche(gang, weiter, ziel, variante, nummer > 0)
        auswahl = tuple(ziel[d] for d in DIMENSIONEN)
        for ergebnis in ergebnisse:
            gang.lauf.ergebnisse.append(
                ergebnis if ergebnis.auswahl else replace(ergebnis, auswahl=auswahl)
            )


def _versuche(
    gang: Gang,
    weiter: Weiterschritt,
    ziel: dict[str, str | None],
    variante: Variante,
    neu: bool,
) -> list[Kombiergebnis]:
    """Ein Start, ab dem zweiten in frischem Kontext; schließt die Frist mitten darin
    (Sperre bei abgelaufener Frist), heißt er „nicht besucht“, wie beim Klicken."""
    try:
        if neu:
            gang.oeffne_neu()
        return _start(gang, weiter, ziel, variante)
    except Abbruch as abbruch:
        if abbruch.status != LAUF_ZEITGRENZE and gang.nach_zeitgrenze(abbruch) is None:
            raise
        return [gang.nicht_besucht(variante)]


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
        return [Kombiergebnis(variante, NICHT_ERFASST, fehlen(gang.karte, fehlend[0]))]
    for dimension in vorn:
        ergebnis = gang.waehle(dimension, str(ziel[dimension]), variante)
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
    """Klickt den einen Weiter-Knopf und lädt die Folgeseite; sonst der Grund.

    Sperrt das Tor Dokument oder POST des Klicks (``sperre_des_klicks``) und kommt
    keine Folgeseite im Netz an, ist der Lauf gesperrt; eine fremde Sperre, etwa ein
    Zähler, zählt nicht.
    """
    seite, tor, wache = gang.seite, gang.tor, gang.wache
    wahl = waehle_knopf(seite, weiter.selektor, weiter.text)
    if wahl.knopf is None:
        return wahl.grund
    wache.warte_offen()
    adresse = ohne_anker(seite.url)
    marke = len(gang.lauf.verworfen)
    anfragen: list[Request] = []

    def merke(anfrage: Request) -> None:
        anfragen.append(anfrage)

    seite.on("request", merke)
    wache.geoeffnet = False
    tor.weiter_klick = True
    try:
        wahl.knopf.click(timeout=gang.frist_ms, no_wait_after=True)
        gewechselt = wache.warte(
            lambda: hat_gewechselt(seite, adresse), WEITER_FRIST_MS
        )
    except PlaywrightFehler as fehler:
        return f"{GRUND_KNOPF} nicht klickbar: {kurz(fehler)}"
    finally:
        tor.nur_lesen = True
        seite.remove_listener("request", merke)
    klick = {
        a.url: a.method
        for a in anfragen
        if a.resource_type == DOKUMENT or a.method == POST
    }
    gesperrt = sperre_des_klicks(gang.lauf.verworfen[marke:], klick)
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
        return [Kombiergebnis(variante, NICHT_ERFASST, fehlen(gang.karte, kachel))]
    ergebnisse: list[Kombiergebnis] = []
    selektor = gang.karte.knoepfe[kachel].selektor
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
            befund = diagnose(gang.seite, ergebnis, vorab, selektor)
            ergebnis = replace(ergebnis, diagnose=befund)
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


def _im_netz(adresse: str) -> bool:
    return urlsplit(adresse).scheme in WEBSCHEMATA


def _geladen(seite: Page) -> bool:
    try:
        return seite.evaluate(_GELADEN_JS) is True
    except PlaywrightFehler:
        return False
