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
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING
from urllib.parse import unquote, urldefrag, urlsplit

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
from .klicktor import GRUND_NUR_LESEN, WARTE_TAKT_MS, kurz
from .klickwache import Abbruch
from .klickziele import Erkundungsziel, Seitenziel, Weiter
from .robots import RobotsWaechter

if TYPE_CHECKING:
    from playwright.sync_api import APIResponse, Browser, Locator, Request

log = logging.getLogger(__name__)

LAUF_BEFUND = "befund"
WEITER_FRIST_MS = 20_000
HOECHSTE_TREFFER = 20
GRUND_KNOPF = "Weiter-Knopf"
GRUND_AUSGANG = "Ausgangsseite"
OHNE_PROBEN = "Folgeseite: keine Klick-Proben"
WEBSCHEMATA = frozenset({"http", "https"})
KNOPF_TAGS = frozenset({"a", "button"})
KNOPF_ROLLEN = frozenset({"button", "link"})
NEUES_FENSTER = "_blank"
POST = "POST"
DOKUMENT = "document"
KAUFWORT = re.compile(
    r"kaufen|bestell|kasse|bezahl|anmeld|einlogg|login|registrier|checkout", re.I
)
_RAND = r"(?<![a-z0-9])(?:{})(?![a-z0-9])"
STRECKENENDE = {
    "Anmeldung": re.compile(
        _RAND.format(
            "login|log-in|signin|sign-in|anmelden|anmeldung|einloggen"
            "|authentifizierung|auth"
        ),
        re.I,
    ),
    "Checkout": re.compile(
        _RAND.format(
            "checkout|check-out|kasse|bestellabschluss|bestelluebersicht"
            "|bestellübersicht"
        ),
        re.I,
    ),
    "Zahlung": re.compile(
        _RAND.format("payment|zahlung|zahlungsart|zahlungsdaten|bezahlen|bezahlung"),
        re.I,
    ),
}
FELDER_JS = """() => {
  const sichtbar = (e) => !!(e.offsetWidth || e.offsetHeight
    || e.getClientRects().length);
  const zeigt = (wahl) => [...document.querySelectorAll(wahl)].some(sichtbar);
  if (zeigt('input[type="password"]')) return ["Anmeldung", "Passwortfeld"];
  if (zeigt('input[autocomplete^="cc-"], input[name*="iban" i], input[id*="iban" i]'))
    return ["Zahlung", "Karten- oder IBAN-Feld"];
  const kasse = /(?:zahlungs|kosten)pflichtig\\s+bestellen/i;
  const knoepfe = document.querySelectorAll(
    'button, input[type="submit"], [role="button"]');
  for (const k of knoepfe) {
    if (sichtbar(k) && kasse.test(k.innerText || k.value || ""))
      return ["Checkout", "Knopf „" + (k.innerText || k.value).trim() + "“"];
  }
  return null;
}"""
KNOPF_JS = """(e) => ({tag: e.tagName.toLowerCase(), rolle: e.getAttribute("role"),
  text: (e.innerText || e.textContent || "").replace(/\\s+/g, " ").trim(),
  ziel: e.getAttribute("target")})"""


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


def streckenende(adresse: str, felder: list[str] | None) -> str | None:
    """Was die Folgeseite als Anmeldung, Checkout oder Zahlung zeigt, mit Beleg."""
    teile = urlsplit(adresse)
    ort = unquote(f"{teile.hostname or ''}{teile.path}")
    for art, muster in STRECKENENDE.items():
        treffer = muster.search(ort)
        if treffer is not None:
            return f"{art} (Adresse: {treffer[0]})"
    return None if felder is None else f"{felder[0]} ({felder[1]})"


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
        adresse = _ohne_anker(self.seite.url)
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
        treffer = self.seite.locator(self.weiter.selektor)
        try:
            anzahl = treffer.count()
            sichtbar = [
                treffer.nth(i)
                for i in range(min(anzahl, HOECHSTE_TREFFER))
                if treffer.nth(i).is_visible()
            ]
            passend = [(k, k.evaluate(KNOPF_JS)) for k in sichtbar]
        except PlaywrightFehler as fehler:
            grund = f"{GRUND_KNOPF}: Selektor nicht lesbar ({kurz(fehler)})"
            raise Abbruch(LAUF_BEFUND, grund) from fehler
        if self.weiter.text is not None:
            gesucht = _knapp(self.weiter.text)
            passend = [(k, d) for k, d in passend if gesucht in _knapp(d["text"])]
        self.protokoll.update(treffer=anzahl, sichtbar=len(sichtbar))
        if len(passend) != 1:
            wie = "nicht gefunden" if not passend else "nicht eindeutig"
            grund = (
                f"{GRUND_KNOPF} {wie}: {anzahl} Treffer, {len(sichtbar)} sichtbar,"
                f" {len(passend)} passend"
            )
            raise Abbruch(LAUF_BEFUND, grund)
        knopf, daten = passend[0]
        self.protokoll["geklickt"] = daten["text"]
        mangel = _kein_weiter(daten)
        if mangel is not None:
            raise Abbruch(LAUF_BEFUND, f"{GRUND_KNOPF} „{daten['text']}“ {mangel}")
        return knopf

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
            if _ohne_anker(self.seite.url) != adresse:
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
        neu = {
            ohne_geheimnisse(v.url): v.grund
            for v in self.lauf.verworfen[verworfen:]
            if v.grund != GRUND_NUR_LESEN
        }
        for eintrag in self.spur.seit(marke):
            if eintrag.url in neu and (
                eintrag.art == DOKUMENT or eintrag.methode == POST
            ):
                return f"{eintrag.methode} {eintrag.url} {neu[eintrag.url]}"
        return None


def _kein_weiter(daten: dict) -> str | None:
    if daten["tag"] not in KNOPF_TAGS and daten["rolle"] not in KNOPF_ROLLEN:
        return f"ist kein Knopf und kein Link ({daten['tag']})"
    if daten["ziel"] == NEUES_FENSTER:
        return "öffnet ein neues Fenster"
    if KAUFWORT.search(daten["text"]):
        return "sieht nach Kauf, Kasse oder Anmeldung aus"
    return None


def _knapp(text: str) -> str:
    return " ".join(text.split()).casefold()


def _ohne_anker(adresse: str) -> str:
    return urldefrag(adresse)[0]
