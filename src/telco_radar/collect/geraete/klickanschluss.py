"""1&1: Anschlusspreis je Tarif aus der Tarifdetail-Seite im Klick-Tageslauf.

Lesart der ``uebersichten`` von 1&1 (``klickuebersicht.LESARTEN``): die sieben
Tarifdetail-Seiten aus ``config/klick_tageslauf.yaml``. Je Seite genau ein Satz mit
``art`` ``ART_ANSCHLUSS``, dem Tarif-Slug aus ``chosenTariff`` der Seitenadresse und
der einmaligen Bereitstellungsgebühr „Tarif mit Smartphone“
(``einsundeins.bereitstellungsgebuehr``). ``klickrohsatz`` setzt ihn auf die Sätze der
Produktseiten mit demselben Tarif. Ohne Slug oder Betrag ist die Seite gestört
(``GeraeteAbrufFehler``), nie ein Nullwert.
"""

from __future__ import annotations

from urllib.parse import parse_qs, urlsplit

from .basis import GeraeteAbrufFehler
from .einsundeins import bereitstellungsgebuehr

ART_ANSCHLUSS = "anschluss"


def anschluss_saetze(text: str, adresse: str) -> list[dict]:
    """Der eine Anschluss-Satz der Tarifdetail-Seite ``adresse``."""
    slug = (parse_qs(urlsplit(adresse).query).get("chosenTariff") or [""])[0].strip()
    if not slug:
        raise GeraeteAbrufFehler("Tarifdetail-Seite ohne chosenTariff in der Adresse")
    gebuehr = bereitstellungsgebuehr(text)
    if gebuehr is None:
        raise GeraeteAbrufFehler(f"Tarifdetail-Seite {slug} ohne Bereitstellungsgebühr")
    return [{"art": ART_ANSCHLUSS, "tarif_slug": slug, "anschlusspreis": gebuehr}]


def kein_folgelink(_text: str) -> None:
    """Eine Tarifdetail-Seite hat keine Folgeseite."""
    return None
