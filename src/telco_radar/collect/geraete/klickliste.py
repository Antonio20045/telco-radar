"""Übersicht aus Datenantworten der Seite (``Lesart.liste``, ``klickuebersicht``).

Rendert ein Anbieter die Übersicht clientseitig (Telekom seit Oktober 2026), stehen
die Geräte in Datenantworten, die der Browser der Seite selbst anfragt. ``Listenlauf``
schneidet sie mit (``klickmitschnitt.Mitschnitt``, gebunden vor dem Laden), wartet
die erste ab, schaltet den Schalter der ``Datenliste`` aus (klicken, bis er auf
``aus`` passt; fehlt er, ist die Übersicht leer mit ``GRUND_OHNE_SCHALTER``) und
wartet die neue Antwort ab. Dann klickt er „Weitere Geräte anzeigen“ im selben
Seitenzustand, bis die letzte Antwort ``(pageNumber+1)*itemsPerPage >= resultCount``
meldet, höchstens ``HOECHSTE_WEITER`` Mal; fehlt der Knopf vorher, steht der Schalter
wieder an oder kommt keine Antwort, nennt ``unvollstaendig`` den Grund. Es zählen nur
Antworten auf Anfragen nach dem Ausschalten. Eine Antwort mit Bot-Schutz
(``klicklauf.bot_schutz``) macht den Lauf gestört. ``diagnose`` geht unter ``liste``
in den Eintrag der Seite, ohne Rohkörper.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from functools import partial
from typing import TYPE_CHECKING

from playwright.sync_api import Error as PlaywrightFehler

from .klickergebnis import LAUF_LEER
from .klicklauf import LAUF_GESTOERT, antworttext, bot_schutz
from .klickmitschnitt import Mitschnitt
from .klicktor import kurz
from .klickwache import Abbruch, Wache

if TYPE_CHECKING:
    from playwright.sync_api import Locator, Page, Response

    from .telekom_liste import Listenlesung

HOECHSTE_WEITER = 10
GRUND_OHNE_SCHALTER = "Übersicht ohne Rückgabedeal-Schalter"
GRUND_SCHALTER_BLEIBT = "Rückgabedeal-Schalter lässt sich nicht ausschalten"
GRUND_OHNE_ANTWORT = "keine Datenantwort nach dem Ausschalten"
GRUND_SCHALTER_WIEDER_AN = "Rückgabedeal-Schalter nach „Weitere Geräte“ wieder an"
GRUND_OHNE_KNOPF = "„Weitere Geräte“ fehlt, die Antwort nennt weitere"
GRUND_WEITER_OHNE_ANTWORT = "keine Datenantwort nach „Weitere Geräte“"
GRUND_OBERGRENZE_WEITER = f"Obergrenze von {HOECHSTE_WEITER} Klicks „Weitere Geräte“"
_PASST_JS = "(element, css) => element.matches(css)"


@dataclass(frozen=True)
class Datenliste:
    """Datenantworten einer Übersicht: Adressteil, Schalter samt Aus-Zustand (CSS),
    Text des Weiter-Knopfs und die Lesung ``saetze(nutzlasten, text, adresse)``."""

    url_teil: str
    schalter: str
    aus: str
    weiter_text: str
    saetze: Callable[[list[object], str, str], Listenlesung]


class Listenlauf:
    """Mitschnitt und Bedienung der Datenliste auf einer Seite."""

    def __init__(self, seite: Page, wache: Wache, liste: Datenliste) -> None:
        self.seite, self.wache, self.liste = seite, wache, liste
        self.mitschnitt = Mitschnitt(lambda url: liste.url_teil in url)
        self.mitschnitt.binde(seite)
        self.nutzlasten: list[object] = []
        self.klicks = 0
        self.diagnose: dict[str, object] = {
            "antworten_beim_laden": 0,
            "antworten": 0,
            "schalter_vorher": None,
            "schalter_nachher": None,
            "weiter_klicks": 0,
            "unvollstaendig": None,
        }

    def bediene(self) -> None:
        """Schaltet aus, blättert weiter und liest die Antworten danach."""
        m, d = self.mitschnitt, self.diagnose
        self.wache.warte(lambda: m.fertig_seit(0))
        d["antworten_beim_laden"] = len(m.antworten_seit(0))
        schalter = self.seite.locator(self.liste.schalter).first
        if not self.wache.warte(lambda: schalter.count() > 0):
            raise Abbruch(LAUF_LEER, GRUND_OHNE_SCHALTER)
        d["schalter_vorher"] = self._zustand(schalter)
        marke = 0
        if not self._aus(schalter):
            marke = m.stand()
            try:
                schalter.click(timeout=self.wache.frist_ms)
            except PlaywrightFehler as fehler:
                grund = f"{GRUND_SCHALTER_BLEIBT}: {kurz(fehler)}"
                raise Abbruch(LAUF_LEER, grund) from fehler
            if not self.wache.warte(lambda: self._aus(schalter)):
                raise Abbruch(LAUF_LEER, GRUND_SCHALTER_BLEIBT)
            if not self.wache.warte(lambda: m.fertig_seit(marke)):
                raise Abbruch(LAUF_LEER, GRUND_OHNE_ANTWORT)
        try:
            d["unvollstaendig"] = self._weiter(marke, schalter)
        except PlaywrightFehler as fehler:
            d["unvollstaendig"] = f"Weitere Geräte: {kurz(fehler)}"
        d["weiter_klicks"] = self.klicks
        d["schalter_nachher"] = self._zustand(schalter)
        self.nutzlasten = [self._nutzlast(a) for a in m.antworten_seit(marke)]
        d["antworten"] = len(self.nutzlasten)

    def _weiter(self, marke: int, schalter: Locator) -> str | None:
        """Klickt „Weitere Geräte“ bis zur letzten Seite; sonst der Grund."""
        m = self.mitschnitt
        knopf = self.seite.locator("a, button").filter(has_text=self.liste.weiter_text)
        for _ in range(HOECHSTE_WEITER):
            if self._letzte_seite(m.letzte_seit(marke)):
                return None
            if not self.wache.warte(lambda: knopf.count() > 0):
                return GRUND_OHNE_KNOPF
            if not self._aus(schalter):
                return GRUND_SCHALTER_WIEDER_AN
            stand = m.stand()
            knopf.first.click(timeout=self.wache.frist_ms)
            self.klicks += 1
            if not self.wache.warte(partial(m.fertig_seit, stand)):
                return GRUND_WEITER_OHNE_ANTWORT
        if self._letzte_seite(m.letzte_seit(marke)):
            return None
        return GRUND_OBERGRENZE_WEITER

    def _zustand(self, schalter: Locator) -> str | None:
        """``aria-checked`` des Schalters; ``None``, wenn er nicht (mehr) lesbar ist."""
        try:
            return schalter.get_attribute("aria-checked", timeout=self.wache.frist_ms)
        except PlaywrightFehler:
            return None

    def _aus(self, schalter: Locator) -> bool:
        return schalter.evaluate(_PASST_JS, self.liste.aus) is True

    def _letzte_seite(self, antwort: Response | None) -> bool:
        nutzlast = None if antwort is None else self._nutzlast(antwort)
        if not isinstance(nutzlast, dict):
            return False
        seite, je_seite, gesamt = (
            nutzlast.get(f) for f in ("pageNumber", "itemsPerPage", "resultCount")
        )
        if not (
            isinstance(seite, int)
            and isinstance(je_seite, int)
            and isinstance(gesamt, int)
        ):
            return False
        return (seite + 1) * je_seite >= gesamt

    def _nutzlast(self, antwort: Response) -> object:
        """Der JSON-Körper; Bot-Schutz heißt gestört, Unlesbares ist ``None``."""
        typ = antwort.headers.get("content-type", "")
        text = antworttext(antwort.body(), typ)
        stoerung = bot_schutz(antwort.status, typ, text, json_erwartet=True)
        if stoerung is not None:
            raise Abbruch(LAUF_GESTOERT, f"Datenantwort: {stoerung}")
        try:
            return json.loads(text)
        except ValueError:
            return None
