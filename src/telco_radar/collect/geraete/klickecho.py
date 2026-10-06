"""Echo nach dem Klick: ein Wert gilt nur, wenn Text, Antwort und Variante passen.

Nach jedem Klick liest der Klick-Crawler dieselben Werte zweimal (Datenkonzept
Geräteradar, Abschnitt 8): aus dem sichtbaren Text der Preiszusammenfassung
(``lies_zusammenfassung`` in ``klicktext``) und aus der mitgeschnittenen Antwort über
die Pfade der Klick-Karte (``lies_antwort``). Die Antwort nennt ihre Variante über Pfade
in der JSON-Antwort oder Parameter ihrer Adresse. ``pruefe_echo`` übernimmt einen Wert
nur, wenn beide ihn gleich nennen und Seite wie Antwort die gewählte Variante zeigen;
eine gewählte Option, die sich nicht lesen lässt, bestätigt nichts. Sonst entsteht ein
``Befund`` mit Grund. Fehlt ein Wert auf beiden Seiten, ist er ``None`` und eine
benannte Lücke, nie 0. Unbegrenztes Volumen ist ``math.inf`` wie im Tarifmodell. Eine
Laufzeit gilt nur als Monatsangabe („24 Monate“, „24 x“ oder reine Zahl), sonst ist sie
``None``. Deutsche Zahlen liest ``tarif_model.zahl``. Dieses Modul ruft kein Netz.
"""

from __future__ import annotations

import math
import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any
from urllib.parse import parse_qs, urlsplit

from ...tarif_model import Preisphase, zahl
from .klickkarte import DIMENSIONEN, PHASENFELD, WERTFELDER, Antwortmuster, Phasenpfad
from .klicktext import Preiswerte, nennt_volumen, phase, volumen_aus_zeile
from .klicktext import lies_zusammenfassung as lies_zusammenfassung

CENT_TOLERANZ = 0.005
GANZZAHLFELDER = frozenset({"ratenzahl", "tarifbindung"})
VOLUMENFELD = "volumen_gb"
LAUFZEIT = "laufzeit"
GRUND_OHNE_ANTWORT = "keine Antwort mitgeschnitten"
GRUND_KEINE_WERTE = "weder Text noch Antwort nennen Preiswerte"
KEINE_AUSWAHL = "keine Auswahl"
GRUND_UNLESBAR = "gewählte Option nicht lesbar"

_GANZZAHL = re.compile(r"\d+")
_MONATSANGABE = re.compile(r"(\d+)\s*(?:Monat|x\b|×)", re.I)
_NUR_ZAHL = re.compile(r"\s*(\d+)\s*")


@dataclass(frozen=True)
class Variante:
    """Speicher, Tarif und Ratenlaufzeit in Monaten; ``None`` heißt nicht bestimmt."""

    speicher: str | None = None
    tarif: str | None = None
    laufzeit: int | None = None


@dataclass(frozen=True)
class Antwortlesung:
    """Werte der Antwort und die Variante, die sie nennt (nur abgebildete Teile)."""

    werte: Preiswerte
    variante: Mapping[str, str | int | None]


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

    @property
    def stimmt(self) -> bool:
        """Wahr, wenn es keinen Befund gibt."""
        return not self.befunde


def variante_aus(speicher: object, tarif: object, laufzeit: object) -> Variante:
    """Liest eine Variante einheitlich: Text ohne Ränder, Laufzeit als Monatszahl."""
    return Variante(_als_text(speicher), _als_text(tarif), _monate(laufzeit))


def lies_antwort(
    nutzlast: object, muster: Antwortmuster, url: str | None = None
) -> Antwortlesung:
    """Liest dieselben Werte aus der JSON-Antwort über die Pfade der Klick-Karte.

    Die Variante steht an den Pfaden ``muster.variante`` oder in den Parametern
    ``muster.parameter`` der Adresse ``url``; fehlt sie dort, ist sie ``None``.
    """
    werte: dict[str, Any] = {
        feld: _feldwert(feld, nutzlast, pfad) for feld, pfad in muster.pfade.items()
    }
    frage = parse_qs(urlsplit(url).query) if url is not None else {}
    variante = {
        d: _dimension(d, frage.get(name, [None])[0])
        for d, name in muster.parameter.items()
    }
    variante.update(
        {
            d: _dimension(d, _am_pfad(nutzlast, pfad))
            for d, pfad in muster.variante.items()
        }
    )
    return Antwortlesung(werte=Preiswerte(**werte), variante=variante)


