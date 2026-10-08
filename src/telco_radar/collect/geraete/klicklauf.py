"""Ergebnis eines Klick-Laufs: Status je Kombination, Strukturwächter, Störung.

Der Klick-Crawler (``klickcrawler``) füllt diese Typen; dieses Modul ruft keinen Browser
und kein Netz. Je Kombination gilt einer von vier Zuständen: ``erfasst``,
``nicht_angeboten`` (die Seite zeigt die Option in Ruhe deaktiviert), ``nicht_erfasst``
(Knöpfe, Option oder Zusammenfassung nicht gefunden, Laufzeit nicht lesbar, nicht
besucht, Seite nicht zur Ruhe gekommen, Preisantwort über die Frist offen, kein
Preiswert gelesen) oder ``befund`` (das Echo widerspricht sich). ``lesestatus`` setzt
den Zustand einer Lesung: ohne ``PREISFELD`` (die Gerätrate), bei ``ein_vertrag`` ohne
``PREISFELD_EIN_VERTRAG`` (den Bündelbetrag) ist sie nie erfasst, auch wenn Tarif,
Volumen oder Bindung stimmen; die Ratenzahl spiegelt nur den Klick. Ein Lauf ist
``gelesen``, ``gestoert`` (Bot-Schutz, fehlender Kanarienwert, offene oder gescheiterte
Preisantwort, Strukturbruch, keine einzige angebotene Kombination), ``gesperrt``
(robots.txt sperrt Seite, Preisantwort oder Besuchszeit) oder ``zeitgrenze`` (die
Zeitgrenze des Aufrufers schnitt ihn ab; was er nicht besuchte, heißt so). Bot-Schutz
heißt ``bot_schutz``: HTTP 202, 4xx oder 5xx, ein bekanntes Challenge-Muster
(``CHALLENGE_MUSTER``) oder eine HTML-Seite, wo die Preisschnittstelle JSON liefern
soll. Gescheiterte Anfragen hält der Lauf mit Grund fest, ebenso jede Hilfsdatei, die
ohne Regeln in den Browser ging (``Hilfsdatei``, ``klickhilfe``).

Jede Kombination mit gelesenen Werten trägt ihren Beleg (``klickbeleg``) und
``beleg_status``: ``offen`` (gebaut, noch nicht im Archiv), ``belegt`` (Dateien in der
Ablage und Zeile im Manifest, gesetzt nur von ``belegarchiv``), ``fehlt`` oder
``ohne_wert``. Ein Wert ohne archivierten Beleg ist nicht gültig: ``beleg_fehlt``
macht eine erfasste Kombination zum ``befund`` mit Grund, die Werte bleiben sichtbar;
``gueltig`` gilt nur erfasst und belegt.

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
from .klicktext import Buendelwerte, Preiswerte

if TYPE_CHECKING:
    from .klickbeleg import Belegpaket
    from .klickdiagnose import Diagnose

ERFASST = "erfasst"
NICHT_ANGEBOTEN = "nicht_angeboten"
NICHT_ERFASST = "nicht_erfasst"
BEFUND = "befund"
LAUF_GELESEN = "gelesen"
LAUF_GESTOERT = "gestoert"
LAUF_GESPERRT = "gesperrt"
LAUF_ZEITGRENZE = "zeitgrenze"
BELEG_OFFEN = "offen"
BELEGT = "belegt"
BELEG_FEHLT = "fehlt"
OHNE_WERT = "ohne_wert"
PREISFELD = "rate"
"""Der Preiswert einer erfassten Kombination: die Gerätrate (``Preiswerte``)."""
PREISFELD_EIN_VERTRAG = "buendelbetrag"
"""Dasselbe bei ``ein_vertrag`` (1&1, freenet), wo Rate und Ratenzahl entfallen
(``Buendelwerte``)."""
GRUND_OHNE_RATE = "kein Gerätepreis gelesen (Rate)"
GRUND_OHNE_BUENDELBETRAG = "kein Bündelbetrag gelesen"
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


_ZEICHENSATZ = re.compile(r"charset=[\"']?([\w.:-]+)", re.I)
STANDARD_ZEICHENSATZ = "utf-8"


def antworttext(koerper: bytes, typ: str) -> str:
    """Der Körper als Text im Zeichensatz aus ``typ``, sonst UTF-8; nie ein Absturz.

    Playwrights ``text()`` liest nur UTF-8. Die Vodafone-Seite enthielt am 07.10.2026
    ein Byte aus ISO-8859-1, und der Fehler im Tor riss den ganzen Lauf mit. Ein
    unlesbares Byte wird zu U+FFFD; die Muster in ``CHALLENGE_MUSTER`` bleiben lesbar.
    """
    treffer = _ZEICHENSATZ.search(typ)
    zeichensatz = STANDARD_ZEICHENSATZ if treffer is None else treffer[1]
    try:
        return koerper.decode(zeichensatz, errors="replace")
    except LookupError:
        return koerper.decode(STANDARD_ZEICHENSATZ, errors="replace")


@dataclass(frozen=True)
class Verworfen:
    """Eine Adresse, die robots.txt sperrt; sie ging nicht hinaus, außer eine
    Hilfsdatei, deren Antwort keine war (``klickhilfe.KEINE_HILFSDATEI``).

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
class Hilfsdatei:
    """Ein Skript oder Stylesheet, das ohne Regeln in den Browser ging (``klicktor``).

    ``grund`` nennt die Antwort der robots.txt ihres Hosts (401 oder 403); ``anfrage``
    ist die Adresse, die die Seite anfragte; nach einer Umleitung weicht sie von
    ``url`` ab.
    """

    url: str
    art: str
    grund: str
    anfrage: str


