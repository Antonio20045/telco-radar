"""Typen der Klick-Karte: Knöpfe, Marken, Vorbereitung, Lesung, Antwort, Kanarie.

Das Format und welcher Anbieter welches Merkmal braucht, beschreibt ``klickkarte``; dort
stehen auch Lader und Prüfung. Dieses Modul hält nur Namen, Grenzen und Datentypen und
ruft weder Netz noch Browser.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field

DIMENSIONEN = ("speicher", "tarif", "laufzeit")
WERTFELDER = (
    "anzahlung",
    "rate",
    "ratenzahl",
    "tarifphasen",
    "tarifbindung",
    "anschluss",
    "volumen_gb",
)
PHASENFELD = "tarifphasen"
PHASENTEILE = ("liste", "von", "bis", "betrag")
GEWAEHLT = "gewaehlt"
PLATZHALTER_MODELL = "modell"
GRUND_FEHLT = "Pflichtfeld fehlt oder ist leer"
GRUND_KEINE_ZUORDNUNG = "ist keine Zuordnung"
GRUND_KEIN_TEXT = "ist kein Text"
GRUND_KEINE_LISTE = "ist keine Liste"
GRUND_UNBEKANNT = "unbekanntes Feld"
GRUND_MUSTER = "kein gültiger regulärer Ausdruck"
GRUND_YAML = "kein lesbares YAML"
GRUND_OHNE_VARIANTE = "Antwort nennt keine Variante (variante oder parameter)"
GRUND_ENTWEDER = "entweder attribut mit wert oder passt"
GRUND_FEST_UND_KNOPF = "fest schließt selektor, wert, wert_in, muster und gewaehlt aus"
GRUND_OHNE_MARKE = "Dimension ohne eigene Marke braucht knoepfe.gewaehlt"
GRUND_PLATZHALTER = "unbekannter Platzhalter"


class KlickkartenFehler(ValueError):
    """Die Karte ist unvollständig oder falsch geformt; ``feld`` nennt die Stelle."""

    def __init__(self, quelle: str, feld: str, grund: str) -> None:
        self.quelle = quelle
        self.feld = feld
        self.grund = grund
        stelle = f", Feld {feld}" if feld else ""
        super().__init__(f"Klick-Karte {quelle}{stelle}: {grund}")


@dataclass(frozen=True)
class Auswahlmarke:
    """Woran die Seite die gewählte Option zeigt.

    Entweder ``attribut`` gleich ``wert`` am Klickziel oder ``passt``: ein CSS-Selektor,
    auf den das Klickziel passt, wenn es gewählt ist (``Element.matches``).
    """

    attribut: str | None = None
    wert: str | None = None
    passt: str | None = None


@dataclass(frozen=True)
class Knopf:
    """Die Optionen einer Dimension: Klickziele, Wert, eigene Marke oder fester Wert.

    ``selektor`` ist ``None`` nur bei einer festen Dimension (``fest``). Der Wert
    kommt aus ``wert_attribut`` oder dem sichtbaren Text, am Klickziel oder an dessen
    erstem Kind-Element ``wert_in``; ``muster`` nimmt daraus die erste Gruppe.
    ``marke`` ist die eigene Auswahlmarke der Dimension, ``None`` heißt: die der Karte.
    """

    selektor: str | None
    wert_attribut: str | None = None
    wert_in: str | None = None
    muster: re.Pattern[str] | None = None
    marke: Auswahlmarke | None = None
    fest: str | None = None


@dataclass(frozen=True)
class Vorbereitung:
    """Ein Zustand, den die Seite vor jeder Lesung haben muss.

    Passt das erste Element zu ``pruefe`` (ohne: zu ``klick``) nicht auf den
    CSS-Selektor ``bis``, klickt der Crawler das erste Element zu ``klick`` und wartet
    darauf.
    """

    klick: str
    bis: str
    pruefe: str | None = None


@dataclass(frozen=True)
class Textlesung:
    """Wo die sichtbare Preiszusammenfassung steht und wie sie zu öffnen ist.

    ``oeffnen`` wird geklickt, wenn der erste Bereich nicht sichtbar ist, ``schliessen``
    nach der Lesung, wenn der Bereich dann noch sichtbar ist.
    """

    selektoren: tuple[str, ...]
    oeffnen: str | None = None
    schliessen: str | None = None


@dataclass(frozen=True)
class Phasenpfad:
    """Liste der Preisphasen in der Antwort und die Feldnamen je Phase."""

    liste: str
    von: str
    bis: str
    betrag: str


@dataclass(frozen=True)
class Antwortmuster:
    """Welche Antwort mitgeschnitten wird und wo ihre Werte stehen."""

    url_muster: re.Pattern[str]
    pfade: Mapping[str, str | Phasenpfad]
    variante: Mapping[str, str]
    parameter: Mapping[str, str]

    def passt(self, url: str) -> bool:
        """Wahr, wenn ``url`` die mitzuschneidende Antwort ist."""
        return self.url_muster.search(url) is not None


@dataclass(frozen=True)
class Kanarie:
    """Ein Text, der an fester Stelle stehen muss, solange die Karte zur Seite passt.

    ``enthaelt`` darf ``{modell}`` tragen: der Modellname des Geräts aus dem Katalog.
    Mit ``attribut`` gilt der Wert dieses Attributs statt des sichtbaren Texts.
    """

    selektor: str
    enthaelt: str
    attribut: str | None = None


@dataclass(frozen=True)
class Klickkarte:
    """Die Klick-Karte eines Anbieters.

    ``gewaehlt`` ist die Standardmarke (``None`` nur, wenn jede geklickte Dimension eine
    eigene trägt); ``zusammenfassung`` nennt die Bereiche der Textlesung für Belege.
    """

    anbieter: str
    knoepfe: Mapping[str, Knopf]
    gewaehlt: Auswahlmarke | None
    zusammenfassung: str
    antwort: Antwortmuster
    kanarie: Kanarie
    textlesung: Textlesung
    vorbereitung: tuple[Vorbereitung, ...] = field(default=())

    def marke(self, dimension: str) -> Auswahlmarke | None:
        """Die Marke einer Dimension: ihre eigene, sonst die der Karte."""
        eigene = self.knoepfe[dimension].marke
        return eigene if eigene is not None else self.gewaehlt
