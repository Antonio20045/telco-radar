"""Typen der Klick-Karte: Knöpfe, Marken, Vorbereitung, Lesung, Antwort, Kanarie.

Das Format und welcher Anbieter welches Merkmal braucht, beschreibt ``klickkarte``; dort
stehen auch Lader und Prüfung. Dieses Modul hält nur Namen, Grenzen und Datentypen und
ruft weder Netz noch Browser.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field, replace

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
BUENDELFELDER = ("buendelbetrag", "einmalzahlung")
EIN_VERTRAG = "ein_vertrag"
VERTRAGSFORMEN = ("tarif_plus_ratenkauf", EIN_VERTRAG)
ENTFALLEN_IM_BUENDEL = ("rate", "ratenzahl")
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
GRUND_ADRESSEN_UND_KNOPF = "adressen schließt alle anderen Teile des Knopfs aus"
GRUND_EINE_ADRESSDIMENSION = "adressen nur bei einer Dimension"
ADRESSATTRIBUT = "href"
GRUND_FEST_UND_KNOPF = "fest schließt selektor, wert, wert_in, muster und gewaehlt aus"
GRUND_OHNE_MARKE = "Dimension ohne eigene Marke braucht knoepfe.gewaehlt"
GRUND_PLATZHALTER = "unbekannter Platzhalter"
GRUND_EINE_QUELLE = "genau eines von url_muster, skript und global"
GRUND_NUR_URL = "nur mit url_muster"
GRUND_WAHRHEITSWERT = "ist kein Wahrheitswert"
GRUND_EINHEIT = "unbekannte Einheit"
GRUND_NAME = "kein gültiger Name (Kleinbuchstaben, Ziffern, _)"
GRUND_SEITENWERT = "braucht selektor oder parameter"
GRUND_NUR_BUENDEL = f"nur mit vertragsform {EIN_VERTRAG}"
GRUND_ENTFAELLT = f"entfällt bei vertragsform {EIN_VERTRAG}"
GRUND_VERTRAGSFORM = "unbekannte Vertragsform"
EINHEIT_CENT = "cent"
EINHEIT_MB = "mb"
EINHEITEN = (EINHEIT_CENT, EINHEIT_MB)
GRUND_DIMENSION = "keine Dimension"
GRUND_KACHEL_KNOPF = "Kacheln brauchen selektor, nicht fest oder adressen"
GRUND_KACHEL_MARKE = "Kacheln werden nie geklickt und tragen keine Marke"
GRUND_KACHEL_BEREICH = "einziger Bereich muss der Selektor der Kacheln sein"
GRUND_KACHEL_MUSTER = "Textmuster lesen in der Kachel, ohne eigenen selektor"
GRUND_WEITER_ADRESSEN = "weiter schließt adressen aus"
GRUND_WEITER_KLICK = "weiter erlaubt keinen zweiten Klick (oeffnen, schliessen)"


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
    ``adressen``: die Optionen sind eigene Seiten (dann ist ``selektor`` ``None``).
    ``gesperrt``: CSS-Selektor für Klickziele, die die Seite als nicht angeboten zeigt.
    """

    selektor: str | None
    wert_attribut: str | None = None
    wert_in: str | None = None
    muster: re.Pattern[str] | None = None
    marke: Auswahlmarke | None = None
    fest: str | None = None
    adressen: Adressen | None = None
    gesperrt: str | None = None


@dataclass(frozen=True)
class Adressen:
    """Optionen einer Dimension als Adressen, die die Seite selbst zeigt.

    ``selektor`` trifft die Elemente, ``attribut`` trägt die Adresse, der Parameter
    ``parameter`` dieser Adresse ist der Optionswert.
    """

    selektor: str
    parameter: str
    attribut: str = ADRESSATTRIBUT


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
class Textmuster:
    """Wo ein Wertfeld im Text steht: erste Gruppe von ``muster``.

    Ohne ``selektor`` im Text der Zusammenfassung, sonst im Text des ersten Treffers.
    """

    muster: re.Pattern[str]
    selektor: str | None = None


