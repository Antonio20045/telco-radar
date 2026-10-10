"""Echo nach dem Klick: ein Wert gilt nur, wenn Text, Antwort und Variante passen.

Nach jedem Klick liest der Klick-Crawler dieselben Werte zweimal (Datenkonzept
Geräteradar, Abschnitt 8): aus dem sichtbaren Text der Preiszusammenfassung
(``lies_zusammenfassung`` in ``klicktext``) und aus der mitgeschnittenen Antwort über
die Pfade der Klick-Karte (``lies_antwort`` in ``klickantwort``). Die Antwort nennt
ihre Variante über Pfade in der JSON-Antwort oder Parameter ihrer Adresse.
``pruefe_echo`` übernimmt einen Wert nur, wenn beide ihn gleich nennen und Seite wie
Antwort die gewählte Variante zeigen; eine gewählte Option, die sich nicht lesen
lässt, bestätigt nichts. Sonst entsteht ein ``Befund`` mit Grund. Fehlt ein Wert auf
beiden Seiten, ist er ``None`` und eine benannte Lücke, nie 0. Bei ``ein_vertrag``
(1&1, freenet) entfallen Rate und Ratenzahl planmäßig, verglichen werden dafür
Bündelbetrag und Einmalzahlung. Mit ``summe`` (Vodafone-Tarifauswahl, zwei Verträge)
nennt der Text nur die Monatssumme aus Rate und Tarif als Bündelbetrag: Rate und Tarif
von Monat 1 gelten aus der Antwort nur, wenn der Text dieselbe Summe nennt wie die
Antwort und Rate plus Tarif sie auf den Cent ergeben; sonst bleibt es ein Befund.
Unbegrenztes Volumen
ist ``math.inf`` wie im Tarifmodell. Optionen vergleicht das Echo ohne Markup,
Leerraum sowie Groß- und Kleinschreibung. Dieses Modul ruft kein Netz.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass, replace
from typing import Any

from ...tarif_model import Preisphase
from .klickantwort import LAUFZEIT as LAUFZEIT
from .klickantwort import Antwortlesung as Antwortlesung
from .klickantwort import adressparameter as adressparameter
from .klickantwort import als_text, monate
from .klickantwort import feldwert as feldwert
from .klickantwort import lies_antwort as lies_antwort
from .klickkarte import BUENDELFELDER, DIMENSIONEN, WERTFELDER
from .klickkartentypen import SUMMENFELD
from .klickpfad import vergleichbar
from .klicktext import Buendelwerte, Preiswerte
from .klicktext import lies_zusammenfassung as lies_zusammenfassung

CENT_TOLERANZ = 0.005
GRUND_OHNE_ANTWORT = "keine Antwort mitgeschnitten"
GRUND_KEINE_WERTE = "weder Text noch Antwort nennen Preiswerte"
KEINE_AUSWAHL = "keine Auswahl"
GRUND_UNLESBAR = "gewählte Option nicht lesbar"
UEBER_DIE_SUMME = ("rate", "tarifphasen")


@dataclass(frozen=True)
class Variante:
    """Speicher, Tarif und Ratenlaufzeit in Monaten; ``None`` heißt nicht bestimmt."""

    speicher: str | None = None
    tarif: str | None = None
    laufzeit: int | None = None


@dataclass(frozen=True)
class Befund:
    """Ein Wert, der nicht übernommen wurde, und warum."""

    feld: str
    grund: str


@dataclass(frozen=True)
class Echo:
    """Übernommene Werte, Befunde und Lücken einer Kombination."""

    werte: Preiswerte
    befunde: tuple[Befund, ...]
    luecken: tuple[str, ...]
    buendel: Buendelwerte = Buendelwerte()

    @property
    def stimmt(self) -> bool:
        """Wahr, wenn es keinen Befund gibt."""
        return not self.befunde


def variante_aus(speicher: object, tarif: object, laufzeit: object) -> Variante:
    """Liest eine Variante einheitlich: Text ohne Ränder, Laufzeit als Monatszahl."""
    return Variante(als_text(speicher), als_text(tarif), monate(laufzeit))


def gleiche_option(a: object, b: object) -> bool:
    """Wahr, wenn zwei Optionswerte ohne Markup, Leerraum und Groß-/Kleinschreibung
    gleich sind; ``None`` ist nur ``None`` gleich."""
    if a is None or b is None:
        return a is None and b is None
    return vergleichbar(a) == vergleichbar(b)


def pruefe_echo(
    gewaehlt: Variante,
    angezeigt: Variante,
    text: Preiswerte,
    antwort: Antwortlesung | None,
    *,
    buendel: Buendelwerte | None = None,
    entfallen: tuple[str, ...] = (),
    summe: bool = False,
) -> Echo:
    """Übernimmt jeden Wert, den Text und Antwort zur Variante gleich nennen.

    ``buendel`` sind die Bündelwerte aus dem Text (``ein_vertrag`` oder ``summe``);
    Felder in ``entfallen`` fallen planmäßig weg und sind weder Befund noch Lücke.
    Mit ``summe`` bestätigt die Monatssumme Rate und Tarif (``_ueber_die_summe``).
    """
    befunde = _variantenbefunde(gewaehlt, angezeigt, antwort)
    if antwort is None:
        befunde.append(Befund("antwort", GRUND_OHNE_ANTWORT))
    if befunde or antwort is None:
        return Echo(Preiswerte(), tuple(befunde), ())
    luecken: list[str] = []
    felder = tuple(f for f in WERTFELDER if f not in entfallen)
    if summe:
        text = _ueber_die_summe(text, buendel, antwort, befunde)
    bestaetigt = _bestaetige(felder, text, antwort.werte, befunde, luecken)
    buendelfelder = BUENDELFELDER if buendel is not None else ()
    gebuendelt = _bestaetige(buendelfelder, buendel, antwort.buendel, befunde, luecken)
    raten = _ratenbefund(gewaehlt, bestaetigt.get("ratenzahl"))
    if raten is not None:
        del bestaetigt["ratenzahl"]
        befunde.append(raten)
    if not bestaetigt and not gebuendelt and not befunde:
        befunde.append(Befund("werte", GRUND_KEINE_WERTE))
    return Echo(
        Preiswerte(**bestaetigt),
        tuple(befunde),
        tuple(luecken),
        Buendelwerte(**gebuendelt),
    )


def seitenbefunde(gewaehlt: Variante, angezeigt: Variante) -> tuple[Befund, ...]:
    """Befunde, wo die Seite eine andere als die gewählte Variante zeigt oder eine
    gewählte Option unlesbar ist; ohne Antwort."""
    return tuple(_variantenbefunde(gewaehlt, angezeigt, None))


def summenfundorte(
    fundorte: Mapping[str, tuple[str, str]], werte: Preiswerte
) -> dict[str, tuple[str, str]]:
    """Die Fundorte des Texts; über die Summe bestätigte Felder ohne eigenen Fundort
    tragen den Fundort der Summe (``pruefe_echo`` mit ``summe``)."""
    ort = fundorte.get(SUMMENFELD)
    if ort is None:
        return dict(fundorte)
    ueber = [f for f in UEBER_DIE_SUMME if getattr(werte, f) is not None]
    return {**{f: ort for f in ueber}, **fundorte}


def _ueber_die_summe(
    text: Preiswerte,
    buendel: Buendelwerte | None,
    antwort: Antwortlesung,
    befunde: list[Befund],
) -> Preiswerte:
    """``text`` mit Rate und Tarif der Antwort, wo der Text sie nicht nennt, nur wenn
    Text und Antwort dieselbe Summe nennen, der Tarif eine einzige Phase ab Monat 1 hat
    und Rate plus Tarif die Summe auf den Cent ergeben; ergeben sie sie nicht, ein
    Befund an der Summe. Sonst bleibt ``text`` unverändert (dann „fehlt im Text“)."""
    im_text = None if buendel is None else getattr(buendel, SUMMENFELD)
    in_antwort = getattr(antwort.buendel, SUMMENFELD)
    rate = antwort.werte.rate
    phasen = antwort.werte.tarifphasen or ()
    einzeln = len(phasen) == 1 and phasen[0].von_monat == 1
    if im_text is None or in_antwort is None or rate is None or not einzeln:
        return text
    tarif = phasen[0].betrag
    if not _gleich(im_text, in_antwort):
        return text
    if abs(rate + tarif - in_antwort) >= CENT_TOLERANZ:
        grund = (
            f"Rate {_deutsch(rate)} + Tarif {_deutsch(tarif)} ergibt nicht die "
            f"Summe {_deutsch(in_antwort)}"
        )
        befunde.append(Befund(SUMMENFELD, grund))
        return text
    ergaenzt = {f: getattr(antwort.werte, f) for f in UEBER_DIE_SUMME}
    fehlend = {f: w for f, w in ergaenzt.items() if getattr(text, f) is None}
    return replace(text, **fehlend)


def _bestaetige(
    felder: tuple[str, ...],
    text: object,
    antwort: object,
    befunde: list[Befund],
    luecken: list[str],
) -> dict[str, Any]:
    bestaetigt: dict[str, Any] = {}
    for feld in felder:
        im_text, in_antwort = getattr(text, feld), getattr(antwort, feld)
        befund = _vergleiche(feld, im_text, in_antwort)
        if befund is not None:
            befunde.append(befund)
        elif im_text is None:
            luecken.append(feld)
        else:
            bestaetigt[feld] = im_text
    return bestaetigt


def _ratenbefund(gewaehlt: Variante, raten: int | None) -> Befund | None:
    if raten is None or gewaehlt.laufzeit is None or raten == gewaehlt.laufzeit:
        return None
    grund = f"Seite nennt {raten} Raten, gewählt {gewaehlt.laufzeit} Monate"
    return Befund("ratenzahl", grund)


def _variantenbefunde(
    gewaehlt: Variante, angezeigt: Variante, antwort: Antwortlesung | None
) -> list[Befund]:
    befunde = []
    genannt = antwort.variante if antwort is not None else {}
    for dimension in DIMENSIONEN:
        soll = getattr(gewaehlt, dimension)
        if soll is None:
            befunde.append(Befund(f"variante.{dimension}", GRUND_UNLESBAR))
            continue
        ist = getattr(angezeigt, dimension)
        if not gleiche_option(ist, soll):
            grund = f"Seite zeigt {_option(ist)} statt {soll}"
            befunde.append(Befund(f"variante.{dimension}", grund))
        if dimension in genannt and not gleiche_option(genannt[dimension], soll):
            grund = f"Antwort nennt {_option(genannt[dimension])} statt {soll}"
            befunde.append(Befund(f"antwort.{dimension}", grund))
    return befunde


def _vergleiche(feld: str, im_text: object, in_antwort: object) -> Befund | None:
    if im_text is None and in_antwort is None:
        return None
    if im_text is None:
        return Befund(feld, f"fehlt im Text, Antwort {_zeige(in_antwort)}")
    if in_antwort is None:
        return Befund(feld, f"fehlt in der Antwort, Text {_zeige(im_text)}")
    if not _gleich(im_text, in_antwort):
        return Befund(feld, f"Text {_zeige(im_text)}, Antwort {_zeige(in_antwort)}")
    return None


def _gleich(a: object, b: object) -> bool:
    if isinstance(a, tuple) and isinstance(b, tuple):
        return len(a) == len(b) and all(map(_gleiche_phase, a, b))
    if isinstance(a, float) and isinstance(b, float):
        return a == b or abs(a - b) < CENT_TOLERANZ
    return a == b


def _gleiche_phase(a: Preisphase, b: Preisphase) -> bool:
    gleiche_monate = (a.von_monat, a.bis_monat) == (b.von_monat, b.bis_monat)
    return gleiche_monate and _gleich(a.betrag, b.betrag)


def _zeige(wert: object) -> str:
    if isinstance(wert, tuple):
        return "; ".join(map(_zeige_phase, wert))
    if isinstance(wert, float):
        return "unbegrenzt" if math.isinf(wert) else _deutsch(wert)
    return str(wert)


def _zeige_phase(p: Preisphase) -> str:
    bis = f"–{p.bis_monat}" if p.bis_monat is not None else " und danach"
    return f"Monat {p.von_monat}{bis}: {_deutsch(p.betrag)}"


def _deutsch(betrag: float) -> str:
    englisch = f"{betrag:,.2f}"
    return englisch.replace(",", " ").replace(".", ",").replace(" ", ".")


def _option(wert: object) -> str:
    return KEINE_AUSWAHL if wert is None else str(wert)
