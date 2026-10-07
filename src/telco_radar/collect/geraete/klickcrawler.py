"""Klick-Crawler: klickt jede angebotene Variante einer Produktseite, liest zweifach.

Gerüst aus Schritt 4 des Datenkonzepts Geräteradar (Abschnitt 8); noch ruft es kein
Tageslauf. Je Produktseite und Klick-Karte (``klickkarte``):

1. Der Crawler legt einen eigenen Browserkontext ohne Vorabladen an (``klickkontext``).
   Jede Anfrage geht durch das Tor (``klicktor``): robots.txt für jede Adresse und jedes
   Ziel einer Umleitung, Crawl-delay je Host. Gesperrte Adressen stehen in
   ``verworfen``, gescheiterte in ``gescheitert``. Fristen zählen ohne Crawl-delay
   (``klickwache``). Am Ende schließt er den Kontext.
2. Zeigen Hauptseite oder Preisantwort Bot-Schutz (202-Challenge, 4xx, 5xx,
   Challenge-Muster), antwortet die eigene Website mit HTTP 202 (``klickwache``) oder
   fehlt der Kanarienwert, ist der Abruf gestört und der Lauf endet sofort, ohne zweiten
   Versuch und ohne Umgehung (CLAUDE.md Regel 4). Sperrt robots.txt Seite oder
   Preisantwort, ist er gesperrt; scheitert die Preisanfrage, gestört.
3. Er liest die angebotenen Optionen je Dimension und klickt jede Kombination; nach
   jedem Klick liest er die Optionen neu und führt neu erschienene Werte mit. Eine feste
   Dimension hat keinen Knopf. Sind die Optionen einer Dimension eigene Adressen
   (``klickadressen``), lädt er jede Adresse der Startseite und klickt dort die übrigen
   Dimensionen; mit ``weiter`` liest er je Kombination der Startseite die Kacheln der
   Folgeseite (``klickweiter``). Eine gewählte Option klickt er nicht, eine gesperrte
   heißt erst ``nicht_angeboten``, wenn die Seite ruht. ``klickbedienung`` lehnt die
   Einwilligung ab und stellt die Vorbereitung her. Eine Antwort gehört nur zum Klick,
   nach dem ihre Anfrage hinausging, sonst ``nicht_erfasst``. Dann liest ``klicklesung``
   Antwort, Text, Markierung und Echo und macht einen Screenshot.
4. Je Kombination: erfasst, nicht_angeboten, nicht_erfasst oder befund; dazu der
   Strukturwächter je Lauf (beides in ``klicklauf``). Ist keine Kombination angeboten,
   ist der Lauf gestört.
5. Jede gelesene Kombination trägt ihren Beleg (``klickbeleg``): Screenshot, HAR der
   Preisantwort, Zeitpunkt aus ``uhr``, Fundstellen. Ohne Beleg ist ein Wert nicht
   gültig (``klicklauf.mit_beleg``), mit Beleg heißt er ``offen``, bis ``belegarchiv``
   ihn ablegt. ``wiedergabe`` nennt HAR-Belege, aus denen der Kontext Antworten ohne
   Netz abspielt (``route_from_har``); was sie nicht kennen, geht durch das Tor. Der
   Beleg hält nur die Preisantwort; eine Seitenkopie gehört nur in den privaten Bucket.

Den Browser startet der Aufrufer; dieses Modul setzt keine Tarnung, keinen Proxy und
keine fremde Kennung.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import replace
from datetime import datetime
from functools import partial
from pathlib import Path
from typing import TYPE_CHECKING

from playwright.sync_api import Error as PlaywrightFehler

from .klickadressen import Adresse, lies_adressen, ohne_adresse, pruefe_robots
from .klickbedienung import Bedienung
from .klickecho import LAUFZEIT, Variante, variante_aus
from .klickkarte import DIMENSIONEN, Adressen, Klickkarte
from .klickkontext import oeffne_sitzung
from .klicklauf import (
    BEFUND,
    ERFASST,
    LAUF_GELESEN,
    LAUF_GESPERRT,
    LAUF_GESTOERT,
    LAUF_ZEITGRENZE,
    NICHT_ANGEBOTEN,
    NICHT_ERFASST,
    Klicklauf,
    Kombiergebnis,
    ergebnisgrund,
    pruefe_struktur,
)
from .klicklesung import Leser
from .klickoptionen import Auswahl, Option, naechste, vereinige
from .klicktor import (
    GRUND_ZU_VIELE,
    HOECHSTE_UMLEITUNGEN,
    Schleuse,
    Tor,
    kurz,
)
from .klickwache import Abbruch, Wache
from .klickweiter import GRUND_NICHT_BESUCHT, Kontexte, je_weiter
from .robots import RobotsWaechter

if TYPE_CHECKING:
    from playwright.sync_api import (
        APIResponse,
        Browser,
        Locator,
        Page,
        Request,
        ViewportSize,
    )


log = logging.getLogger(__name__)

ANTWORT_FRIST_MS = 15000
HOECHSTE_KOMBINATIONEN = 200
FENSTER: ViewportSize = {"width": 1280, "height": 900}
GRUND_ZEIT = "Zeitgrenze erreicht"


def klicke_durch(
    browser: Browser,
    adresse: str,
    karte: Klickkarte,
    waechter: RobotsWaechter,
    uhr: Callable[[], datetime],
    *,
    schleuse: Schleuse,
    vorlauf: Klicklauf | None = None,
    frist_ms: int = ANTWORT_FRIST_MS,
    wiedergabe: tuple[Path, ...] = (),
    kennung: str | None = None,
    hoechste: int = HOECHSTE_KOMBINATIONEN,
    frist: Callable[[str], bool] | None = None,
    beobachter: Callable[[Request, APIResponse], str | None] | None = None,
    cookies: set[str] | None = None,
    modell: str | None = None,
) -> Klicklauf:
    """Klickt alle angebotenen Kombinationen auf ``adresse``; wirft nie.

    ``uhr`` liefert die Zeit des nächsten Abrufs für robots.txt; ``schleuse`` hält den
    Crawl-delay je Host über Läufe hinweg (``klicktor.Hostschleuse``). ``vorlauf`` ist
    der letzte Lauf derselben Seite (``klicklauf.pruefe_struktur``). Ein Abbruch steht
    als Status und Grund im Lauf; Kombinationen davor bleiben. ``kennung`` ist der
    User-Agent aus ``geraete_quellen.yaml``. Nach ``hoechste`` Kombinationen oder wenn
    ``frist`` vor einem Klick falsch ist, heißt die Kombination ``nicht_erfasst`` mit
    Grund ``nicht besucht``; schneidet die Frist welche ab oder verwirft sie eine
    Anfrage, ist der Lauf ``zeitgrenze``. ``beobachter`` sieht jede Antwort, ``cookies``
    die Cookie-Werte jedes Kontexts, ``modell`` füllt ``{modell}`` im Kanarienwert.
    """
    lauf = Klicklauf(anbieter=karte.anbieter, adresse=adresse)
    tor = Tor(waechter, uhr, schleuse, lauf)
    tor.beobachter = beobachter
    oeffne = partial(oeffne_sitzung, browser, tor, FENSTER, kennung)
    kontexte = Kontexte(partial(oeffne, wiedergabe=wiedergabe), tor, cookies)
    try:
        gang = _Gang(kontexte, karte, tor, frist_ms, lauf, hoechste, frist, modell)
        gang.laufe()
    except Abbruch as abbruch:
        lauf.status, lauf.grund = abbruch.status, abbruch.grund
    except PlaywrightFehler as fehler:
        lauf.status, lauf.grund = LAUF_GESTOERT, f"Browserfehler: {kurz(fehler)}"
        if tor.stoerung is not None:
            lauf.grund = tor.stoerung
    finally:
        kontexte.schliesse()
    bruch = pruefe_struktur(lauf, vorlauf)
    leer = ergebnisgrund(lauf.ergebnisse)
    for grund in (bruch, leer):
        if lauf.status == LAUF_GELESEN and grund is not None:
            lauf.status, lauf.grund = LAUF_GESTOERT, grund
    if lauf.status != LAUF_GELESEN:
        log.warning("Klick-Crawler %s %s: %s", karte.anbieter, adresse, lauf.grund)
    return lauf


class _Klickfehler(Exception):
    """Ein Knopf ließ sich nicht klicken."""


class _Gang:
    """Zustand eines Laufs: Seite, Karte, Tor, Leser, Wache und Grenzen."""

    def __init__(
        self,
        kontexte: Kontexte,
        karte: Klickkarte,
        tor: Tor,
        frist_ms: int,
        lauf: Klicklauf,
        hoechste: int,
        frist: Callable[[str], bool] | None,
        modell: str | None = None,
    ) -> None:
        self.karte, self.tor, self.lauf = karte, tor, lauf
        self.frist_ms, self.hoechste, self.frist = frist_ms, hoechste, frist
        self.kontexte, self.modell = kontexte, modell
        self._binde(kontexte.neu())
        self.geklickt = False
        self.nach_frist = 0
        self.unberuehrt = True

    def _binde(self, seite: Page) -> None:
        """Seite, Wache, Leser und Bedienung eines (neuen) Kontexts."""
        self.seite, karte, modell = seite, self.karte, self.modell
        self.wache = Wache(seite, karte, self.tor, self.lauf, self.frist_ms)
        self.leser = Leser(seite, karte, self.frist_ms, self.wache, modell)
        self.bedienung = Bedienung(seite, karte, self.wache, self.leser, modell)

    def laufe(self) -> None:
        self._oeffne_vor_frist(self.lauf.adresse)
        dimension = self.karte.adressdimension
        besucht: set[Auswahl] = set()
        adressen = None if dimension is None else self.karte.knoepfe[dimension].adressen
        if self.karte.weiter is not None:
            je_weiter(self, self.karte.weiter)
        elif dimension is None or adressen is None:
            self._klicke_alle(besucht)
        else:
            self._je_adresse(dimension, adressen, besucht)
        self.wache.warte_offen()
        self.wache.pruefe_tor()
        if self.nach_frist:
            grund = f"{GRUND_ZEIT}: {self.nach_frist} Kombinationen nicht besucht"
            raise Abbruch(LAUF_ZEITGRENZE, grund)

    def _je_adresse(
        self, dimension: str, adressen: Adressen, besucht: set[Auswahl]
    ) -> None:
        """Lädt jede Adresse der Dimension und klickt dort die übrigen durch."""
        karte = self.karte
        gelesen = lies_adressen(self.seite, adressen)
        self.lauf.struktur.knopf(any(a.grund is None for a in gelesen))
        if not gelesen:
            grund = f"Adressen für {dimension} nicht gefunden ({adressen.selektor})"
            gelesen = [Adresse(None, self.seite.url, grund)]
        for roh in gelesen:
            adresse = pruefe_robots(roh, self.tor, self.lauf)
            if adresse.wert is None or adresse.grund is not None:
                self.lauf.ergebnisse.append(ohne_adresse(dimension, adresse))
                continue
            self._nimm_karte(karte.mit_fest(dimension, adresse.wert))
            self._oeffne_vor_frist(adresse.url)
            self._klicke_alle(besucht)

    def _nimm_karte(self, karte: Klickkarte) -> None:
        self.karte = self.leser.karte = self.leser.quellen.karte = karte
        self.bedienung.karte = self.wache.karte = karte

    def _klicke_alle(self, besucht: set[Auswahl]) -> None:
        werte = {d: self._angebotene_werte(d) for d in DIMENSIONEN}
        while (auswahl := naechste(werte, besucht)) is not None:
            self.wache.pruefe_tor()
            besucht.add(auswahl)
            self.geklickt = False
            try:
                ergebnis = self._kombination(auswahl, len(besucht))
            except Abbruch as abbruch:
                if self._nach_zeitgrenze(abbruch) is None:
                    raise
                ergebnis = self._nicht_besucht(variante_aus(*auswahl))
            self.lauf.ergebnisse.append(replace(ergebnis, auswahl=auswahl))
            if self.geklickt:
                for d in DIMENSIONEN:
                    werte[d] = vereinige(werte[d], self._angebotene_werte(d))

    def _oeffne_vor_frist(self, ziel: str) -> None:
        try:
            self._oeffne(ziel)
        except Abbruch as abbruch:
            raise self._nach_zeitgrenze(abbruch) or abbruch from None

    def _nach_zeitgrenze(self, abbruch: Abbruch) -> Abbruch | None:
        """Eine Sperre bei geschlossener Frist als ``zeitgrenze``; sonst ``None``."""
        if abbruch.status != LAUF_GESPERRT or not self._zeit_um():
            return None
        return Abbruch(LAUF_ZEITGRENZE, f"{GRUND_ZEIT}: {abbruch.grund}")

    def _zeit_um(self) -> bool:
        return self.frist is not None and not self.frist(self.lauf.adresse)

    def _nicht_besucht(self, variante: Variante) -> Kombiergebnis:
        self.nach_frist += 1
        grund = f"{GRUND_NICHT_BESUCHT}: {GRUND_ZEIT}"
        return Kombiergebnis(variante, NICHT_ERFASST, grund)

    def _oeffne(self, ziel: str) -> None:
        self.wache.warte_offen()
        self.wache.geoeffnet = False
        marke = self.wache.marke()
        self.wache.geladen = marke[0]
        for _ in range(HOECHSTE_UMLEITUNGEN + 1):
            darf, grund = self.tor.darf(ziel)
            if not darf:
                raise Abbruch(LAUF_GESPERRT, grund)
            self.wache.lade(ziel)
            if self.tor.umleitung is None:
                break
            ziel = self.tor.umleitung
        else:
            raise Abbruch(LAUF_GESTOERT, f"Abruf gestört ({GRUND_ZU_VIELE})")
        self.wache.geoeffnet = True
        self.wache.pruefe_tor()
        darf, grund = self.tor.darf(self.seite.url)
        if not darf:
            raise Abbruch(LAUF_GESPERRT, grund)
        self.bedienung.pruefe_kanarie()
        quellen = self.karte.lesequellen
        if any(q.url_muster is not None for q in quellen):
            self.wache.nimm_antwort(marke)
        if not self.karte.je_klick:
            self.wache.warte_ruhe()
        self.bedienung.lehne_einwilligung_ab()
        self.unberuehrt = not self.bedienung.bereite_vor()

    def _angebotene_werte(self, dimension: str) -> list[str | None]:
        return self.leser.angebotene(dimension, self.lauf.struktur)

    def _kombination(self, auswahl: Auswahl, nummer: int) -> Kombiergebnis:
        ziel = dict(zip(DIMENSIONEN, auswahl, strict=True))
        variante = variante_aus(*auswahl)
        if nummer > self.hoechste:
            grund = f"{GRUND_NICHT_BESUCHT}: mehr als {self.hoechste} Kombinationen"
            return Kombiergebnis(variante, NICHT_ERFASST, grund)
        fehlend = [d for d in DIMENSIONEN if ziel[d] is None]
        if fehlend:
            self.lauf.struktur.knopf(False)
            return Kombiergebnis(variante, NICHT_ERFASST, self._fehlen(fehlend[0]))
        unlesbar = self.leser.unlesbar_in(ziel)
        if unlesbar is not None:
            return Kombiergebnis(variante, NICHT_ERFASST, unlesbar)
        if variante.laufzeit is None:
            grund = f"Laufzeit „{ziel[LAUFZEIT]}“ nicht lesbar"
            return Kombiergebnis(variante, NICHT_ERFASST, grund)
        for dimension in DIMENSIONEN:
            ergebnis = self._waehle(dimension, str(ziel[dimension]), variante)
            if ergebnis is not None:
                return ergebnis
        if self.bedienung.bereite_vor():
            self.geklickt = True
            self.unberuehrt = False
        if self.wache.ausstehend is not None:
            return Kombiergebnis(variante, NICHT_ERFASST, self.wache.ausstehend)
        struktur = self.lauf.struktur
        ergebnis = self.leser.lies(variante, ziel, struktur, self.unberuehrt)
        if ergebnis.status not in (ERFASST, BEFUND):
            return ergebnis
        return self.leser.belege(ergebnis, variante, self.lauf, self.tor.uhr())

    def _fehlen(self, dimension: str) -> str:
        selektor = self.karte.knoepfe[dimension].selektor
        return f"Knöpfe für {dimension} nicht gefunden ({selektor})"

    def _waehle(
        self, dimension: str, wert: str, variante: Variante
    ) -> Kombiergebnis | None:
        """Klickt ``wert``, wenn nötig; sonst das Ergebnis, das den Weg beendet.

        Eine gewählte Option bleibt, auch wenn die Seite sie sperrt. Eine gesperrte
        heißt erst ``nicht_angeboten``, wenn die Seite ruht; kommt sie nicht zur Ruhe,
        heißt die Kombination ``nicht_erfasst``.
        """
        if self.karte.knoepfe[dimension].fest is not None:
            return None
        optionen: list[Option] | None = self.leser.optionen(dimension)
        self.lauf.struktur.knopf(bool(optionen))
        if not optionen:
            return Kombiergebnis(variante, NICHT_ERFASST, self._fehlen(dimension))
        option = _option(optionen, wert)
        if option is not None and option.deaktiviert and not option.gewaehlt:
            optionen = self.wache.in_ruhe(lambda: self.leser.optionen(dimension))
            if optionen is None:
                grund = f"Seite kam für {dimension} {wert} nicht zur Ruhe"
                return Kombiergebnis(variante, NICHT_ERFASST, grund)
            option = _option(optionen, wert)
        if option is None:
            grund = f"Seite zeigt {dimension} {wert} in diesem Zustand nicht"
            return Kombiergebnis(variante, NICHT_ERFASST, grund)
        if option.gewaehlt:
            return None
        if option.deaktiviert:
            grund = f"Seite bietet {dimension} {wert} nicht an"
            return Kombiergebnis(variante, NICHT_ANGEBOTEN, grund)
        return self._klicke(dimension, optionen.index(option), variante)

    def _klicke(
        self, dimension: str, stelle: int, variante: Variante
    ) -> Kombiergebnis | None:
        selektor = self.karte.knoepfe[dimension].selektor
        if selektor is None:
            return Kombiergebnis(variante, NICHT_ERFASST, self._fehlen(dimension))
        self.wache.warte_offen()
        if self._zeit_um():
            return self._nicht_besucht(variante)
        marke = self.wache.marke()
        knopf = self.seite.locator(selektor).nth(stelle)
        try:
            self._druecke(knopf)
        except _Klickfehler as fehler:
            grund = f"Knopf für {dimension} nicht klickbar: {fehler}"
            return Kombiergebnis(variante, NICHT_ERFASST, grund)
        self.geklickt = True
        self.unberuehrt = False
        if self.karte.je_klick:
            self.wache.nimm_antwort(marke)
        else:
            self.wache.warte_ruhe()
        return None

    def _druecke(self, knopf: Locator) -> None:
        try:
            knopf.click(timeout=self.frist_ms)
        except PlaywrightFehler as fehler:
            raise _Klickfehler(kurz(fehler)) from fehler


def _option(optionen: list[Option], wert: str) -> Option | None:
    return next((o for o in optionen if o.wert == wert), None)
