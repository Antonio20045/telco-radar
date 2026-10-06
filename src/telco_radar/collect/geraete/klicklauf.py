"""Ergebnis eines Klick-Laufs: Status je Kombination, Strukturwächter, Störung.

Der Klick-Crawler (``klickcrawler``) füllt diese Typen; dieses Modul ruft keinen
Browser und kein Netz. Je Kombination gilt einer von vier Zuständen: ``erfasst``,
``nicht_angeboten`` (die Seite zeigt die Option deaktiviert), ``nicht_erfasst`` (Knöpfe,
Option oder Zusammenfassung nicht gefunden, Laufzeit nicht lesbar, nicht besucht) oder
``befund`` (das Echo widerspricht sich). Ein Lauf ist ``gelesen``, ``gestoert``
(Challenge 202, 4xx, 5xx, fehlender Kanarienwert, offene Preisantwort, Strukturbruch)
oder ``gesperrt`` (robots.txt sperrt Seite, Preisantwort oder Zeit).

Der Strukturwächter zählt je Lauf gesuchte und gefundene Knöpfe und Felder. Findet ein
Lauf weniger als ``MINDESTANTEIL_KNOEPFE`` der gesuchten Knöpfe oder fällt ein Anteil
gegen den letzten gelesenen Lauf um mehr als ``STRUKTUR_SPRUNG``, ist der Lauf gestört
und nicht „nichts gefunden“. Ohne Suche ist ein Anteil ``None``, nie 0.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .klickecho import Befund, Variante
from .klickkarte import WERTFELDER
from .klicktext import Preiswerte

ERFASST = "erfasst"
NICHT_ANGEBOTEN = "nicht_angeboten"
NICHT_ERFASST = "nicht_erfasst"
BEFUND = "befund"
LAUF_GELESEN = "gelesen"
LAUF_GESTOERT = "gestoert"
LAUF_GESPERRT = "gesperrt"
CHALLENGE_STATUS = 202
FEHLER_AB_STATUS = 400
STRUKTUR_SPRUNG = 0.2
MINDESTANTEIL_KNOEPFE = 0.5


@dataclass(frozen=True)
class Verworfen:
    """Eine Adresse, die robots.txt sperrt; sie ging nicht hinaus.

    ``anfrage`` ist die Adresse, die die Seite anfragte; nach einer Umleitung weicht
    sie von ``url`` ab.
    """

    url: str
    grund: str
    anfrage: str


@dataclass(frozen=True)
class Kombiergebnis:
    """Das Ergebnis einer Kombination aus Speicher, Tarif und Ratenlaufzeit.

    ``variante`` ist gelesen (Laufzeit als Monatszahl), ``auswahl`` die rohen Werte
    der Knöpfe in der Reihenfolge von ``klickkarte.DIMENSIONEN``.
    """

    variante: Variante
    status: str
    grund: str | None = None
    werte: Preiswerte = field(default_factory=Preiswerte)
    befunde: tuple[Befund, ...] = ()
    luecken: tuple[str, ...] = ()
    screenshot_png: bytes | None = None
    antwort_url: str | None = None
    auswahl: tuple[str | None, ...] = ()


@dataclass
class Strukturbilanz:
    """Wie viele gesuchte Knöpfe und Felder ein Lauf gefunden hat."""

    knoepfe_gesucht: int = 0
    knoepfe_gefunden: int = 0
    felder_gesucht: int = 0
    felder_gefunden: int = 0

    def knopf(self, gefunden: bool) -> None:
        """Zählt eine Suche nach den Knöpfen einer Dimension."""
        self.knoepfe_gesucht += 1
        self.knoepfe_gefunden += int(gefunden)

    def felder(self, gefunden: int) -> None:
        """Zählt die Wertfelder einer gelesenen oder fehlenden Zusammenfassung."""
        self.felder_gesucht += len(WERTFELDER)
        self.felder_gefunden += gefunden

    @property
    def anteil_knoepfe(self) -> float | None:
        """Anteil gefundener Knöpfe; ``None``, wenn nichts gesucht wurde."""
        return _anteil(self.knoepfe_gefunden, self.knoepfe_gesucht)

    @property
    def anteil_felder(self) -> float | None:
        """Anteil gefundener Felder; ``None``, wenn nichts gesucht wurde."""
        return _anteil(self.felder_gefunden, self.felder_gesucht)


@dataclass
class Klicklauf:
    """Ein Lauf über eine Produktseite: Status, Ergebnisse, Struktur, Verworfenes."""

    anbieter: str
    adresse: str
    status: str = LAUF_GELESEN
    grund: str | None = None
    http_status: int | None = None
    ergebnisse: list[Kombiergebnis] = field(default_factory=list)
    struktur: Strukturbilanz = field(default_factory=Strukturbilanz)
    verworfen: list[Verworfen] = field(default_factory=list)


def abruf_gestoert(status: int | None) -> str | None:
    """Grund, wenn der HTTP-Status den Abruf stört (202, 4xx, 5xx), sonst ``None``."""
    if status is None:
        return "Abruf gestört (keine Antwort)"
    if status == CHALLENGE_STATUS or status >= FEHLER_AB_STATUS:
        return f"Abruf gestört (HTTP {status})"
    return None


def strukturgrund(aktuell: Strukturbilanz, vorlauf: Klicklauf | None) -> str | None:
    """Grund, wenn der Lauf zu wenige Knöpfe fand oder gegen den Vorlauf einbrach.

    Der Mindestanteil gilt immer; der Vorlauf zählt nur, wenn er gelesen ist.
    """
    anteil = aktuell.anteil_knoepfe
    if anteil is not None and anteil < MINDESTANTEIL_KNOEPFE:
        return (
            f"Strukturbruch: nur {_prozent(anteil)} der gesuchten Knöpfe gefunden"
            f" (mindestens {_prozent(MINDESTANTEIL_KNOEPFE)})"
        )
    if vorlauf is None or vorlauf.status != LAUF_GELESEN:
        return None
    return strukturbruch(aktuell, vorlauf.struktur)


def strukturbruch(
    aktuell: Strukturbilanz, vorlauf: Strukturbilanz, sprung: float = STRUKTUR_SPRUNG
) -> str | None:
    """Grund, wenn ein Anteil gegen den Vorlauf um mehr als ``sprung`` fällt."""
    paare = (
        ("Knöpfe", aktuell.anteil_knoepfe, vorlauf.anteil_knoepfe),
        ("Felder", aktuell.anteil_felder, vorlauf.anteil_felder),
    )
    for name, jetzt, vorher in paare:
        if jetzt is not None and vorher is not None and vorher - jetzt > sprung:
            return (
                f"Strukturbruch: Anteil gefundener {name} fiel von"
                f" {_prozent(vorher)} auf {_prozent(jetzt)}"
            )
    return None


def _anteil(gefunden: int, gesucht: int) -> float | None:
    return gefunden / gesucht if gesucht else None


def _prozent(anteil: float) -> str:
    return f"{round(anteil * 100)} %"
