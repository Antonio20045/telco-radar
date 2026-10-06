"""Ergebnis eines Klick-Laufs: Status je Kombination, Strukturwächter, Störung.

Der Klick-Crawler (``klickcrawler``) füllt diese Typen; dieses Modul ruft keinen Browser
und kein Netz. Je Kombination gilt einer von vier Zuständen: ``erfasst``,
``nicht_angeboten`` (die Seite zeigt die Option in Ruhe deaktiviert), ``nicht_erfasst``
(Knöpfe, Option oder Zusammenfassung nicht gefunden, Laufzeit nicht lesbar, nicht
besucht, Seite nicht zur Ruhe gekommen, Preisantwort über die Frist offen) oder
``befund`` (das Echo widerspricht sich). Ein Lauf ist ``gelesen``, ``gestoert``
(Bot-Schutz, fehlender Kanarienwert, offene oder gescheiterte Preisantwort,
Strukturbruch, keine einzige angebotene Kombination) oder ``gesperrt`` (robots.txt
sperrt Seite, Preisantwort oder Zeit). Bot-Schutz heißt ``bot_schutz``: HTTP 202, 4xx
oder 5xx, ein bekanntes Challenge-Muster (``CHALLENGE_MUSTER``) oder eine HTML-Seite, wo
die Preisschnittstelle JSON liefern soll. Gescheiterte Anfragen hält der Lauf mit Grund
fest.

Jede Kombination mit gelesenen Werten trägt ihren Beleg (``klickbeleg``) und
``beleg_status``: ``belegt``, ``fehlt`` oder ``ohne_wert``. Ein Wert ohne Beleg ist
nicht gültig: ``mit_beleg`` macht eine erfasste Kombination ohne Beleg zum ``befund``
mit Grund, die Werte bleiben sichtbar; ``gueltig`` gilt nur erfasst und belegt.

Der Strukturwächter zählt je Lauf gesuchte und gefundene Knöpfe und Felder. Findet ein
Lauf weniger als ``MINDESTANTEIL_KNOEPFE`` der gesuchten Knöpfe oder weniger als
``MINDESTANTEIL_FELDER`` der gesuchten Felder, oder fällt ein Anteil gegen den Bezug um
mehr als ``STRUKTUR_SPRUNG``, ist der Lauf gestört und nicht „nichts gefunden“. Bezug
ist die Bilanz des letzten gelesenen Laufs; ein gestörter oder gesperrter Lauf trägt sie
weiter, sodass ein bleibender Bruch gestört bleibt. Ohne Suche ist ein Anteil ``None``,
nie 0.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING

from .klickecho import Befund, Variante
from .klickkarte import WERTFELDER
from .klicktext import Preiswerte

if TYPE_CHECKING:
    from .klickbeleg import Belegpaket

ERFASST = "erfasst"
NICHT_ANGEBOTEN = "nicht_angeboten"
NICHT_ERFASST = "nicht_erfasst"
BEFUND = "befund"
LAUF_GELESEN = "gelesen"
LAUF_GESTOERT = "gestoert"
LAUF_GESPERRT = "gesperrt"
BELEGT = "belegt"
BELEG_FEHLT = "fehlt"
OHNE_WERT = "ohne_wert"
CHALLENGE_STATUS = 202
FEHLER_AB_STATUS = 400
STRUKTUR_SPRUNG = 0.2
MINDESTANTEIL_KNOEPFE = 0.5
MINDESTANTEIL_FELDER = 0.1
CHALLENGE_MUSTER = re.compile(
    r"radware bot manager|validate\.perfdrive\.com|captcha-delivery\.com|px-captcha"
    r"|cf-chl-|attention required! \| cloudflare|incapsula incident"
    r"|ein mensch sind|are you a (?:human|robot)",
    re.I,
)


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
class Gescheitert:
    """Eine Anfrage, die hinausging oder hinaus sollte und keine Antwort bekam.

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
    text: str | None = None
    beleg: Belegpaket | None = None
    beleg_status: str = OHNE_WERT

    @property
    def gueltig(self) -> bool:
        """Wahr nur für eine erfasste Kombination mit Beleg."""
        return self.status == ERFASST and self.beleg_status == BELEGT


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
    """Ein Lauf über eine Produktseite: Status, Ergebnisse, Struktur, Verworfenes.

    ``bezug`` ist die Strukturbilanz, gegen die ``pruefe_struktur`` den Lauf maß.
    """

    anbieter: str
    adresse: str
    status: str = LAUF_GELESEN
    grund: str | None = None
    http_status: int | None = None
    ergebnisse: list[Kombiergebnis] = field(default_factory=list)
    struktur: Strukturbilanz = field(default_factory=Strukturbilanz)
    verworfen: list[Verworfen] = field(default_factory=list)
    gescheitert: list[Gescheitert] = field(default_factory=list)
    bezug: Strukturbilanz | None = None


