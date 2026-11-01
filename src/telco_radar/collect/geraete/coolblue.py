"""Coolblue Deutschland: belegter Barpreis je konkreter Produktseite.

Keine Mobilfunktarife: PayPal-Raten werden erst im Checkout vereinbart
und sind mangels belegter Ratenkosten ausdrücklich KEINE Geräte-TCO.
Die Produktseite muss eine strukturierte, eindeutig zuordenbare Preisangabe
liefern; eine leere JS-Hülle oder Cross-Selling-Produkte sind kein Messwert.
"""

from __future__ import annotations

import re
from urllib.parse import urlparse

from .basis import GeraeteAbrufFehler
from .strukturdaten import produkte_aus_html

_PRODUKT = re.compile(r"/produkt/([0-9]+)(?:/|$)")


def lies(text: str, url: str = "") -> list[dict]:
    """Liest genau die aufgerufene Coolblue-Variante, ohne Tarifannahmen."""
    adresse = urlparse(url)
    treffer = _PRODUKT.search(adresse.path)
    if adresse.hostname != "www.coolblue.de" or treffer is None:
        raise GeraeteAbrufFehler(f"Coolblue: keine belegte Produktadresse: {url}")
    if not text or not text.strip():
        raise GeraeteAbrufFehler("Coolblue: leere Produktseite, nicht gelesen")

    saetze = produkte_aus_html(text)
    if not saetze:
        raise GeraeteAbrufFehler(
            "Coolblue: keine strukturierten Produktpreise; Format oder Zugriff geändert"
        )

    passend = []
    for satz in saetze:
        if not satz.get("titel") or satz.get("preis") is None:
            continue
        if satz.get("waehrung") != "EUR":
            continue
        quelllink = str(satz.get("url") or "").strip()
        produkt_sku = str(satz.get("sku") or "").strip()
        quelle = urlparse(quelllink)
        identitaet = _PRODUKT.search(quelle.path)
        if quelle.hostname and quelle.hostname not in (
            "coolblue.de",
            "www.coolblue.de",
        ):
            continue
        # Eine Preisangabe aus Empfehlungen / Cross-Selling darf niemals
        # dem angefragten Produkt zugeschrieben werden. Mindestens EINE
        # strukturierte Identität muss die URL-ID exakt belegen.
        if identitaet is not None and identitaet.group(1) != treffer.group(1):
            continue
        if produkt_sku and produkt_sku.isdecimal() and produkt_sku != treffer.group(1):
            continue
        if identitaet is None and produkt_sku != treffer.group(1):
            continue
        passend.append(
            {
                **satz,
                "url": url,
                "quelle": "coolblue_produkt",
                # Es sind reine Kaufpreise: keinerlei erfundene Finanzierungs-
                # oder Tarifkomponenten ergänzen.
            }
        )
    if len(passend) != 1:
        raise GeraeteAbrufFehler(
            f"Coolblue: {len(passend)} eindeutig passende Preise statt genau einem"
        )
    return passend