def pruefe_echo(
    gewaehlt: Variante,
    angezeigt: Variante,
    text: Preiswerte,
    antwort: Antwortlesung | None,
) -> Echo:
    """Übernimmt jeden Wert, den Text und Antwort zur Variante gleich nennen."""
    befunde = _variantenbefunde(gewaehlt, angezeigt, antwort)
    if antwort is None:
        befunde.append(Befund("antwort", GRUND_OHNE_ANTWORT))
    if befunde or antwort is None:
        return Echo(Preiswerte(), tuple(befunde), ())
    bestaetigt: dict[str, Any] = {}
    luecken = []
    for feld in WERTFELDER:
        im_text, in_antwort = getattr(text, feld), getattr(antwort.werte, feld)
        befund = _vergleiche(feld, im_text, in_antwort)
        if befund is not None:
            befunde.append(befund)
        elif im_text is None:
            luecken.append(feld)
        else:
            bestaetigt[feld] = im_text
    raten = _ratenbefund(gewaehlt, bestaetigt.get("ratenzahl"))
    if raten is not None:
        del bestaetigt["ratenzahl"]
        befunde.append(raten)
    if not bestaetigt and not befunde:
        befunde.append(Befund("werte", GRUND_KEINE_WERTE))
    return Echo(Preiswerte(**bestaetigt), tuple(befunde), tuple(luecken))


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
        if ist != soll:
            grund = f"Seite zeigt {_option(ist)} statt {soll}"
            befunde.append(Befund(f"variante.{dimension}", grund))
        if dimension in genannt and genannt[dimension] != soll:
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


def _feldwert(feld: str, nutzlast: object, pfad: str | Phasenpfad) -> object:
    if isinstance(pfad, Phasenpfad):
        return _phasen_aus_liste(_am_pfad(nutzlast, pfad.liste), pfad)
    roh = _am_pfad(nutzlast, pfad)
    if feld == PHASENFELD:
        betrag = _betrag(roh)
        return None if betrag is None else (Preisphase(1, None, betrag),)
    if feld in GANZZAHLFELDER:
        return _ganzzahl(roh)
    if feld == VOLUMENFELD:
        return _volumen(roh)
    return _betrag(roh)


def _phasen_aus_liste(liste: object, pfad: Phasenpfad) -> tuple[Preisphase, ...] | None:
    if not isinstance(liste, list) or not liste:
        return None
    phasen = []
    for eintrag in liste:
        von = _ganzzahl(_am_pfad(eintrag, pfad.von))
        bis = _ganzzahl(_am_pfad(eintrag, pfad.bis))
        betrag = _betrag(_am_pfad(eintrag, pfad.betrag))
        teil = None if von is None else phase(von, bis, betrag)
        if teil is None:
            return None
        phasen.append(teil)
    return tuple(sorted(phasen, key=lambda p: p.von_monat))


def _am_pfad(nutzlast: object, pfad: str) -> object:
    knoten = nutzlast
    for teil in pfad.split("."):
        if isinstance(knoten, Mapping):
            knoten = knoten.get(teil)
        elif isinstance(knoten, list) and teil.isdigit() and int(teil) < len(knoten):
            knoten = knoten[int(teil)]
        else:
            return None
    return knoten


def _betrag(roh: object) -> float | None:
    if isinstance(roh, bool):
        return None
    if isinstance(roh, int | float):
        return float(roh) if math.isfinite(roh) else None
    return zahl(roh) if isinstance(roh, str) else None


def _ganzzahl(roh: object) -> int | None:
    if isinstance(roh, bool):
        return None
    if isinstance(roh, int | float):
        return int(roh) if float(roh).is_integer() else None
    treffer = _GANZZAHL.search(roh) if isinstance(roh, str) else None
    return int(treffer[0]) if treffer else None


def _monate(roh: object) -> int | None:
    if not isinstance(roh, str):
        return _ganzzahl(roh)
    treffer = _NUR_ZAHL.fullmatch(roh) or _MONATSANGABE.search(roh)
    return int(treffer[1]) if treffer else None


def _volumen(roh: object) -> float | None:
    if isinstance(roh, str) and nennt_volumen(roh):
        return volumen_aus_zeile(roh)
    return _betrag(roh)


def _dimension(dimension: str, roh: object) -> str | int | None:
    return _monate(roh) if dimension == LAUFZEIT else _als_text(roh)


def _als_text(roh: object) -> str | None:
    text = "" if roh is None or isinstance(roh, bool) else str(roh).strip()
    if not text:
        return None
    return text
