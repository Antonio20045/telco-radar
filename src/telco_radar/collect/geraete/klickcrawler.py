"""Klick-Crawler: klickt jede angebotene Variante einer Produktseite, liest zweifach.

Gerüst aus Schritt 4 des Datenkonzepts Geräteradar (Abschnitt 8); noch ruft es kein
Tageslauf. Je Produktseite und Klick-Karte (``klickkarte``):

1. Der Crawler legt einen eigenen Browserkontext ohne Vorabladen an (``klickkontext``).
   Jede Anfrage geht durch das Tor (``klicktor``): robots.txt für jede Adresse und jedes
   Ziel einer Umleitung, Crawl-delay je Host für jede Anfrage. Gesperrte Adressen gehen
   nicht hinaus und stehen in ``verworfen``, gescheiterte in ``gescheitert``. Fristen
   zählen nur Zeit, in der niemand auf den Crawl-delay wartet (``klickwache``). Nach dem
   Lauf verlässt er die Seite und schließt den Kontext.
2. Zeigt eine Hauptseite Bot-Schutz (202-Challenge, 4xx, 5xx, Challenge-Muster), beim
   Öffnen oder mitten im Lauf, oder die Preisantwort, oder fehlt der Kanarienwert, ist
   der Abruf gestört und der Lauf endet sofort: kein zweiter Versuch, keine Umgehung
   (CLAUDE.md Regel 4). Sperrt robots.txt die Seite oder ihre Preisantwort, ist der Lauf
   gesperrt; scheitert die Preisanfrage, ist er gestört.
3. Er liest die angebotenen Optionen je Dimension und klickt jede Kombination; nach
   jedem Klick liest er die Optionen neu und führt neu erschienene Werte mit. Eine
   gewählte Option klickt er nicht; eine gesperrte heißt erst ``nicht_angeboten``, wenn
   die Seite ruht (keine Anfrage läuft, zwei gleiche Lesungen). Eine Antwort gehört nur
   zu dem Klick, nach dem ihre Anfrage hinausging; bleibt eine Anfrage über die Frist
   offen, heißt die Kombination ``nicht_erfasst``, und vor dem nächsten Klick wie am
   Ende wartet er sie ab oder bricht den Lauf als gestört ab. Dann liest ``klicklesung``
   Antwort, Text, Markierung und Echo und macht einen Screenshot.
4. Je Kombination: erfasst, nicht_angeboten, nicht_erfasst oder befund; dazu der
   Strukturwächter je Lauf (beides in ``klicklauf``). Ist keine Kombination angeboten,
   ist der Lauf gestört.
5. Jede gelesene Kombination trägt ihren Beleg (``klickbeleg``): Screenshot, HAR der
   Preisantwort, Zeitpunkt aus ``uhr``, Fundstellen. Ohne Beleg ist ein Wert nicht
   gültig (``klicklauf.mit_beleg``), mit Beleg heißt er ``offen``, bis
   ``belegarchiv`` ihn ablegt. ``wiedergabe`` nennt HAR-Belege, aus denen der
   Kontext Antworten ohne Netz abspielt (``route_from_har``); was sie nicht kennen,
   geht wie sonst durch das Tor. Grenze: der Beleg hält nur die Preisantwort, die
   Produktseite kommt weiter aus dem Netz; ist sie weg, liest die Wiedergabe nichts.
   Eine Seitenkopie gehört nur in den privaten Bucket, nie ins Repo.

Den Browser startet der Aufrufer; dieses Modul setzt keine Tarnung, keinen Proxy und
keine fremde Kennung.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from playwright.sync_api import Error as PlaywrightFehler

from .klickbeleg import Belegquelle, baue_beleg, kopie_aus
from .klickecho import LAUFZEIT, Variante, variante_aus
from .klickkarte import DIMENSIONEN, Klickkarte
from .klickkontext import Sitzung, cookie_werte, oeffne_sitzung, schliesse
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
    mit_beleg,
    pruefe_struktur,
)
from .klicklesung import Leser
from .klickoptionen import Auswahl, Option, angebotene_werte, naechste, vereinige
from .klicktor import (
    GRUND_ZU_VIELE,
    HOECHSTE_UMLEITUNGEN,
    SEITEN_FRIST_MS,
    Schleuse,
    Tor,
    kurz,
)
from .klickwache import Abbruch, Wache
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
GRUND_NICHT_BESUCHT = "nicht besucht"
GRUND_ZEIT = "Zeitgrenze erreicht"
_GELADEN_JS = "() => document.readyState === 'complete'"


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
) -> Klicklauf:
    """Klickt alle angebotenen Kombinationen auf ``adresse``; wirft nie.

    ``uhr`` liefert die Zeit des nächsten Abrufs für robots.txt; ``schleuse`` hält den
    Crawl-delay je Host über Läufe hinweg (``klicktor.Hostschleuse``, eine je
    Anbieterlauf). ``vorlauf`` ist der letzte Lauf derselben Seite; sein Bezug für den
    Strukturwächter wandert weiter (``klicklauf.pruefe_struktur``). Ein Abbruch steht
    als Status und Grund im Lauf, die Kombinationen bis dahin bleiben erhalten.
    ``kennung`` ist der User-Agent aus ``geraete_quellen.yaml``. Nach ``hoechste``
    Kombinationen klickt der Lauf nicht mehr, ebenso wenn ``frist`` vor einem Klick für
    ``adresse`` falsch ist (``klickseite.Fristschleuse.offen``, die Grenze der
    Schleuse): die Kombination heißt ``nicht_erfasst`` mit Grund ``nicht besucht``. Hat
    die Frist welche abgeschnitten oder eine Anfrage verworfen, ist der Lauf
    ``zeitgrenze``. ``beobachter`` sieht im Tor jede Antwort (``Tor.beobachter``);
    in ``cookies`` landen beim Schließen die Cookie-Werte des Kontexts.
    """
    lauf = Klicklauf(anbieter=karte.anbieter, adresse=adresse)
    tor = Tor(waechter, uhr, schleuse, lauf)
    tor.beobachter = beobachter
    sitzung: Sitzung | None = None
    try:
        sitzung = oeffne_sitzung(browser, tor, FENSTER, kennung, wiedergabe=wiedergabe)
        gang = _Gang(sitzung.seite, karte, tor, frist_ms, lauf, hoechste, frist)
        gang.laufe()
    except Abbruch as abbruch:
        lauf.status, lauf.grund = abbruch.status, abbruch.grund
    except PlaywrightFehler as fehler:
        lauf.status, lauf.grund = LAUF_GESTOERT, f"Browserfehler: {kurz(fehler)}"
        if tor.stoerung is not None:
            lauf.grund = tor.stoerung
    finally:
        tor.geschlossen = True
        if cookies is not None:
            cookies.update(cookie_werte(sitzung))
        schliesse(sitzung)
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
        seite: Page,
        karte: Klickkarte,
        tor: Tor,
        frist_ms: int,
        lauf: Klicklauf,
        hoechste: int,
        frist: Callable[[str], bool] | None,
    ) -> None:
        self.seite, self.karte, self.tor, self.lauf = seite, karte, tor, lauf
        self.frist_ms, self.hoechste, self.frist = frist_ms, hoechste, frist
        self.leser = Leser(seite, karte, frist_ms)
        self.wache = Wache(seite, karte, tor, lauf, frist_ms)
        self.geklickt = False
        self.nach_frist = 0

    def laufe(self) -> None:
        try:
            self._oeffne()
        except Abbruch as abbruch:
            raise self._nach_zeitgrenze(abbruch) or abbruch from None
        werte = {d: self._angebotene_werte(d) for d in DIMENSIONEN}
        besucht: set[Auswahl] = set()
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
        self.wache.warte_offen()
        self.wache.pruefe_tor()
        if self.nach_frist:
            grund = f"{GRUND_ZEIT}: {self.nach_frist} Kombinationen nicht besucht"
            raise Abbruch(LAUF_ZEITGRENZE, grund)

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

    def _oeffne(self) -> None:
        ziel = self.lauf.adresse
        for _ in range(HOECHSTE_UMLEITUNGEN + 1):
            darf, grund = self.tor.darf(ziel)
            if not darf:
                raise Abbruch(LAUF_GESPERRT, grund)
            self._lade(ziel)
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
        kanarie = self.karte.kanarie
        ort = self.seite.locator(kanarie.selektor)
        if kanarie.enthaelt not in self.leser.text(ort, kanarie.enthaelt):
            self.wache.pruefe_tor()
            grund = f"Kanarienwert fehlt: {kanarie.selektor} ohne „{kanarie.enthaelt}“"
            raise Abbruch(LAUF_GESTOERT, grund)
        self.wache.nimm_antwort((0, 0, 0))

    def _lade(self, ziel: str) -> None:
        """Öffnet ``ziel``; die Frist bis zur Antwort trägt den Crawl-delay mit."""
        self.tor.umleitung = None
        _, verworfen, gescheitert = self.wache.marke()
        frist = SEITEN_FRIST_MS + round(1000 * self.tor.schleuse.abstand(ziel))
        try:
            self.seite.goto(ziel, wait_until="commit", timeout=frist)
        except PlaywrightFehler as fehler:
            self.lauf.http_status = self.tor.haupt_status
            self.wache.pruefe_tor()
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
        if self.tor.umleitung is None and not self.wache.warte(
            self._geladen, SEITEN_FRIST_MS
        ):
            grund = f"Seite nach {SEITEN_FRIST_MS} ms nicht geladen"
            raise Abbruch(LAUF_GESTOERT, grund)

    def _geladen(self) -> bool:
        try:
            return self.seite.evaluate(_GELADEN_JS) is True
        except PlaywrightFehler:
            return False

    def _angebotene_werte(self, dimension: str) -> list[str | None]:
        optionen = self.leser.optionen(dimension)
        self.lauf.struktur.knopf(bool(optionen))
        return angebotene_werte(optionen)

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
        if variante.laufzeit is None:
            grund = f"Laufzeit „{ziel[LAUFZEIT]}“ nicht lesbar"
            return Kombiergebnis(variante, NICHT_ERFASST, grund)
        for dimension in DIMENSIONEN:
            ergebnis = self._waehle(dimension, str(ziel[dimension]), variante)
            if ergebnis is not None:
                return ergebnis
        if self.wache.ausstehend is not None:
            return Kombiergebnis(variante, NICHT_ERFASST, self.wache.ausstehend)
        antwort = self.wache.antwort
        ergebnis = self.leser.lies(variante, ziel, antwort, self.lauf.struktur)
        if ergebnis.status not in (ERFASST, BEFUND):
            return ergebnis
        quelle = Belegquelle(
            anbieter=self.karte.anbieter,
            adresse=self.lauf.adresse,
            seite=self.seite.url,
            http_status=self.lauf.http_status,
            variante=variante,
            status=ergebnis.status,
            werte=ergebnis.werte,
            text=ergebnis.text,
            screenshot_png=ergebnis.screenshot_png,
            antwort=kopie_aus(antwort),
        )
        paket, ohne = baue_beleg(quelle, self.karte, self.tor.uhr())
        return mit_beleg(ergebnis, paket, ohne)

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
        self.wache.warte_offen()
        if self._zeit_um():
            return self._nicht_besucht(variante)
        marke = self.wache.marke()
        knopf = self.seite.locator(self.karte.knoepfe[dimension].selektor).nth(stelle)
        try:
            self._druecke(knopf)
        except _Klickfehler as fehler:
            grund = f"Knopf für {dimension} nicht klickbar: {fehler}"
            return Kombiergebnis(variante, NICHT_ERFASST, grund)
        self.geklickt = True
        self.wache.nimm_antwort(marke)
        return None

    def _druecke(self, knopf: Locator) -> None:
        try:
            knopf.click(timeout=self.frist_ms)
        except PlaywrightFehler as fehler:
            raise _Klickfehler(kurz(fehler)) from fehler


def _option(optionen: list[Option], wert: str) -> Option | None:
    return next((o for o in optionen if o.wert == wert), None)
