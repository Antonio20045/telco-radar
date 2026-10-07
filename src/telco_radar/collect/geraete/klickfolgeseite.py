"""Folgeseite der Klick-Erkundung: ein benannter Klick in die Bestellstrecke.

Manche Anbieter zeigen Tarif oder Ratenlaufzeit erst nach dem ersten Schritt der
Bestellstrecke (Datenkonzept Abschnitt 13). Trägt eine Seite in
``config/klick_erkundung.yaml`` ``weiter`` (``klickziele.Weiter``), plant ``plane``
nach ihr einen eigenen Schritt mit eigener Nummer; ``folge_von`` nennt die
Ausgangsseite. ``Folgelauf`` öffnet die Ausgangsseite in einem frischen Kontext wie
jede Seite (``klickseite.Seitenlauf``: dasselbe Tor, robots.txt und Crawl-delay für
jede Anfrage, auch ein POST), lehnt die Einwilligung ab und klickt genau einmal: unter
den Treffern des Selektors genau einen sichtbaren mit dem erwarteten Text, ein ``a``
oder ``button`` (oder mit dieser Rolle), ohne neues Fenster und ohne Kauf-, Kassen- oder
Anmeldewort (``KAUFWORT``). Nur dieser Klick darf serverseitig Zustand ändern
(Warenkorb); kein Formular wird ausgefüllt. Ab dem Klick lässt das Tor nur GET und HEAD
durch (``klicktor.GRUND_NUR_LESEN``); allein die Anfragen des Klicks bis zur Navigation
der Hauptseite dürfen schreiben. Dann wartet er auf den Wechsel der Adresse, folgt
Umleitungen geprüft, wartet auf Laden und Ruhe und hält von der Folgeseite Inventar,
Preise, Seite und Mitschnitt fest, ohne Klick-Proben und ohne Kartenprobe
(``OHNE_PROBEN``).

Scheitern ist ein benannter Befund (``LAUF_BEFUND`` mit Grund), kein leeres Ergebnis:
der Knopf fehlt, ist nicht eindeutig, kein Knopf, nicht klickbar, öffnet ein neues
Fenster oder führt nirgends hin, oder die Folgeseite zeigt Anmeldung, Checkout oder
Zahlung (``streckenende``: Wort in Host oder Pfad, sichtbares Passwort-, Karten- oder
IBAN-Feld, Knopf „zahlungspflichtig bestellen“), geprüft nach dem Laden, nach der Ruhe
und noch einmal nach dem Festhalten. Verwirft das Tor das Ziel des Klicks oder seinen
POST (robots.txt), heißt die Folgeseite ``gesperrt``; Bot-Schutz heißt ``gestoert``,
und jede Störung des Tors beendet den Anbieter, auch nach einem Befund
(``klickseite.Seitenlauf``). Den Körper einer Antwort auf ein POST liest der Lauf schon
im Tor, auf Challenge-Muster wie jede Antwort, für den Mitschnitt und für die Kennungen
zum Schwärzen (``klickspur.geheime_werte``), weil die Seite gleich danach wechselt und
der Browser ihn dann nicht mehr herausgibt.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING
from urllib.parse import urlsplit

from playwright.sync_api import Error as PlaywrightFehler

from .klickinventar import Inventar
from .klickkartenprobe import SEITE_PROBIERBAR
from .klicklauf import LAUF_GESPERRT, LAUF_GESTOERT
from .klickproben import KLICK_FRIST_MS
from .klickseite import Fristschleuse, Seitenergebnis, Seitenlauf
from .klickspur import (
    HOECHSTE_ANTWORT,
    Eintrag,
    bot_verdacht,
    geheime_werte,
    ohne_geheimnisse,
)
from .klickstrecke import (
    DOKUMENT,
    FELDER_JS,
    GRUND_KNOPF,
    POST,
    WEBSCHEMATA,
    ohne_anker,
    sperre_des_klicks,
    streckenende,
    waehle_knopf,
)
from .klicktor import WARTE_TAKT_MS, kurz
from .klickwache import Abbruch
from .klickziele import Erkundungsziel, Seitenziel, Weiter
from .robots import RobotsWaechter

if TYPE_CHECKING:
    from playwright.sync_api import APIResponse, Browser, Locator, Request

log = logging.getLogger(__name__)

LAUF_BEFUND = "befund"
WEITER_FRIST_MS = 20_000
GRUND_AUSGANG = "Ausgangsseite"
OHNE_PROBEN = "Folgeseite: keine Klick-Proben"


@dataclass(frozen=True)
class Folge:
    """Woher eine Folgeseite kommt: Nummer der Ausgangsseite und ihr Weiter."""

    von: int
    weiter: Weiter


@dataclass(frozen=True)
class Schritt:
    """Ein Schritt der Erkundung: eine Seite oder die Folgeseite einer Seite."""

    nummer: int
    seite: Seitenziel
    folge: Folge | None = None


def plane(seiten: tuple[Seitenziel, ...]) -> list[Schritt]:
    """Jede Seite mit ihrer Nummer, direkt danach ihre Folgeseite mit neuer Nummer."""
    schritte: list[Schritt] = []
    naechste = len(seiten) + 1
    for nummer, seite in enumerate(seiten, 1):
        schritte.append(Schritt(nummer, seite))
        if seite.weiter is not None:
            schritte.append(Schritt(naechste, seite, Folge(nummer, seite.weiter)))
            naechste += 1
    return schritte


def ohne_ausgang(ausgang: Seitenergebnis | None, von: int) -> str | None:
    """Grund, wenn die Ausgangsseite nicht gelesen oder leer ist; sonst ``None``."""
    if ausgang is None:
        return f"{GRUND_AUSGANG} {von} nicht besucht"
    if ausgang.status in SEITE_PROBIERBAR:
        return None
    return f"{GRUND_AUSGANG} {von} {ausgang.status}: {ausgang.grund}"


def angabe(weiter: Weiter) -> dict:
    """Selektor und Text aus der Konfiguration, wie sie im Index stehen."""
    return {"selektor": weiter.selektor, "text": weiter.text}


class Folgelauf(Seitenlauf):
    """Ausgangsseite öffnen, einmal weiterklicken, die Folgeseite festhalten."""

    def __init__(
        self,
        browser: Browser,
        ziel: Erkundungsziel,
        seite: Seitenziel,
        waechter: RobotsWaechter,
        uhr: Callable[[], datetime],
        schleuse: Fristschleuse,
        weiter: Weiter,
    ) -> None:
        super().__init__(browser, ziel, seite, waechter, uhr, schleuse)
        self.weiter = weiter
        self.protokoll = angabe(weiter)
        self.ergebnis.weiter = self.protokoll
        self.ergebnis.klick_vermerk = OHNE_PROBEN
        self.koerper: dict[tuple[str, str], bytes] = {}

    def _beobachte(self, anfrage: Request, antwort: APIResponse) -> str | None:
        """Wie jede Seite; dazu Körper und Challenge-Muster der Antwort auf ein POST."""
        grund = super()._beobachte(anfrage, antwort)
        if grund is not None or anfrage.method != POST:
            return grund
        try:
            koerper = antwort.body()
        except PlaywrightFehler as fehler:
            log.warning(
                "Folgeseite: Körper von %s nicht gelesen: %s", anfrage.url, kurz(fehler)
            )
            return None
        url = ohne_geheimnisse(anfrage.url)
        self.koerper[(POST, url)] = koerper
        eintrag = Eintrag(0, POST, url, anfrage.resource_type, antwort.status)
        text = koerper[:HOECHSTE_ANTWORT].decode("utf-8", errors="replace")
        self.ergebnis.cookies.update(geheime_werte(text))
        return bot_verdacht(eintrag, text, self.adresse)

    def _uebernimm(self) -> None:
        """Wie jede Seite; Körper, die der Browser nicht mehr hergab, aus dem Tor."""
        super()._uebernimm()
        for satz in self.ergebnis.mitschnitt:
            koerper = self.koerper.get((satz["methode"], satz["url"]))
            if koerper is None or satz.get("koerper") is not None:
                continue
            satz.pop("grund", None)
            satz["groesse"] = len(koerper)
            satz["gekuerzt"] = len(koerper) > HOECHSTE_ANTWORT
            satz["koerper"] = koerper[:HOECHSTE_ANTWORT].decode(
                "utf-8", errors="replace"
            )

    def _vor_der_lesung(self) -> None:
        """Klickt den einen Weiter-Knopf und folgt ihm bis zur geladenen Folgeseite."""
        knopf = self._knopf()
        self.protokoll["von"] = ohne_geheimnisse(self.seite.url)
        gescheitert = len(self.lauf.gescheitert)
        self.tor.weiter_klick = True
        try:
            self._klicke(knopf)
        finally:
            self.tor.nur_lesen = True
        if self.tor.umleitung is not None:
            self._folge(self.tor.umleitung)
        elif urlsplit(self.seite.url).scheme not in WEBSCHEMATA:
            ohne = self.lauf.gescheitert[gescheitert:]
            grund = ohne[0].grund if ohne else self.seite.url
            raise Abbruch(LAUF_GESTOERT, f"Folgeseite nicht geladen ({grund})")
        else:
            self.pruefe_geladen()
        self.protokoll["nach"] = ohne_geheimnisse(self.seite.url)
        self._pruefe_strecke()
        self.ergebnis.ruhe = self.ruhe()
        self._pruefe_strecke()

    def _nach_der_lesung(self, inventar: Inventar) -> None:
        """Keine Klick-Proben auf ``inventar``; zeigt die Seite jetzt Anmeldung, Kasse
        oder Zahlung, ist sie ein Befund."""
        try:
            self._pruefe_strecke()
        except Abbruch as abbruch:
            self._halte_an(abbruch)

    def _pruefe_strecke(self) -> None:
        """Wirft einen Befund, wenn Adresse oder Seite das Streckenende zeigen."""
        ende = streckenende(self.seite.url, self.seite.evaluate(FELDER_JS))
        if ende is not None:
            raise Abbruch(LAUF_BEFUND, f"Folgeseite zeigt {ende}")

    def _klicke(self, knopf: Locator) -> None:
        """Klickt einmal und wartet, bis die Adresse wechselt."""
        adresse = ohne_anker(self.seite.url)
        marke, verworfen = self.spur.marke(), len(self.lauf.verworfen)
        fenster = len(self.seite.context.pages)
        try:
            knopf.click(timeout=KLICK_FRIST_MS, no_wait_after=True)
        except PlaywrightFehler as fehler:
            grund = f"{GRUND_KNOPF} nicht klickbar: {kurz(fehler)}"
            raise Abbruch(LAUF_BEFUND, grund) from fehler
        self._warte_auf_wechsel(adresse, marke, verworfen, fenster)

    def _knopf(self) -> Locator:
        """Der eine sichtbare Treffer mit dem erwarteten Text; sonst ein Befund."""
        wahl = waehle_knopf(self.seite, self.weiter.selektor, self.weiter.text)
        if wahl.treffer is not None:
            self.protokoll.update(treffer=wahl.treffer, sichtbar=wahl.sichtbar)
        if wahl.text is not None:
            self.protokoll["geklickt"] = wahl.text
        if wahl.knopf is None:
            raise Abbruch(LAUF_BEFUND, str(wahl.grund))
        return wahl.knopf

    def _warte_auf_wechsel(
        self, adresse: str, marke: int, verworfen: int, fenster: int
    ) -> None:
        """Wartet, bis die Adresse wechselt; sonst gesperrt oder ein Befund."""
        frist = WEITER_FRIST_MS + round(2000 * self.schleuse.abstand(adresse))
        for _ in range(frist // WARTE_TAKT_MS):
            self.pruefe()
            gesperrt = self._gesperrt_seit(marke, verworfen)
            if gesperrt is not None:
                raise Abbruch(LAUF_GESPERRT, f"{GRUND_KNOPF}: {gesperrt}")
            if self.tor.umleitung is not None:
                return
            if ohne_anker(self.seite.url) != adresse:
                return
            if len(self.seite.context.pages) > fenster:
                raise Abbruch(LAUF_BEFUND, f"{GRUND_KNOPF} öffnete ein neues Fenster")
            self.seite.wait_for_timeout(WARTE_TAKT_MS)
        grund = (
            f"{GRUND_KNOPF} führt nirgends hin: Adresse nach {frist // 1000} s gleich"
        )
        raise Abbruch(LAUF_BEFUND, grund)

    def _gesperrt_seit(self, marke: int, verworfen: int) -> str | None:
        """Ziel oder POST des Klicks, wenn das Tor sie verwarf, nicht wegen
        ``GRUND_NUR_LESEN``; sonst ``None``."""
        klick = {
            e.url: e.methode
            for e in self.spur.seit(marke)
            if e.art == DOKUMENT or e.methode == POST
        }
        verworfen_seit = self.lauf.verworfen[verworfen:]
        return sperre_des_klicks(verworfen_seit, klick, ohne_geheimnisse)
