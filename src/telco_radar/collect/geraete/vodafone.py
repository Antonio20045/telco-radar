"""Vodafone: der eigene Preis, ohne den es keinen Vergleich gibt.

WARUM DIESER ADAPTER ZUERST GEBAUT WURDE
----------------------------------------
Die Seite beantwortet die Frage "wer ist guenstiger als Vodafone?". Ohne die
eigene Listung hat diese Frage keinen Bezugspunkt - jede andere Zahl steht
dann allein da. Deshalb ist Vodafone der erste neue Anbieter dieser Stufe und
nicht der letzte.

DER WEG, GEMESSEN AM 28.08.2026
-------------------------------
Im Roh-HTML von /privat/handys-tablets-tarife/alle-smartphones.html steht
kein Preis - das war der Befund vom 11.08.2026 und er stimmt weiterhin. Der
Preis entsteht im Browser aus derselben oeffentlichen Schnittstelle, die
diese Seite selbst benutzt:

    GET https://api.vodafone.de/glados/v2/hardware/v2
        ?businessTransaction=newContract&salesChannel=Online.Consumer
    GET https://api.vodafone.de/glados/v2/hardware/v2/virtualItem/<id>?…

Die Adresse, die zwei Pflichtparameter und der oeffentliche Browser-Schluessel
stehen woertlich in Vodafones eigenem Skriptbuendel
`/simplicity/device-overview/device-overview.bundle.js`; jeder Besucher der
Seite schickt sie mit. `api.vodafone.de` hat keine robots.txt (HTTP 404, also
keine Regeln).

ZWEI PREISE, UND NUR EINER IST DER GERAETEPREIS
-----------------------------------------------
Die Liste traegt unter `prices.composition` ausschliesslich Buendelzahlen
(Tarif plus Geraet, 1 EUR Anzahlung). Der Preis OHNE Vertrag steht eine Ebene
tiefer, je Variante, unter

    atomics[].prices.hardware.priceByType.rate.onetime.withoutDiscounts.gross

Deshalb ruft dieser Adapter je Geraet die Detailnutzlast ab, statt sich die
Liste zu sparen: die Liste allein haette 1-Euro-Lockpreise geliefert, und
genau die haelt der Lockpreis-Waechter seit dem 10.08.2026 heraus.

DIE REGEL "NUR VERLINKTE ADRESSEN" GILT UNVERAENDERT
----------------------------------------------------
Die `virtualItemId` jedes Geraets steht in der Nutzlast der Einstiegsseite.
Es wird keine ID hochgezaehlt - dieselbe Grenze wie beim Tarif-Sammler
(§ 87b UrhG).
"""
from __future__ import annotations

import json
import re
from typing import Optional
from urllib.parse import urlsplit

from . import GeraeteAbrufFehler

# Die zwei Pflichtparameter. Ohne sie antwortet die Schnittstelle mit
# HTTP 400 und nennt das fehlende Feld beim Namen - beide Werte stammen aus
# dem Skriptbuendel der Seite, nicht aus einem Versuch.
_PARAMETER = "businessTransaction=newContract&salesChannel=Online.Consumer"

_GB_RE = re.compile(r"(\d+)\s*(GB|TB)", re.IGNORECASE)


def _json(text: str, was: str) -> dict:
    try:
        daten = json.loads(text or "")
    except (json.JSONDecodeError, ValueError) as exc:
        raise GeraeteAbrufFehler(f"{was} unlesbar: {exc}") from exc
    if not isinstance(daten, dict):
        raise GeraeteAbrufFehler(f"{was}: kein Objekt")
    return daten


def _speicher_gb(label: str) -> Optional[int]:
    """"256 GB" -> 256, "1 TB" -> 1024.

    Bewusst am `displayLabel` und nicht am `sortValue`: der ist in Mebibyte
    (262144 fuer 256 GB) und braeuchte eine zweite Umrechnung, die bei
    1 TB stillschweigend danebenliegen kann.
    """
    m = _GB_RE.search(label or "")
    if not m:
        return None
    zahl = int(m.group(1))
    return zahl * 1024 if m.group(2).upper() == "TB" else zahl


