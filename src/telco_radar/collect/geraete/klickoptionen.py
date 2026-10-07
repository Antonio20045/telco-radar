"""Optionsknöpfe einer Produktseite: lesen und die Folge der Kombinationen.

Der Klick-Crawler liest die Knöpfe je Dimension mit Wert, Sperre und Markierung
(``lies_optionen``) und führt die Werte als wachsende Menge: Erscheint nach einem Klick
eine neue Option, kommt sie hinzu (``vereinige``), und ``naechste`` liefert die erste
noch nicht besuchte Kombination. ``[None]`` steht für eine Dimension ohne gefundene
Knöpfe. Der Wert kommt aus Attribut oder Text des Klickziels oder seines
Kind-Elements ``wert_in``, ``muster`` nimmt daraus die erste Gruppe; ein Wert, auf den
das Muster nicht passt, fehlt. Die Marke ist die der Dimension, sonst die der Karte:
Attribut gleich Wert oder ein CSS-Selektor, auf den das Klickziel passt. Eine feste
Dimension hat genau eine gewählte Option ohne Knopf. Dieses Modul ruft kein Netz.
"""

from __future__ import annotations

import itertools
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

from .klickkarte import DIMENSIONEN, Klickkarte

if TYPE_CHECKING:
    from playwright.sync_api import Page

Auswahl = tuple[str | None, ...]
_OPTIONEN_JS = """(knoepfe, art) => knoepfe.map((k) => {
  const traeger = art.wertIn ? k.querySelector(art.wertIn) : k;
  const wert = traeger === null ? null
    : (art.wert ? traeger.getAttribute(art.wert) : traeger.innerText);
  const an = art.passt ? k.matches(art.passt)
    : art.marke !== null && k.getAttribute(art.marke) === art.markenwert;
  return [wert, k.disabled === true || k.getAttribute("aria-disabled") === "true", an];
})"""


@dataclass(frozen=True)
class Option:
    """Ein Optionsknopf: Wert ohne doppelte Leerzeichen, deaktiviert, gewählt."""

    wert: str | None
    deaktiviert: bool
    gewaehlt: bool


def lies_optionen(seite: Page, karte: Klickkarte, dimension: str) -> list[Option]:
    """Die Knöpfe einer Dimension im aktuellen Zustand der Seite."""
    knopf = karte.knoepfe[dimension]
    if knopf.fest is not None or knopf.selektor is None:
        return [Option(knopf.fest, False, True)]
    marke = karte.marke(dimension)
    art = {
        "wert": knopf.wert_attribut,
        "wertIn": knopf.wert_in,
        "passt": None if marke is None else marke.passt,
        "marke": None if marke is None else marke.attribut,
        "markenwert": None if marke is None else marke.wert,
    }
    roh = seite.locator(knopf.selektor).evaluate_all(_OPTIONEN_JS, art)
    return [Option(_wert(w, knopf.muster), bool(a), bool(g)) for w, a, g in roh]


def angebotene_werte(optionen: list[Option]) -> list[str | None]:
    """Die Werte der Knöpfe in Reihenfolge; ``[None]``, wenn es keine gibt."""
    werte: list[str | None] = list(
        dict.fromkeys(o.wert for o in optionen if o.wert is not None)
    )
    return werte or [None]


def naechste(
    werte: dict[str, list[str | None]], besucht: set[Auswahl]
) -> Auswahl | None:
    """Die erste nicht besuchte Kombination der gesehenen Werte, sonst ``None``."""
    alle = itertools.product(*(werte[d] for d in DIMENSIONEN))
    return next((a for a in alle if a not in besucht), None)


def vereinige(alt: list[str | None], neu: list[str | None]) -> list[str | None]:
    """Hängt neu erschienene Werte an; verschwundene bleiben in der Folge."""
    if alt == [None]:
        return neu
    return alt + [w for w in neu if w is not None and w not in alt]


def wert_nach_muster(roh: str, muster: re.Pattern[str] | None) -> str | None:
    """Die erste Gruppe von ``muster`` in ``roh`` (ohne Gruppe der Treffer), sonst
    ``None``; ohne Muster ``roh``."""
    if muster is None:
        return roh
    treffer = muster.search(roh)
    if treffer is None:
        return None
    teil = treffer[1] if muster.groups else treffer[0]
    if teil is None or not teil.strip():
        return None
    return teil.strip()


def _wert(roh: object, muster: re.Pattern[str] | None) -> str | None:
    text = " ".join(roh.split()) if isinstance(roh, str) else ""
    if not text:
        return None
    return wert_nach_muster(text, muster)
