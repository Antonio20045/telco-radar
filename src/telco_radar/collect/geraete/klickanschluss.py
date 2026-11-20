"""1&1: Anschlusspreis je Tarif aus der Tarifdetail-Seite im Klick-Tageslauf.

Lesart der ``uebersichten`` von 1&1 (``klickuebersicht.LESARTEN``): die sieben
Tarifdetail-Seiten aus ``config/klick_tageslauf.yaml``. Je Seite genau ein Satz mit
``art`` ``ART_ANSCHLUSS``, dem Tarif-Slug aus ``chosenTariff`` der Seitenadresse und
der einmaligen Bereitstellungsgebühr „Tarif mit Smartphone“
(``einsundeins.bereitstellungsgebuehr``) und dem Tarifnamen der Überschrift
(``tariff-detail__heading``, sonst ``None``). ``klickrohsatz`` setzt ihn auf die Sätze
der Produktseiten mit demselben Slug, ``klickraster`` auf die Rastersätze mit demselben
Namen (``anschluesse``). Ohne Slug oder Betrag ist die Seite gestört
(``GeraeteAbrufFehler``), nie ein Nullwert.
"""

from __future__ import annotations

import re
from urllib.parse import parse_qs, urlsplit

from .basis import GeraeteAbrufFehler
from .einsundeins import bereitstellungsgebuehr, tarifname_bereinigt
from .klickergebnis import GELESENE_SEITEN
from .klickkartentypen import EIN_VERTRAG

ART_ANSCHLUSS = "anschluss"
_NAME = re.compile(r'class="tariff-detail__heading">\s*<h2>([^<]+)</h2>')


def anschluss_saetze(text: str, adresse: str) -> list[dict]:
    """Der eine Anschluss-Satz der Tarifdetail-Seite ``adresse``."""
    slug = (parse_qs(urlsplit(adresse).query).get("chosenTariff") or [""])[0].strip()
    if not slug:
        raise GeraeteAbrufFehler("Tarifdetail-Seite ohne chosenTariff in der Adresse")
    gebuehr = bereitstellungsgebuehr(text)
    if gebuehr is None:
        raise GeraeteAbrufFehler(f"Tarifdetail-Seite {slug} ohne Bereitstellungsgebühr")
    name = _NAME.search(text)
    return [
        {
            "art": ART_ANSCHLUSS,
            "tarif_slug": slug,
            "tarif_name": tarifname_bereinigt(name[1]) if name else None,
            "anschlusspreis": gebuehr,
        }
    ]


def anschluesse(daten: dict) -> dict[str, float]:
    """Anschlusspreis je Tarif-Slug und je Tarifname aus den heute gelesenen
    Tarifdetail-Seiten einer Ergebnisdatei, nur bei ``ein_vertrag``. Der Name trägt,
    wo die Kachel den Tarif mit Namen nennt (Nachweis ``tarifname``, 1&1 seit
    20.11.2026) und ihr Slug von dem der Detailseite abweicht (Unlimited XL:
    ``…-xl-mvl`` gegen ``…-xl-ovl``)."""
    if daten.get("vertragsform") != EIN_VERTRAG:
        return {}
    saetze = [
        roh
        for u in daten.get("uebersichten") or []
        if u.get("status") in GELESENE_SEITEN
        for roh in u.get("saetze") or []
        if roh.get("art") == ART_ANSCHLUSS
    ]
    je_slug = {str(roh.get("tarif_slug")): roh["anschlusspreis"] for roh in saetze}
    je_name = {
        str(roh["tarif_name"]): roh["anschlusspreis"]
        for roh in saetze
        if roh.get("tarif_name")
    }
    return {**je_name, **je_slug}


def kein_folgelink(_text: str) -> None:
    """Eine Tarifdetail-Seite hat keine Folgeseite."""
    return None
