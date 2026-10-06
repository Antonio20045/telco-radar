"""Optionsknöpfe einer Produktseite: lesen und die Folge der Kombinationen.

Der Klick-Crawler liest die Knöpfe je Dimension mit Wert, Sperre und Markierung
(``lies_optionen``) und führt die Werte als wachsende Menge: Erscheint nach einem Klick
eine neue Option, kommt sie hinzu (``vereinige``), und ``naechste`` liefert die erste
noch nicht besuchte Kombination. ``[None]`` steht für eine Dimension ohne gefundene
Knöpfe. Dieses Modul ruft kein Netz.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass
from typing import TYPE_CHECKING

from .klickkarte import DIMENSIONEN, Klickkarte

if TYPE_CHECKING:
    from playwright.sync_api import Page

Auswahl = tuple[str | None, ...]
_OPTIONEN_JS = """(knoepfe, art) => knoepfe.map((k) => [
  art.wert ? k.getAttribute(art.wert) : k.innerText,
  k.disabled === true || k.getAttribute("aria-disabled") === "true",
  k.getAttribute(art.marke) === art.markenwert,
])"""


@dataclass(frozen=True)
class Option:
    """Ein Optionsknopf: Wert ohne doppelte Leerzeichen, deaktiviert, gewählt."""

    wert: str | None
    deaktiviert: bool
    gewaehlt: bool


def lies_optionen(seite: Page, karte: Klickkarte, dimension: str) -> list[Option]:
    """Die Knöpfe einer Dimension im aktuellen Zustand der Seite."""
    knopf = karte.knoepfe[dimension]
    art = {
        "wert": knopf.wert_attribut,
        "marke": karte.gewaehlt.attribut,
        "markenwert": karte.gewaehlt.wert,
    }
    roh = seite.locator(knopf.selektor).evaluate_all(_OPTIONEN_JS, art)
    return [Option(_wert(w), bool(aus), bool(an)) for w, aus, an in roh]


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


def _wert(roh: object) -> str | None:
    text = " ".join(roh.split()) if isinstance(roh, str) else ""
    if not text:
        return None
    return text
