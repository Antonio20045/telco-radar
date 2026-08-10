"""Preise aus STRUKTURIERTEN Daten - Stufe 2 der Rangfolge aus Teil C1.

Zwei Schreibweisen desselben Standards, in dieser Reihenfolge:

    1. JSON-LD   <script type="application/ld+json"> mit schema.org/Product
    2. Microdata itemprop="price" innerhalb itemtype=".../Offer"

Beide sind ausdruecklich fuer Maschinen gedacht und ueberleben ein Redesign,
das jeden CSS-Selektor bricht. Am 10.08.2026 gemessen: Medimax und ep.de
liefern Product/offers als JSON-LD (349,00 bzw. 699,00 EUR), freenet sogar
mitsamt sieben Varianten unter `isSimilarTo` - je mit eigener Farbe, eigenem
Speicher und eigenem Preis. ALDI TALK traegt kein JSON-LD, aber vollstaendige
Microdata. Ein Extraktor, zwei Lesarten, vier Anbieter.

DER LOCKPREIS-WAECHTER
----------------------
Dieselbe Messung hat die Falle gezeigt, vor der Teil C4 warnt: bei WinSIM,
o2 und Blau steht im voellig korrekten `offers.price` die Zahl **1** - die
Zuzahlung im Tarifbuendel. Wer sie als Geraetepreis nimmt, stellt ein iPhone
fuer 1 Euro in die Positionskarte, und die Grafik ist von da an Unsinn.
Deshalb faellt ein Preis unter `_LOCKPREIS_GRENZE` fuer die Preisart "ohne
Vertrag" durch. Das ist keine Plausibilitaetsschaetzung, sondern eine
Aussage ueber die Preisart: ein Elektronikhaendler verkauft kein Smartphone
fuer unter 30 Euro, ein Netzbetreiber verschenkt es im Buendel staendig.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Optional

from bs4 import BeautifulSoup

log = logging.getLogger(__name__)

_LDJSON_RE = re.compile(
    r'<script[^>]+type\s*=\s*["\']application/ld\+json["\'][^>]*>(.*?)</script>',
    re.IGNORECASE | re.DOTALL)

# Unterhalb dieser Grenze ist eine Zahl in der Spalte "Preis ohne Vertrag"
# keine Preisangabe, sondern ein Buendel-Lockpreis. Gemessen an echten
# Datensaetzen: WinSIM price=1, o2 price="1.00", Blau price="1.00".
_LOCKPREIS_GRENZE = 30.0

# Obergrenze gegen offensichtlichen Datenmuell (ein Cent-Preis mal 100, ein
# Bundle-Gesamtpreis). Faltbare liegen bei 2000-2500 Euro, also grosszuegig.
_PREIS_OBERGRENZE = 10000.0

_VERFUEGBARKEIT = {
    "instock": "lieferbar",
    "inStoreOnly": "lieferbar",
    "instoreonly": "lieferbar",
    "limitedavailability": "lieferbar",
    "onlineonly": "lieferbar",
    "preorder": "vorbestellbar",
    "presale": "vorbestellbar",
    "backorder": "nicht_lieferbar",
    "outofstock": "ausverkauft",
    "soldout": "ausverkauft",
    "discontinued": "ausverkauft",
}


def verfuegbarkeit_aus_schema(wert) -> str:
    """"http://schema.org/InStock" -> "lieferbar".

    "ausverkauft" ist NICHT "ausgelistet": ob ein Geraet aus dem Portfolio
    faellt, entscheidet die Zwei-Stufen-Logik des Stores ueber mehrere
    Laeufe, nie ein Verfuegbarkeitsetikett einer einzelnen Seite (Teil F).
    """
    if not wert:
        return "unbekannt"
    schluessel = str(wert).rsplit("/", 1)[-1].strip().lower()
    return _VERFUEGBARKEIT.get(schluessel, "unbekannt")


def lies_preis(roh) -> Optional[float]:
    """Preisangabe -> float, oder None.

    Der schema.org-Entwurf verlangt einen Punkt als Dezimaltrenner, aber
    deutsche Shops schreiben auch "1.099,00" und "1.099". Die Trennung:
      * beide Zeichen vorhanden -> das LETZTE ist der Dezimaltrenner
      * nur Komma -> Dezimaltrenner, wenn genau zwei Ziffern folgen
      * nur Punkt mit genau DREI Ziffern danach und sonst nichts ->
        Tausendertrenner ("1.099" ist 1099, nicht 1,099)
    """
    if roh is None:
        return None
    if isinstance(roh, (int, float)):
        wert = float(roh)
        return wert if 0 < wert <= _PREIS_OBERGRENZE else None
    text = str(roh).strip()
    text = re.sub(r"[^\d.,-]", "", text)
    if not text:
        return None
    hat_punkt, hat_komma = "." in text, "," in text
    if hat_punkt and hat_komma:
        if text.rfind(",") > text.rfind("."):
            text = text.replace(".", "").replace(",", ".")
        else:
            text = text.replace(",", "")
    elif hat_komma:
        nach = text.rsplit(",", 1)[1]
        text = text.replace(",", "." if len(nach) == 2 else "")
    elif hat_punkt:
        nach = text.rsplit(".", 1)[1]
        if text.count(".") == 1 and len(nach) == 3:
            text = text.replace(".", "")
    try:
        wert = float(text)
    except ValueError:
        return None
    return wert if 0 < wert <= _PREIS_OBERGRENZE else None


def ist_lockpreis(preis: Optional[float]) -> bool:
    return preis is not None and preis < _LOCKPREIS_GRENZE


# --------------------------------------------------------------------------
# Stufe 1: JSON-LD
# --------------------------------------------------------------------------

def _knoten(wurzel):
    """Alle dicts eines JSON-Baums, flach. Iterativ, damit ein tief
    verschachtelter @graph nicht die Rekursionsgrenze reisst - dieselbe
    Bauform wie `collect/lieferzeit._knoten`."""
    stapel = [wurzel]
    while stapel:
        knoten = stapel.pop()
        if isinstance(knoten, dict):
            yield knoten
            stapel.extend(knoten.values())
        elif isinstance(knoten, list):
            stapel.extend(knoten)


def _ist_produkt(knoten: dict) -> bool:
    typ = knoten.get("@type")
    if isinstance(typ, list):
        return any(str(t).lower() == "product" for t in typ)
    return str(typ or "").lower() == "product"


def _erstes_angebot(knoten: dict) -> dict:
    angebot = knoten.get("offers")
    if isinstance(angebot, list):
        angebot = angebot[0] if angebot else None
    return angebot if isinstance(angebot, dict) else {}


def _aus_produktknoten(knoten: dict) -> Optional[dict]:
    name = knoten.get("name")
    if not name or not isinstance(name, str):
        return None
    angebot = _erstes_angebot(knoten)
    preis = lies_preis(angebot.get("price"))
    if preis is None:
        preis = lies_preis((angebot.get("priceSpecification") or {}).get("price")
                           if isinstance(angebot.get("priceSpecification"), dict) else None)
    farbe = knoten.get("color")
    return {
        "titel": name.strip(),
        "preis": preis,
        "waehrung": str(angebot.get("priceCurrency") or "").upper(),
        "verfuegbarkeit": verfuegbarkeit_aus_schema(angebot.get("availability")),
        "sku": str(knoten.get("sku") or "").strip(),
        "ean": str(knoten.get("gtin13") or knoten.get("gtin") or "").strip(),
        "farbe": str(farbe).strip() if isinstance(farbe, str) else "",
        "url": str(angebot.get("url") or knoten.get("url") or "").strip(),
        "quelle": "ldjson",
    }


def produkte_aus_ldjson(html: str) -> list[dict]:
    """Alle Product-Knoten der Seite, inklusive Varianten.

    freenet haengt seine Speicher- und Farbvarianten unter `isSimilarTo` -
    sieben eigene Product-Knoten mit eigenem Preis. Weil `_knoten()` den
    ganzen Baum abgeht, kommen sie ohne Sonderbehandlung mit; das ist genau
    die Granularitaet, die eine SKU-Matrix braucht.
    """
    gefunden: list[dict] = []
    gesehen: set[tuple] = set()
    for block in _LDJSON_RE.findall(html or ""):
        try:
            daten = json.loads(block.strip())
        except (json.JSONDecodeError, ValueError):
            continue
        for knoten in _knoten(daten):
            if not _ist_produkt(knoten):
                continue
            satz = _aus_produktknoten(knoten)
            if not satz:
                continue
            schluessel = (satz["titel"].lower(), satz["preis"], satz["farbe"].lower())
            if schluessel in gesehen:
                continue
            gesehen.add(schluessel)
            gefunden.append(satz)
    return gefunden


# --------------------------------------------------------------------------
# Stufe 2: Microdata
# --------------------------------------------------------------------------

def _itemprop(wurzel, name: str) -> str:
    knoten = wurzel.find(attrs={"itemprop": name})
    if knoten is None:
        return ""
    for attribut in ("content", "href"):
        wert = knoten.get(attribut)
        if wert:
            return str(wert).strip()
    return knoten.get_text(" ", strip=True)


def produkte_aus_microdata(html: str) -> list[dict]:
    """schema.org als HTML-Attribute statt als JSON-Block (ALDI TALK)."""
    suppe = BeautifulSoup(html or "", "html.parser")
    gefunden: list[dict] = []
    for produkt in suppe.find_all(attrs={"itemtype": True}):
        typ = str(produkt.get("itemtype") or "").rsplit("/", 1)[-1].lower()
        if typ != "product":
            continue
        name = _itemprop(produkt, "name")
        if not name:
            continue
        angebot = produkt.find(attrs={"itemtype": re.compile(r"schema\.org/Offer$", re.I)})
        quelle = angebot if angebot is not None else produkt
        preis = lies_preis(_itemprop(quelle, "price"))
        gefunden.append({
            "titel": name,
            "preis": preis,
            "waehrung": (_itemprop(quelle, "priceCurrency") or "").upper(),
            "verfuegbarkeit": verfuegbarkeit_aus_schema(_itemprop(quelle, "availability")),
            "sku": _itemprop(produkt, "sku"),
            "ean": _itemprop(produkt, "gtin13"),
            "farbe": _itemprop(produkt, "color"),
            "url": "",
            "quelle": "microdata",
        })
    return gefunden


def produkte_aus_html(html: str) -> list[dict]:
    """Die Kaskade: JSON-LD zuerst, Microdata als zweite Lesart.

    Es wird NICHT auf Textextraktion zurueckgefallen. Bricht das
    strukturierte Datum weg, ist die Quelle tot und sagt das - ein stiller
    Rueckfall auf einen Regex ueber den sichtbaren Preis waere genau die
    Sorte Zahl, die aussieht wie gemessen und geraten ist.
    """
    treffer = produkte_aus_ldjson(html)
    if treffer:
        return treffer
    return produkte_aus_microdata(html)
