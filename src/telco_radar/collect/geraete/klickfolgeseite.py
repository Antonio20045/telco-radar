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
der Hauptseite dürfen schreiben. Dann wartet er auf den Wechsel der Adresse
(``klickstrecke.hat_gewechselt``: bei einer Umleitung erst, wenn die Leerseite des Tors
angekommen und geladen ist, sonst unterbräche sie das Laden des Ziels), folgt
Umleitungen geprüft, wartet auf Laden und Ruhe und hält von der Folgeseite Inventar,
Preise, Seite und Mitschnitt fest, ohne Kartenprobe und ohne Klick-Proben
(``OHNE_PROBEN``), außer ``weiter.proben`` nennt Optionen: dann klickt er nach dem
Festhalten höchstens ``HOECHSTE_PROBEN`` nicht gewählte davon (Vodafone: die Tarife der
Tarifauswahl), ohne Kauf- oder Anmeldewort, nur noch mit GET und HEAD, und hält je Probe
Anfragen, geänderte €-Texte und die Übernahme der Wahl fest wie die Startseite.

Scheitern ist ein benannter Befund (``LAUF_BEFUND`` mit Grund), kein leeres Ergebnis:
der Knopf fehlt, ist nicht eindeutig, kein Knopf, nicht klickbar, öffnet ein neues
Fenster oder führt nirgends hin, oder die Folgeseite zeigt Anmeldung, Checkout oder
Zahlung (``streckenende``: Wort in Host oder Pfad, sichtbares Passwort-, Karten- oder
IBAN-Feld, Knopf „zahlungspflichtig bestellen“), geprüft nach dem Laden, nach der Ruhe
und noch einmal nach dem Festhalten. Verwirft das Tor das Ziel des Klicks oder seinen
POST (robots.txt), heißt die Folgeseite ``gesperrt``, festgehalten erst, wenn die
Fehlerseite des Browsers da ist (``FEHLERSEITE_FRIST_MS``); Bot-Schutz heißt
``gestoert``, und jede Störung des Tors beendet den Anbieter, auch nach einem Befund
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