@dataclass(frozen=True)
class Textlesung:
    """Wo die sichtbare Preiszusammenfassung steht und wie sie zu öffnen ist.

    Der Text ist der der Bereiche ``selektoren`` ohne den Text der Treffer zu ``ohne``.
    ``oeffnen`` wird geklickt, wenn der erste Bereich nicht sichtbar ist, ``schliessen``
    nach der Lesung, wenn der Bereich dann noch sichtbar ist. ``muster`` nennt je
    Wertfeld seinen Fundort; es ersetzt die allgemeine Lesung dieses Felds.
    """

    selektoren: tuple[str, ...]
    oeffnen: str | None = None
    schliessen: str | None = None
    ohne: tuple[str, ...] = ()
    muster: Mapping[str, Textmuster] = field(default_factory=dict)


@dataclass(frozen=True)
class Phasenpfad:
    """Liste der Preisphasen in der Antwort und die Feldnamen je Phase."""

    liste: str
    von: str
    bis: str
    betrag: str


@dataclass(frozen=True)
class Wertpfad:
    """Ein Pfad (oder Parametername) mit Muster und Einheit.

    ``muster`` nimmt aus dem Wert als Text die erste Gruppe; ``einheit`` rechnet um
    (``cent`` in Euro, ``mb`` in GB zu 1024 MB).
    """

    pfad: str
    muster: re.Pattern[str] | None = None
    einheit: str | None = None


@dataclass(frozen=True)
class Antwortmuster:
    """Eine Quelle der zweiten Lesung und wo ihre Werte stehen.

    Genau eines von ``url_muster`` (mitgeschnittene Antwort), ``skript`` (JSON im
    ersten Treffer des CSS-Selektors) und ``globale`` (globale Variablen der Seite).
    ``laden``: die Antwort gilt für jede Kombination, nicht nur für den Klick, nach dem
    sie kam; ``start``: die Quelle gilt nur, bis die Seite zum ersten Mal geklickt
    wurde. ``erkennung`` wählt unter Antworten derselben Adresse die mit einem Wert an
    diesem Pfad; ``segment`` nimmt die erste Gruppe aus der Antwortadresse, Base64 mit
    ``name=wert`` durch ``;`` getrennt, als weitere Parameter. ``platzhalter`` nennt
    Werte dieser Antwort an Pfaden, die ihre Pfade und Varianten als weitere
    Platzhalter tragen (Telekom: der Ratenplan zu Laufzeit und Anzahlung der Seite).
    """

    url_muster: re.Pattern[str] | None
    pfade: Mapping[str, str | Wertpfad | Phasenpfad]
    variante: Mapping[str, str | Wertpfad]
    parameter: Mapping[str, str | Wertpfad]
    skript: str | None = None
    globale: tuple[str, ...] = ()
    laden: bool = False
    start: bool = False
    erkennung: str | None = None
    segment: re.Pattern[str] | None = None
    platzhalter: Mapping[str, str] = field(default_factory=dict)

    def passt(self, url: str) -> bool:
        """Wahr, wenn ``url`` die mitzuschneidende Antwort ist."""
        return self.url_muster is not None and self.url_muster.search(url) is not None

    @property
    def je_klick(self) -> bool:
        """Wahr, wenn die Quelle eine Antwort nach jedem Klick erwartet."""
        return self.url_muster is not None and not self.laden

    @property
    def ort(self) -> str:
        """Woher die Quelle liest, für Beleg und Gründe."""
        if self.skript is not None:
            return f"skript {self.skript}"
        if self.globale:
            return f"global {', '.join(self.globale)}"
        return "" if self.url_muster is None else self.url_muster.pattern


@dataclass(frozen=True)
class Seitenwert:
    """Ein Wert der Seite für Platzhalter und Echo.

    Text oder ``attribut`` am ersten Treffer zu ``selektor``, ohne ``selektor`` die
    Adresse der Seite; ``parameter`` nimmt daraus den Parameter der Adresse,
    ``muster`` die erste Gruppe.
    """

    selektor: str | None = None
    attribut: str | None = None
    parameter: str | None = None
    muster: re.Pattern[str] | None = None


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
class Weiterschritt:
    """Der eine Klick in die Bestellstrecke und die Dimension auf der Folgeseite.

    ``selektor`` und ``text`` nennen den Weiter-Knopf der Startseite; die Optionen von
    ``kacheln`` stehen auf der Folgeseite als Kacheln nebeneinander und werden gelesen,
    nie geklickt.
    """

    selektor: str
    text: str
    kacheln: str