def _pfad(nutzlast: dict, *stufen):
    """Einen tiefen Pfad lesen, ohne bei jeder fehlenden Stufe zu werfen."""
    knoten = nutzlast
    for stufe in stufen:
        if not isinstance(knoten, dict):
            return None
        knoten = knoten.get(stufe)
    return knoten


def ernte(text: str, basis_url: str, pfadmuster="", kind: str = "") -> list[str]:
    """Aus der Geraeteliste die Detailadressen - eine je Geraet.

    Die Adressen entstehen aus den `virtualItemId`, die die Liste selbst
    nennt. Ein Geraet ohne Id wird uebersprungen und nicht geraten.
    """
    daten = _json(text, "Geraeteliste")
    geraete = _pfad(daten, "data", "devices") or []
    teile = urlsplit(basis_url)
    herkunft = f"{teile.scheme}://{teile.netloc}"
    out: list[str] = []
    gesehen: set[str] = set()
    for geraet in geraete:
        if not isinstance(geraet, dict):
            continue
        vid = str(geraet.get("virtualItemId") or "").strip()
        if not vid or vid in gesehen:
            continue
        gesehen.add(vid)
        out.append(f"{herkunft}/glados/v2/hardware/v2/virtualItem/{vid}"
                   f"?{_PARAMETER}")
    return out


def lies(text: str, url: str = "") -> list[dict]:
    """Aus der Detailnutzlast eines Geraets je Variante einen Rohsatz.

    Eine Variante ohne Geraetepreis wird uebergangen statt mit ihrer
    Buendelzahl gefuellt - eine Zuzahlung ohne Tarifreferenz ist nach der
    Disziplin dieses Projekts kein Preis.
    """
    daten = _json(text, "Geraetedetail")
    knoten = daten.get("data") if isinstance(daten.get("data"), dict) else daten
    modell = str(knoten.get("modelName") or "").strip()
    if not modell:
        raise GeraeteAbrufFehler("Geraetedetail ohne modelName")

    # Die Produktseite, die ein Mensch aufrufen kann. Der rohe
    # Schnittstellenaufruf waere als Quellenlink wertlos: die Seite
    # verspricht zu jeder Zahl einen nachpruefbaren Beleg, und niemand
    # prueft eine JSON-Antwort mit Schluessel nach.
    hubpage = str(_pfad(knoten, "hubpage", "href") or "").strip()

    out: list[dict] = []
    for atom in (knoten.get("atomics") or []):
        if not isinstance(atom, dict):
            continue
        preis = _pfad(atom, "prices", "hardware", "priceByType", "rate",
                      "onetime", "withoutDiscounts", "gross")
        if preis is None:
            continue
        speicher = _speicher_gb(str(_pfad(atom, "capacity", "displayLabel") or ""))
        farbe = str(_pfad(atom, "color", "displayLabel") or "").strip()
        # Der Titel wird aus MODELL, Speicher und Farbe gebaut, nicht aus
        # `label` uebernommen: dort steht "Google Pixel Hibiscus (256 GB)" -
        # ohne die Generation, weil die Farbe den Modellnamen verdraengt hat.
        # Aus so einem Titel findet die Geraeteerkennung ihren Katalogeintrag
        # nicht mehr.
        titel = " ".join(x for x in (modell,
                                     f"{speicher} GB" if speicher else "",
                                     farbe) if x)
        out.append({
            "titel": titel,
            "preis": float(preis),
            "waehrung": "EUR",
            # `shippingInfo` nennt einen Liefertermin, wenn es einen gibt.
            # Daraus "lieferbar" zu machen waere eine Behauptung ueber den
            # Lagerbestand, die dort nicht steht.
            "verfuegbarkeit": ("lieferbar"
                               if _pfad(atom, "shippingInfo", "date")
                               else "unbekannt"),
            "sku": str(atom.get("hardwareId") or "").strip(),
            "ean": "",
            "farbe": farbe,
            "speicher_gb": speicher,
            "url": hubpage,
            "quelle": "vodafone_api",
        })
    return out