@dataclass(frozen=True)
class Kombiergebnis:
    """Das Ergebnis einer Kombination aus Speicher, Tarif und Ratenlaufzeit.

    ``variante`` ist gelesen (Laufzeit als Monatszahl), ``auswahl`` die rohen Werte
    der Knöpfe in der Reihenfolge von ``klickkarte.DIMENSIONEN``. ``werte`` hält nur,
    was Text und Antwort gleich nennen; ``textwerte`` und ``antwortwerte`` sind die
    beiden Lesungen davor, ``None`` heißt nicht gelesen. ``buendel`` hat nur eine
    Karte mit ``vertragsform`` ``ein_vertrag``, ebenso ``textbuendel`` und
    ``antwortbuendel``, die beiden Lesungen der Bündelwerte. ``diagnose`` hat nur eine
    Kachel des Weiter-Schritts (``klickdiagnose``); ``echo_quelle`` nennt die Quelle,
    die statt der zweiten Lesung bestätigt hat (``klickkachel.QUELLE_KACHEL``).
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
    textwerte: Preiswerte | None = None
    antwortwerte: Preiswerte | None = None
    buendel: Buendelwerte | None = None
    textbuendel: Buendelwerte | None = None
    antwortbuendel: Buendelwerte | None = None
    diagnose: Diagnose | None = None
    echo_quelle: str | None = None

    @property
    def gueltig(self) -> bool:
        """Wahr nur für eine erfasste Kombination mit archiviertem Beleg."""
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

    def felder(self, gefunden: int, gesucht: int = len(WERTFELDER)) -> None:
        """Zählt die Wertfelder einer gelesenen oder fehlenden Zusammenfassung."""
        self.felder_gesucht += gesucht
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

    ``bezug`` ist die Strukturbilanz, gegen die ``pruefe_struktur`` den Lauf maß;
    ``hilfsdateien`` sind die Skripte und Stylesheets, die ohne Regeln geladen wurden.
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
    hilfsdateien: list[Hilfsdatei] = field(default_factory=list)
    bezug: Strukturbilanz | None = None


def fehlender_preis(
    werte: Preiswerte, buendel: Buendelwerte | None, *, ein_vertrag: bool = False
) -> str | None:
    """Der Grund, wenn der Preiswert der Lesung fehlt, sonst ``None``.

    Ohne ``ein_vertrag`` ist es ``PREISFELD`` in ``werte``, mit ihm
    ``PREISFELD_EIN_VERTRAG`` in ``buendel``.
    """
    if ein_vertrag:
        betrag = None if buendel is None else getattr(buendel, PREISFELD_EIN_VERTRAG)
        return GRUND_OHNE_BUENDELBETRAG if betrag is None else None
    return GRUND_OHNE_RATE if getattr(werte, PREISFELD) is None else None


def lesestatus(
    befunde: tuple[Befund, ...],
    werte: Preiswerte,
    buendel: Buendelwerte | None,
    *,
    ein_vertrag: bool = False,
) -> tuple[str, str | None]:
    """Zustand und Grund einer Lesung mit Echo: ``befund`` mit dem ersten Grund, ohne
    Preiswert ``nicht_erfasst`` mit dem Grund aus ``fehlender_preis``, sonst
    ``erfasst``."""
    if befunde:
        return BEFUND, befunde[0].grund
    fehlt = fehlender_preis(werte, buendel, ein_vertrag=ein_vertrag)
    if fehlt is not None:
        return NICHT_ERFASST, fehlt
    return ERFASST, None


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
    """Hängt den Beleg als ``offen`` an; ohne Beleg werden Werte zum Befund."""
    if paket is not None:
        return replace(ergebnis, beleg=paket, beleg_status=BELEG_OFFEN)
    gelesen = any(getattr(ergebnis.werte, f) is not None for f in WERTFELDER)
    gelesen = gelesen or (
        ergebnis.buendel is not None and ergebnis.buendel != Buendelwerte()
    )
    if not gelesen:
        return replace(ergebnis, beleg_status=OHNE_WERT)
    return beleg_fehlt(ergebnis, grund or "Beleg fehlt")


def beleg_fehlt(ergebnis: Kombiergebnis, grund: str) -> Kombiergebnis:
    """Der Beleg fehlt oder kam nicht ins Archiv: Befund mit Grund, nicht gültig."""
    befund = Befund("beleg", grund)
    return replace(
        ergebnis,
        status=BEFUND,
        grund=ergebnis.grund or grund,
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