@dataclass(frozen=True)
class Klickkarte:
    """Die Klick-Karte eines Anbieters.

    ``gewaehlt`` ist die Standardmarke (``None`` nur, wenn jede geklickte Dimension eine
    eigene trägt); ``zusammenfassung`` nennt die Bereiche der Textlesung für Belege.
    ``quellen`` sind alle Quellen der zweiten Lesung in Reihenfolge, ``antwort`` ist
    die erste; ``seite`` nennt Seitenwerte nach Namen. Bei ``vertragsform``
    ``ein_vertrag`` entfallen Rate und Ratenzahl planmäßig, dafür gelten
    ``BUENDELFELDER``. ``weiter`` nennt den Klick in die Bestellstrecke.
    """

    anbieter: str
    knoepfe: Mapping[str, Knopf]
    gewaehlt: Auswahlmarke | None
    zusammenfassung: str
    antwort: Antwortmuster
    kanarie: Kanarie
    textlesung: Textlesung
    vorbereitung: tuple[Vorbereitung, ...] = field(default=())
    quellen: tuple[Antwortmuster, ...] = field(default=())
    seite: Mapping[str, Seitenwert] = field(default_factory=dict)
    vertragsform: str = VERTRAGSFORMEN[0]
    weiter: Weiterschritt | None = None

    @property
    def ein_vertrag(self) -> bool:
        """Wahr, wenn Gerät und Tarif ein Vertrag mit Bündelbetrag sind."""
        return self.vertragsform == EIN_VERTRAG

    @property
    def entfallen(self) -> tuple[str, ...]:
        """Wertfelder, die planmäßig entfallen und keine Lücke sind."""
        return ENTFALLEN_IM_BUENDEL if self.ein_vertrag else ()

    @property
    def lesefelder(self) -> tuple[str, ...]:
        """Die Felder, die jede Lesung sucht: Wertfelder und bei Bedarf Bündelfelder."""
        felder = tuple(f for f in WERTFELDER if f not in self.entfallen)
        return (*felder, *BUENDELFELDER) if self.ein_vertrag else felder

    @property
    def lesequellen(self) -> tuple[Antwortmuster, ...]:
        """Alle Quellen der zweiten Lesung; ohne ``quellen`` nur ``antwort``."""
        return self.quellen if self.quellen else (self.antwort,)

    @property
    def je_klick(self) -> bool:
        """Wahr, wenn eine Quelle nach jedem Klick eine Antwort erwartet."""
        return any(q.je_klick for q in self.lesequellen)

    @property
    def adressdimension(self) -> str | None:
        """Die Dimension, deren Optionen eigene Adressen sind; ``None`` ohne."""
        return next((d for d, k in self.knoepfe.items() if k.adressen), None)

    @property
    def kacheldimension(self) -> str | None:
        """Die Dimension mit Kacheln auf der Folgeseite; ``None`` ohne ``weiter``."""
        return None if self.weiter is None else self.weiter.kacheln

    def mit_fest(self, dimension: str, wert: str) -> Klickkarte:
        """Dieselbe Karte, in der ``dimension`` den festen Wert ``wert`` hat; eine
        Adressdimension bleibt eine (``adressen``), damit die Lesung ihr Echo prüft."""
        adressen = self.knoepfe[dimension].adressen
        knoepfe = {
            **self.knoepfe,
            dimension: Knopf(selektor=None, fest=wert, adressen=adressen),
        }
        return replace(self, knoepfe=knoepfe)

    def marke(self, dimension: str) -> Auswahlmarke | None:
        """Die Marke einer Dimension: ihre eigene, sonst die der Karte."""
        eigene = self.knoepfe[dimension].marke
        return eigene if eigene is not None else self.gewaehlt
