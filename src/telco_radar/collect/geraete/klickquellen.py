"""Zweite Lesung aus den Quellen der Klick-Karte: Antworten und Seitenzustand.

Je Quelle (``klickkarte.Antwortmuster``) liest ``Quellenleser`` die Nutzlast: die
letzte passende Antwort seit dem Klick (``je_klick``) oder seit dem Laden (``laden``,
congstar und Vodafone laden die Preise einmal), unter Antworten derselben Adresse die
mit einem Wert an ``erkennung`` (congstar: drei GraphQL-Antworten, Vodafone: dieselbe
Antwort als xhr und fetch); JSON in einem Skript der Seite (o2 ``script#pageValue``)
oder globale Variablen (1&1 ``hwdVariantsPrices``). Eine ``start``-Quelle gilt nur,
solange niemand geklickt hat. Die Werte liest ``klickecho.lies_antwort`` mit den
Platzhaltern der Kombination; je Wertfeld zählt die erste Quelle mit einem Wert, je
Dimension müssen alle Quellen dieselbe Variante nennen, sonst ist sie mehrdeutig.

Für den Beleg nimmt der Leser die eine Antwort, aus der alle Werte stammen; kommen sie
aus mehreren Quellen oder aus der Seite, ist der Mitschnitt eine Lesung: JSON der
beitragenden Quellen nach Stelle und Ort, Methode ``LESUNG``, Adresse der Seite mit
``#lesung``, die Cookie- und Zugangswerte aller beitragenden Antworten geschwärzt. Die
Wiedergabe (``route_from_har``) trifft sie nie. ``seitenwerte`` liest die benannten
Werte der Seite. Dieses Modul ruft kein Netz außer über die Seite.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any
from urllib.parse import urljoin

from playwright.sync_api import Error as PlaywrightFehler

from .klickbeleg import kopie_aus, pfadtext
from .klickecho import (
    Antwortlesung,
    Befund,
    adressparameter,
    gleiche_option,
    lies_antwort,
)
from .klickhar import Antwortkopie, schwaerze
from .klickkarte import (
    BUENDELFELDER,
    DIMENSIONEN,
    WERTFELDER,
    Antwortmuster,
    Klickkarte,
)
from .klickoptionen import wert_nach_muster
from .klickpfad import am_pfad
from .klicktext import Buendelwerte, Preiswerte
from .klicktor import kurz

if TYPE_CHECKING:
    from playwright.sync_api import Page, Response

    from .klickmitschnitt import Mitschnitt

LESUNG = "LESUNG"
MEHRDEUTIG = "mehrdeutig"
FELDER = (*WERTFELDER, *BUENDELFELDER)
_SEITENWERT_JS = "(e, a) => a ? e.getAttribute(a) : e.innerText"
_GLOBALE_JS = """(namen) => Object.fromEntries(
  namen.map((n) => [n, window[n] === undefined ? null : window[n]]))"""


@dataclass(frozen=True)
class Nutzlast:
    """Was eine Quelle geliefert hat: Daten, Adresse und Antwort, wenn es eine ist."""

    stelle: int
    daten: object
    url: str | None = None
    antwort: Response | None = None


@dataclass(frozen=True)
class Quellenlesung:
    """Die zweite Lesung einer Kombination mit Beleg-Teilen.

    ``lesung`` ist ``None``, wenn keine Quelle etwas lieferte; ``befund`` nennt eine
    unlesbare Quelle; ``json_pfade`` je gelesenem Feld den Pfad in ``kopie``.
    """

    lesung: Antwortlesung | None
    befund: Befund | None = None
    kopie: Antwortkopie | None = None
    json_pfade: Mapping[str, str] = field(default_factory=dict)


class Quellenleser:
    """Liest die Quellen einer Karte auf einer Seite aus dem Mitschnitt und dem DOM."""

    def __init__(self, seite: Page, karte: Klickkarte, mitschnitt: Mitschnitt) -> None:
        self.seite, self.karte, self.mitschnitt = seite, karte, mitschnitt

    def seitenwerte(self) -> dict[str, str | None]:
        """Die benannten Werte der Seite; ``None``, wo der Wert fehlt."""
        werte: dict[str, str | None] = {}
        for name, wert in self.karte.seite.items():
            roh = (
                self.seite.url
                if wert.selektor is None
                else self._am(wert.selektor, wert.attribut)
            )
            if roh is not None and wert.parameter is not None:
                frage = adressparameter(urljoin(self.seite.url, roh), None)
                roh = frage.get(wert.parameter)
            text = None if roh is None else " ".join(roh.split())
            werte[name] = None if not text else wert_nach_muster(text, wert.muster)
        return werte

    def lies(
        self,
        seit: int,
        unberuehrt: bool,
        platz: Mapping[str, str | None],
        geladen: int = 0,
    ) -> Quellenlesung:
        """Liest jede gültige Quelle und vereint ihre Werte.

        ``laden``-Quellen lesen die Antworten seit ``geladen``, dem Stand des
        Mitschnitts vor dem Laden der Seite.
        """
        lasten: list[Nutzlast] = []
        for stelle, quelle in enumerate(self.karte.lesequellen):
            if quelle.start and not unberuehrt:
                continue
            ab = geladen if quelle.laden else seit
            last, befund = self._nutzlast(stelle, quelle, ab, platz)
            if befund is not None:
                return Quellenlesung(None, befund)
            if last is not None:
                lasten.append(last)
        if not lasten:
            return Quellenlesung(None)
        quellen = self.karte.lesequellen
        lesungen = [
            lies_antwort(n.daten, quellen[n.stelle], n.url, platz) for n in lasten
        ]
        herkunft = _herkunft(lasten, lesungen)
        return Quellenlesung(
            _vereint(lesungen),
            kopie=self._kopie(lasten, herkunft),
            json_pfade=self._json_pfade(herkunft),
        )

    def _nutzlast(
        self,
        stelle: int,
        quelle: Antwortmuster,
        seit: int,
        platz: Mapping[str, str | None],
    ) -> tuple[Nutzlast | None, Befund | None]:
        if quelle.skript is not None:
            return self._skript(stelle, quelle.skript)
        if quelle.globale:
            return self._globale(stelle, quelle.globale)
        alle = self.mitschnitt.antworten_seit(seit)
        passend = [a for a in alle if quelle.passt(a.url)]
        for antwort in reversed(passend):
            try:
                daten = antwort.json()
            except (PlaywrightFehler, ValueError) as fehler:
                if quelle.erkennung is not None:
                    continue
                return None, Befund("antwort", f"Antwort nicht lesbar: {kurz(fehler)}")
            if (
                quelle.erkennung is None
                or am_pfad(daten, quelle.erkennung, platz) is not None
            ):
                return Nutzlast(stelle, daten, antwort.url, antwort), None
        return None, None

    def _skript(
        self, stelle: int, selektor: str
    ) -> tuple[Nutzlast | None, Befund | None]:
        ort = self.seite.locator(selektor)
        try:
            if ort.count() == 0:
                return None, None
            daten = json.loads(ort.first.text_content() or "")
        except (PlaywrightFehler, ValueError) as fehler:
            return None, Befund(
                "antwort", f"Skript {selektor} nicht lesbar: {kurz(fehler)}"
            )
        return Nutzlast(stelle, daten), None

    def _globale(
        self, stelle: int, namen: tuple[str, ...]
    ) -> tuple[Nutzlast | None, Befund | None]:
        try:
            daten = self.seite.evaluate(_GLOBALE_JS, list(namen))
        except PlaywrightFehler as fehler:
            grund = f"Globale {', '.join(namen)} nicht lesbar: {kurz(fehler)}"
            return None, Befund("antwort", grund)
        if not isinstance(daten, dict) or all(v is None for v in daten.values()):
            return None, None
        return Nutzlast(stelle, daten), None

    def _am(self, selektor: str, attribut: str | None) -> str | None:
        ort = self.seite.locator(selektor)
        try:
            if ort.count() == 0:
                return None
            roh = ort.first.evaluate(_SEITENWERT_JS, attribut)
        except PlaywrightFehler:
            return None
        return roh if isinstance(roh, str) else None

    def _kopie(
        self, lasten: list[Nutzlast], herkunft: Mapping[str, Nutzlast | None]
    ) -> Antwortkopie | None:
        beitrag = [n for n in lasten if any(h is n for h in herkunft.values())]
        if not beitrag:
            beitrag = lasten[:1]
        if len(beitrag) == 1 and beitrag[0].antwort is not None:
            return kopie_aus(beitrag[0].antwort)
        quellen = self.karte.lesequellen
        koerper: dict[str, Any] = {
            _kennung(n.stelle, quellen[n.stelle]): n.daten for n in beitrag
        }
        kopien = [kopie_aus(n.antwort) for n in beitrag if n.antwort is not None]
        koepfe = [
            k for c in kopien if c is not None for k in (c.anfragekopf, c.antwortkopf)
        ]
        roh = json.dumps(koerper, ensure_ascii=False, default=str).encode("utf-8")
        return Antwortkopie(
            methode=LESUNG,
            url=f"{self.seite.url.split('#')[0]}#lesung",
            anfragekopf={},
            status=200,
            statustext="OK",
            antwortkopf={"content-type": "application/json"},
            koerper=schwaerze(roh, *koepfe),
        )

    def _json_pfade(self, herkunft: Mapping[str, Nutzlast | None]) -> dict[str, str]:
        quellen = self.karte.lesequellen
        pfade = {}
        for feld, last in herkunft.items():
            if last is None:
                continue
            pfad = pfadtext(quellen[last.stelle].pfade[feld])
            if len(quellen) > 1:
                pfad = f"{_kennung(last.stelle, quellen[last.stelle])}: {pfad}"
            pfade[feld] = pfad
        return pfade


def _kennung(stelle: int, quelle: Antwortmuster) -> str:
    return f"[{stelle}] {quelle.ort}"


def _herkunft(
    lasten: list[Nutzlast], lesungen: list[Antwortlesung]
) -> dict[str, Nutzlast | None]:
    paare = list(zip(lasten, lesungen, strict=True))
    return {
        f: next((n for n, lesung in paare if gelesen(lesung, f) is not None), None)
        for f in FELDER
    }


def gelesen(lesung: Antwortlesung, feld: str) -> Any:
    """Der Wert eines Wert- oder Bündelfelds einer Lesung."""
    return getattr(lesung.buendel if feld in BUENDELFELDER else lesung.werte, feld)


def _vereint(lesungen: list[Antwortlesung]) -> Antwortlesung:
    werte = {
        f: next((w for x in lesungen if (w := gelesen(x, f)) is not None), None)
        for f in FELDER
    }
    variante: dict[str, str | int | None] = {}
    for dimension in DIMENSIONEN:
        genannt = [x.variante[dimension] for x in lesungen if dimension in x.variante]
        verschieden = [
            w
            for n, w in enumerate(genannt)
            if not any(gleiche_option(w, v) for v in genannt[:n])
        ]
        if len(verschieden) == 1:
            variante[dimension] = verschieden[0]
        elif verschieden:
            liste = " | ".join(str(w) for w in verschieden)
            variante[dimension] = f"{MEHRDEUTIG}: {liste}"
    return Antwortlesung(
        Preiswerte(**{f: werte[f] for f in WERTFELDER}),
        variante,
        Buendelwerte(**{f: werte[f] for f in BUENDELFELDER}),
    )