def abruf_gestoert(status: int | None) -> str | None:
    """Grund, wenn der HTTP-Status den Abruf stört (202, 4xx, 5xx), sonst ``None``."""
    if status is None:
        return "Abruf gestört (keine Antwort)"
    if status == CHALLENGE_STATUS or status >= FEHLER_AB_STATUS:
        return f"Abruf gestört (HTTP {status})"
    return None


def bot_schutz(
    status: int | None, typ: str, koerper: str, *, json_erwartet: bool = False
) -> str | None:
    """Grund, wenn eine Antwort nach Bot-Schutz oder Störung aussieht, sonst ``None``.

    HTTP 202, 4xx oder 5xx; eine HTML-Seite, wo ``json_erwartet`` gilt; oder ein
    Muster aus ``CHALLENGE_MUSTER`` im Körper.
    """
    gestoert = abruf_gestoert(status)
    if gestoert is not None:
        return gestoert
    if json_erwartet and "html" in typ.lower():
        return f"Abruf gestört (HTML statt JSON, HTTP {status})"
    treffer = CHALLENGE_MUSTER.search(koerper)
    if treffer is not None:
        return f"Abruf gestört (Challenge „{treffer[0]}“, HTTP {status})"
    return None


def mit_beleg(
    ergebnis: Kombiergebnis, paket: Belegpaket | None, grund: str | None
) -> Kombiergebnis:
    """Hängt den Beleg an; ohne Beleg werden gelesene Werte zum Befund mit Grund."""
    if paket is not None:
        return replace(ergebnis, beleg=paket, beleg_status=BELEGT)
    gelesen = any(getattr(ergebnis.werte, f) is not None for f in WERTFELDER)
    if not gelesen:
        return replace(ergebnis, beleg_status=OHNE_WERT)
    befund = Befund("beleg", grund or "Beleg fehlt")
    return replace(
        ergebnis,
        status=BEFUND,
        grund=ergebnis.grund or befund.grund,
        befunde=(*ergebnis.befunde, befund),
        beleg_status=BELEG_FEHLT,
    )


def ergebnisgrund(ergebnisse: list[Kombiergebnis]) -> str | None:
    """Grund, wenn jede Kombination ``nicht_angeboten`` ist; der Lauf las nichts."""
    if ergebnisse and all(e.status == NICHT_ANGEBOTEN for e in ergebnisse):
        return "keine Kombination angeboten: alle Knöpfe gesperrt"
    return None


def pruefe_struktur(lauf: Klicklauf, vorlauf: Klicklauf | None) -> str | None:
    """Grund, wenn der Lauf zu wenige Knöpfe oder Felder fand oder gegen den Bezug
    einbrach.

    Die Mindestanteile gelten immer, auch im ersten Lauf. Bezug ist die Bilanz des
    Vorlaufs, wenn er gelesen ist, sonst der Bezug, den er selbst trug;
    ``lauf.bezug`` hält ihn fest.
    """
    if vorlauf is not None:
        gelesen = vorlauf.status == LAUF_GELESEN
        lauf.bezug = vorlauf.struktur if gelesen else vorlauf.bezug
    aktuell = lauf.struktur
    minima = (
        ("Knöpfe", aktuell.anteil_knoepfe, MINDESTANTEIL_KNOEPFE),
        ("Felder", aktuell.anteil_felder, MINDESTANTEIL_FELDER),
    )
    for name, anteil, mindestens in minima:
        if anteil is not None and anteil < mindestens:
            return (
                f"Strukturbruch: nur {_prozent(anteil)} der gesuchten {name} gefunden"
                f" (mindestens {_prozent(mindestens)})"
            )
    if lauf.bezug is None:
        return None
    return strukturbruch(aktuell, lauf.bezug)


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