from .klickinventar import Inventar, preistexte
from .klickkartenprobe import SEITE_PROBIERBAR
from .klicklauf import LAUF_GESPERRT, LAUF_GESTOERT
from .klickproben import (
    AKTIONSWORT,
    JA,
    KLICK_FRIST_MS,
    NEIN,
    UNBEKANNT,
    unterschiede,
)
from .klickseite import ABGELAUFEN, Fristschleuse, Seitenergebnis, Seitenlauf
from .klickspur import (
    HOECHSTE_ANTWORT,
    Eintrag,
    als_daten,
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
    hat_gewechselt,
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
FEHLERSEITE_FRIST_MS = 5_000
GRUND_AUSGANG = "Ausgangsseite"
GRUND_LEERSEITE = "Leerseite der Umleitung"
OHNE_PROBEN = "Folgeseite: keine Klick-Proben"
MIT_PROBEN = "Folgeseite: Proben auf"
HOECHSTE_PROBEN = 6
PROBENART = "tarif"
_WAHL_JS = """e => {
  const i = e.matches("input") ? e
    : (e.control || (e.parentElement && e.parentElement.querySelector("input")));
  return i ? {gewaehlt: i.checked === true, wert: i.value || null} : null;
}"""


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
    """Selektor, Text und, wenn angegeben, Proben aus der Konfiguration, wie sie im
    Index stehen."""
    daten = {"selektor": weiter.selektor, "text": weiter.text}
    if weiter.proben is not None:
        daten["proben"] = weiter.proben
    return daten


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
        self.ergebnis.klick_vermerk = (
            OHNE_PROBEN if weiter.proben is None else f"{MIT_PROBEN} {weiter.proben}"
        )
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
            if not self._warte_geladen():
                raise Abbruch(LAUF_GESTOERT, f"{GRUND_LEERSEITE} nicht geladen")
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
        """Keine Klick-Proben auf ``inventar``, nur auf den Optionen von
        ``weiter.proben``; zeigt die Seite Anmeldung, Kasse oder Zahlung, ist sie ein
        Befund. Eine erreichte Zeitgrenze beendet nur die Proben."""
        try:
            self._pruefe_strecke()
            if self.weiter.proben is not None:
                self._proben(self.weiter.proben)
                self._pruefe_strecke()
        except Abbruch as abbruch:
            if self.weiter.proben is not None:
                self.ergebnis.klick_vermerk = abbruch.grund
            if abbruch.status != ABGELAUFEN:
                self._halte_an(abbruch)

    def _proben(self, selektor: str) -> None:
        """Klickt höchstens ``HOECHSTE_PROBEN`` nicht gewählte Optionen von
        ``selektor``, ohne Kauf- oder Anmeldewort; das Tor lässt danach nur GET und
        HEAD durch. Wechselt die Seite, enden die Proben dort."""
        ziele = self.seite.locator(selektor)
        for stelle in range(min(ziele.count(), HOECHSTE_PROBEN)):
            self.pruefe()
            ort = ziele.nth(stelle)
            wahl = ort.evaluate(_WAHL_JS) or {}
            text = " ".join((ort.text_content() or "").split())
            if wahl.get("gewaehlt") or AKTIONSWORT.search(text):
                continue
            probe = self._probe(ort, selektor, stelle, text, wahl.get("wert"))
            if probe["navigiert"] is not None or probe["umleitung"] is not None:
                return

    def _probe(
        self, ort: Locator, selektor: str, stelle: int, text: str, wert: str | None
    ) -> dict:
        vorher, adresse, marke = (
            preistexte(self.seite),
            self.seite.url,
            self.spur.marke(),
        )
        probe: dict = {
            "art": PROBENART,
            "pfad": f"{selektor} >> nth={stelle}",
            "text": text,
            "wert": wert,
            "fehler": None,
            "navigiert": None,
            "umleitung": None,
        }
        self.ergebnis.klicks.append(probe)
        try:
            ort.click(timeout=KLICK_FRIST_MS)
        except PlaywrightFehler as fehler:
            probe["fehler"] = kurz(fehler)
        try:
            self.pruefe()
            probe["ruhe"] = self.ruhe()
        finally:
            probe["anfragen"] = als_daten(self.spur.seit(marke))
        umleitung = self.umgeleitet()
        probe["umleitung"] = ohne_geheimnisse(umleitung) if umleitung else None
        if self.seite.url != adresse:
            probe["navigiert"] = ohne_geheimnisse(self.seite.url)
            return probe
        probe["preise_geaendert"] = unterschiede(vorher, preistexte(self.seite))
        jetzt = ort.evaluate(_WAHL_JS) if ort.count() else None
        probe["uebernommen"] = (
            UNBEKANNT if jetzt is None else JA if jetzt["gewaehlt"] else NEIN
        )
        return probe

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
        """Wartet, bis die Adresse wechselt (``hat_gewechselt``, auch nach einer
        Umleitung); sonst gesperrt oder ein Befund."""
        frist = WEITER_FRIST_MS + round(2000 * self.schleuse.abstand(adresse))
        for _ in range(frist // WARTE_TAKT_MS):
            self.pruefe()
            gesperrt = self._gesperrt_seit(marke, verworfen)
            if gesperrt is not None:
                self._warte_auf_fehlerseite(adresse, marke)
                raise Abbruch(LAUF_GESPERRT, f"{GRUND_KNOPF}: {gesperrt}")
            if hat_gewechselt(self.seite, adresse):
                return
            if len(self.seite.context.pages) > fenster:
                raise Abbruch(LAUF_BEFUND, f"{GRUND_KNOPF} öffnete ein neues Fenster")
            self.seite.wait_for_timeout(WARTE_TAKT_MS)
        grund = (
            f"{GRUND_KNOPF} führt nirgends hin: Adresse nach {frist // 1000} s gleich"
        )
        raise Abbruch(LAUF_BEFUND, grund)

    def _warte_auf_fehlerseite(self, adresse: str, marke: int) -> None:
        """Sperrt das Tor eine Navigation des Klicks, zeigt der Browser danach eine
        Fehlerseite; liest die Erkundung die Seite vorher, scheitert das Lesen
        („page is navigating“). Wartet auf sie, höchstens ``FEHLERSEITE_FRIST_MS``."""
        if not any(e.art == DOKUMENT for e in self.spur.seit(marke)):
            return
        for _ in range(FEHLERSEITE_FRIST_MS // WARTE_TAKT_MS):
            if hat_gewechselt(self.seite, adresse):
                self._warte_geladen()
                return
            self.seite.wait_for_timeout(WARTE_TAKT_MS)

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
