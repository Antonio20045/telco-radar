"""Pfade der Klick-Karte in JSON-Daten: Punkte, Listenfilter, Auffächerung, Platzhalter.

Ein Pfad besteht aus Schritten, getrennt durch Punkte außerhalb eckiger Klammern
(``data.atomics[capacity.sortValue={speicher}].prices``). Ein Schritt ist ein Schlüssel,
eine Listenstelle als Zahl, ``*`` (jedes Element einer Liste, jeder Wert einer
Zuordnung) oder leer; dahinter stehen beliebig viele Filter ``[feld=wert]``: ``feld``
ist ein Punktpfad im Element, ``wert`` ein Text. Schlüssel und Filterwerte dürfen
Platzhalter ``{name}`` tragen; fehlt ein Wert dafür, ist das Ergebnis ``None``. Filter
und ``*`` fächern auf: nennen die Treffer mehr als einen verschiedenen Wert, ist das
Ergebnis mehrdeutig und ``None``, nie der erste (o2 ``paymentOptions[selected=true]``,
congstar ``variants[id={plan}]``, Vodafone ``atomics[capacity.sortValue={speicher}]``).
Verglichen wird ohne Markup, Leerraum sowie Groß- und Kleinschreibung
(``vergleichbar``). Dieses Modul ruft kein Netz.
"""

from __future__ import annotations

import html
import json
import re
from collections.abc import Mapping

ALLE = "*"
GRUND_KLAMMERN = "Klammern passen nicht"
GRUND_SCHRITT = "leerer oder falsch geformter Schritt"

_SCHRITT = re.compile(r"([^\[\]=]*)((?:\[[^\[\]=]+=[^\[\]]*\])*)")
_FILTER = re.compile(r"\[([^\[\]=]+)=([^\[\]]*)\]")
_PLATZHALTER = re.compile(r"\{([^{}]*)\}")
_MARKUP = re.compile(r"<[^>]*>")


def schritte(pfad: str) -> list[str]:
    """Die Schritte eines Pfads: getrennt an Punkten außerhalb eckiger Klammern."""
    teile, tiefe, anfang = [], 0, 0
    for stelle, zeichen in enumerate(pfad):
        if zeichen == "[":
            tiefe += 1
        elif zeichen == "]":
            tiefe -= 1
        elif zeichen == "." and tiefe == 0:
            teile.append(pfad[anfang:stelle])
            anfang = stelle + 1
    teile.append(pfad[anfang:])
    return teile


def pfadfehler(pfad: str) -> str | None:
    """Warum ``pfad`` kein gültiger Pfad ist; ``None``, wenn er gilt."""
    if pfad.count("[") != pfad.count("]"):
        return GRUND_KLAMMERN
    for schritt in schritte(pfad):
        treffer = _SCHRITT.fullmatch(schritt)
        if treffer is None or not (treffer[1] or treffer[2]):
            return f"{GRUND_SCHRITT} „{schritt}“"
        for feld, _ in _FILTER.findall(treffer[2]):
            grund = pfadfehler(feld)
            if grund is not None:
                return grund
    return None


def platzhalter(text: str) -> list[str]:
    """Die Namen der Platzhalter ``{name}`` in ``text``."""
    return _PLATZHALTER.findall(text)


def setze(text: str, platz: Mapping[str, str | None]) -> str | None:
    """``text`` mit eingesetzten Platzhaltern; ``None``, wenn einer keinen Wert hat."""
    fehlt = [n for n in platzhalter(text) if platz.get(n) is None]
    if fehlt:
        return None
    return _PLATZHALTER.sub(lambda t: str(platz[t[1]]), text)


def am_pfad(
    daten: object, pfad: str, platz: Mapping[str, str | None] | None = None
) -> object:
    """Der eine Wert an ``pfad``; ``None``, wenn er fehlt oder mehrdeutig ist."""
    werte = _alle(daten, pfad, {} if platz is None else platz)
    eindeutig: dict[str, object] = {}
    for wert in werte:
        if wert is not None:
            eindeutig.setdefault(_schluessel(wert), wert)
    if len(eindeutig) != 1:
        return None
    return next(iter(eindeutig.values()))


def vergleichbar(wert: object) -> str | None:
    """Ein einfacher Wert als Text ohne Markup, Leerraum, Groß- und Kleinschreibung."""
    if isinstance(wert, bool):
        text = "true" if wert else "false"
    elif isinstance(wert, float) and wert.is_integer():
        text = str(int(wert))
    elif isinstance(wert, int | float | str):
        text = str(wert)
    else:
        return None
    return "".join(ohne_markup(text).split()).casefold()


def ohne_markup(text: str) -> str:
    """``text`` ohne HTML-Tags und mit aufgelösten Entitäten (o2 „O<sub>2</sub>“)."""
    return html.unescape(_MARKUP.sub("", text))


def _alle(daten: object, pfad: str, platz: Mapping[str, str | None]) -> list[object]:
    knoten = [daten]
    for schritt in schritte(pfad):
        treffer = _SCHRITT.fullmatch(schritt)
        name = None if treffer is None else setze(treffer[1], platz)
        if treffer is None or name is None:
            return []
        knoten = [kind for k in knoten for kind in _kinder(k, name)]
        filter_ = [(f, setze(roh, platz)) for f, roh in _FILTER.findall(treffer[2])]
        if any(soll is None for _, soll in filter_):
            return []
        if filter_:
            knoten = [
                e
                for k in knoten
                for e in _elemente(k)
                if all(_gleich(_alle(e, f, platz), str(s)) for f, s in filter_)
            ]
    return knoten


def _kinder(knoten: object, name: str) -> list[object]:
    if not name:
        return [knoten]
    if name == ALLE:
        return _elemente(knoten)
    if isinstance(knoten, Mapping):
        return [knoten[name]] if name in knoten else []
    if isinstance(knoten, list) and name.isdigit() and int(name) < len(knoten):
        return [knoten[int(name)]]
    return []


def _elemente(knoten: object) -> list[object]:
    if isinstance(knoten, list):
        return list(knoten)
    if isinstance(knoten, Mapping):
        return list(knoten.values())
    return []


def _gleich(werte: list[object], soll: str) -> bool:
    ziel = vergleichbar(soll)
    return any(vergleichbar(w) == ziel for w in werte)


def _schluessel(wert: object) -> str:
    try:
        return json.dumps(wert, sort_keys=True, default=str)
    except (TypeError, ValueError):
        return repr(wert)
