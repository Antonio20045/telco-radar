"""Optionen als eigene Adressen: Links und Attribute, die die Seite selbst zeigt.

Telekom führt den Tarif über die Seitenadresse (``tariffId``), freenet jedes Bündel auf
einer eigenen Seite (``ts`` in der Tarifliste), 1&1 den Tarif über ``chosenTariff``.
``lies_adressen`` liest je Element zu ``Adressen.selektor`` das Attribut, löst es gegen
die Seitenadresse auf und nimmt den Parameter ``Adressen.parameter`` als Optionswert; je
Wert gilt die erste Adresse. Adressen werden nie zusammengesetzt oder hochgezählt
(CLAUDE.md Regel 2 und 4): es gilt nur, was die Seite zeigt. Eine Adresse auf einem
anderen Host, ohne den Parameter oder ein Element ohne das Attribut ist keine Option,
sondern bleibt mit Grund stehen. ``pruefe_robots`` fragt robots.txt am Tor, bevor eine
Adresse geladen wird; eine gesperrte steht in ``verworfen`` und mit Grund im Lauf.
``ohne_adresse`` macht daraus eine Kombination ``nicht_erfasst``, nie ein leeres
Ergebnis. Dieses Modul ruft kein Netz außer über die Seite.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING
from urllib.parse import parse_qs, urljoin, urlsplit

from playwright.sync_api import Error as PlaywrightFehler

from .klickecho import variante_aus
from .klickkarte import DIMENSIONEN, Adressen
from .klicklauf import NICHT_ERFASST, Klicklauf, Kombiergebnis, Verworfen
from .klickspur import WEB_SCHEMA, ohne_geheimnisse
from .klicktor import Tor, kurz

if TYPE_CHECKING:
    from playwright.sync_api import Page

log = logging.getLogger(__name__)

GRUND_FREMDER_HOST = "Adresse auf anderem Host"
GRUND_OHNE_ATTRIBUT = "Element ohne Attribut"
_ADRESSEN_JS = "(elemente, a) => elemente.map((e) => e.getAttribute(a))"


@dataclass(frozen=True)
class Adresse:
    """Eine Option als Adresse; ``grund`` nennt, warum sie nicht geladen wird."""

    wert: str | None
    url: str
    grund: str | None = None


def lies_adressen(seite: Page, adressen: Adressen) -> list[Adresse]:
    """Die Adressen, die die Seite zeigt; leer, wenn kein Element passt."""
    try:
        roh = seite.locator(adressen.selektor).evaluate_all(
            _ADRESSEN_JS, adressen.attribut
        )
    except PlaywrightFehler as fehler:
        grund = f"Adressen {adressen.selektor} nicht lesbar: {kurz(fehler)}"
        log.warning("Klick-Crawler: %s", grund)
        return [Adresse(None, seite.url, grund)]
    host = urlsplit(seite.url).hostname
    ergebnis: dict[str, Adresse] = {}
    for eintrag in roh:
        adresse = _adresse(seite.url, host, eintrag, adressen)
        schluessel = adresse.url if adresse.wert is None else adresse.wert
        ergebnis.setdefault(schluessel, adresse)
    return list(ergebnis.values())


def pruefe_robots(adresse: Adresse, tor: Tor, lauf: Klicklauf) -> Adresse:
    """Die Adresse mit Grund, wenn robots.txt sie sperrt; dazu in verworfen."""
    if adresse.grund is not None:
        return adresse
    darf, grund = tor.darf(adresse.url)
    if darf:
        return adresse
    lauf.verworfen.append(Verworfen(adresse.url, grund, adresse.url))
    return replace(adresse, grund=f"{grund} ({ohne_geheimnisse(adresse.url)})")


def ohne_adresse(dimension: str, adresse: Adresse) -> Kombiergebnis:
    """Die Kombination einer Adresse, die nicht geladen wird: ``nicht_erfasst``."""
    auswahl = tuple(adresse.wert if d == dimension else None for d in DIMENSIONEN)
    return Kombiergebnis(
        variante_aus(*auswahl), NICHT_ERFASST, adresse.grund, auswahl=auswahl
    )


def _adresse(
    seite_url: str, host: str | None, roh: object, adressen: Adressen
) -> Adresse:
    if not isinstance(roh, str) or not roh.strip():
        grund = f"{GRUND_OHNE_ATTRIBUT} {adressen.attribut} ({adressen.selektor})"
        return Adresse(None, seite_url, grund)
    url = urljoin(seite_url, roh.strip())
    teile = urlsplit(url)
    sauber = ohne_geheimnisse(url)
    if teile.scheme not in WEB_SCHEMA or teile.hostname != host:
        return Adresse(None, url, f"{GRUND_FREMDER_HOST} ({sauber})")
    werte = parse_qs(teile.query).get(adressen.parameter)
    if not werte or not werte[0].strip():
        grund = f"Adresse ohne Parameter {adressen.parameter} ({sauber})"
        return Adresse(None, url, grund)
    return Adresse(werte[0].strip(), url)
