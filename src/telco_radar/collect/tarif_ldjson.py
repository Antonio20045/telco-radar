"""Tarife aus den strukturierten Daten einer Shop-Seite (schema.org).

WARUM ES DIESEN ZWEITEN WEG UEBERHAUPT GIBT
-------------------------------------------
Der Tarif-Sammler liest Pflichtdokumente nach § 1 TK-TransparenzV. Das ist
die belastbarste Quelle dieses Marktes - und die traegste. Das Blatt nennt
den Vermarktungsstand, die Shop-Seite den Preis von heute. Wer nur Blaetter
liest, sieht eine Preisaktion erst, wenn sie ein neues Blatt bekommt.

Dieses Modul liest deshalb den zweiten Preis: den, den der Anbieter selbst
in seine Seite schreibt, als `application/ld+json` nach schema.org. Das ist
kein Ersatz, sondern eine zweite Messung, und sie wird als solche
gekennzeichnet (`Tarif.preistyp = live_shop`). Weichen beide voneinander
ab, ist genau DAS die Auskunft - nicht ein Fehler, der wegzurechnen waere.

DIE MESSUNG, DIE DIESES MODUL TRAEGT (1&1, 04.09.2026)
------------------------------------------------------
`https://www.1und1.de/handytarife` (HTTP 200, 452 KB, statisches HTML)
liefert einen `@graph` mit SIEBEN Product-Knoten:

    {"@type": "Product", "brand": {"name": "1&1"},
     "name": "1&1 All-Net-Flat S", "description": "1&1 All-Net-Flat S 10 GB",
     "offers": {"priceCurrency": "EUR", "price": "14.99"}}

Dieselben sieben Knoten mit denselben Betraegen stehen auf
`/handytarife-ohne-handy`, der SIM-only-Seite. Das ist der Grund, warum
diese Zahl als Tarifpreis OHNE Geraet gelesen werden darf: der Anbieter
stellt sie selbst auf seine SIM-only-Seite. (Und es ist der Grund, warum
die zweite Seite NICHT zusaetzlich abgerufen wird - derselbe Graph unter
zwei Adressen ergaebe dieselben sieben Tarife zweimal, und der Sammler
haengte an den zweiten Satz einen Hash-Zusatz. Ein Abruf, der nur
Dubletten erzeugt, kostet nur Zeit.)

WAS HIER NICHT PASSIERT
-----------------------
* **Keine Preisphase wird erfunden.** Die Seite nennt keine ("ab dem 7.
  Monat" kommt im gemessenen HTML kein einziges Mal vor), also traegt der
  Satz keine. Ob 14,99 EUR ein Aktions- oder ein Dauerpreis ist, sagt die
  Quelle nicht - und dieses Modul sagt es deshalb auch nicht.
* **Keine Laufzeit wird abgeleitet.** Steht sie nicht im Knoten, bleibt sie
  `None`.
* **Kein `allnet_flat: true` aus dem Namen.** "All-Net-Flat S" ist eine
  Produktbezeichnung, keine Leistungszusage in einem Datenfeld. Aus einem
  Marketingnamen ein Leistungsmerkmal zu lesen waere geraten, und der
  ganze Sinn von `Tarif.setze()` ist, dass nichts ohne Fundstelle
  hereinkommt.

DER BELEG IST DER JSON-AUSSCHNITT SELBST
----------------------------------------
`Tarif.pruefe_belege()` verlangt, dass jede Fundstelle woertlich im
Rohtext steht. Rohtext ist hier der Product-Knoten, so wie er in der Seite
steht; die Fundstelle ist der Ausschnitt daraus, aus dem der Wert kommt.
Damit gilt dieselbe Zusage wie beim PDF: wer die Zahl nachschlagen will,
bekommt die Zeile, in der sie stand.

DIE ABGRENZUNG GEGEN GERAETE-KNOTEN
-----------------------------------
`mobile.1und1.de/iphone-17-pro` traegt AUCH einen Product-Knoten mit
`offers.price` - dort sind es 44,99 EUR, und das ist der Monatspreis des
BUENDELS aus Geraet und Tarif, nicht der Tarifpreis. Genau diese
Verwechslung ist der Grund, aus dem 1&1 im Geraetezweig ein Jahr lang
`aktiv: false` stand.

Unterschieden werden die zwei an der MARKE: ein Tarif traegt die Marke des
Anbieters ("1&1"), ein Geraet die des Herstellers ("Apple"). Das ist kein
Kniff, sondern die Sache selbst - 1&1 verkauft seinen eigenen Tarif und
Apples Telefon. Ein Knoten mit fremder Marke wird uebersprungen und
protokolliert.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Optional

from bs4 import BeautifulSoup

from ..tarif_model import HOCH, PREISTYP_LIVE_SHOP, Tarif, zahl
from .tarif_pdf import dokument_hash

log = logging.getLogger(__name__)

# "1&1 All-Net-Flat M 50 GB" -> 50.0. Der Wert steht in der `description`,
# und nur dort - der `name` traegt ihn nicht. Absichtlich ohne "MB": ein
# Tarif dieses Marktes wird in GB beworben, und eine MB-Zahl in einer
# Produktbeschreibung ist eher eine Drosselgeschwindigkeit als ein Volumen.
_VOLUMEN_RE = re.compile(r"(\d+(?:[.,]\d+)?)\s*GB\b", re.I)


def _marke(text: str) -> str:
    """Markenname auf das reduziert, was sich vergleichen laesst.

    "1&1" steht im Graph als `1&1`, in der Konfiguration ebenso, im
    HTML-Quelltext aber als `1&amp;1`. Nach dieser Funktion ist alles
    davon `11` - dieselbe Vereinfachung, die `tarif_crawler.tarif_id` fuer
    den Anbieterteil der ID benutzt.
    """
    return re.sub(r"[^a-z0-9]+", "", (text or "").lower())


def _knoten(daten) -> list[dict]:
    """Alle Product-Knoten eines ld+json-Blocks, egal wie er verpackt ist.

    schema.org kennt drei Verpackungen, und 1&1 benutzt die dritte: ein
    einzelnes Objekt, eine Liste von Objekten, oder ein `@graph`. Wer nur
    eine davon liest, findet bei der naechsten Umstellung nichts mehr -
    ohne dass etwas wirft.
    """
    if isinstance(daten, list):
        out: list[dict] = []
        for teil in daten:
            out.extend(_knoten(teil))
        return out
    if not isinstance(daten, dict):
        return []
    if daten.get("@graph"):
        return _knoten(daten["@graph"])
    typ = daten.get("@type")
    typen = typ if isinstance(typ, list) else [typ]
    return [daten] if "Product" in typen else []


def ld_json_bloecke(html: str) -> list[dict]:
    """Die geparsten ld+json-Bloecke einer Seite.

    Ein unlesbarer Block ist kein Grund, die Seite wegzuwerfen: Shops
    liefern regelmaessig einen kaputten Block neben drei heilen (bei 1&1
    stehen FAQPage, WebSite und Organization neben dem Tarifgraphen).
    """
    out = []
    suppe = BeautifulSoup(html or "", "html.parser")
    for tag in suppe.find_all("script", attrs={"type": "application/ld+json"}):
        roh = tag.string or tag.get_text() or ""
        try:
            out.append(json.loads(roh))
        except (json.JSONDecodeError, ValueError):
            log.debug("ld+json-Block unlesbar - uebersprungen")
    return out


def _ausschnitt(knoten: dict, *pfad) -> str:
    """Der Beleg: der Knoten, eingedampft auf den Weg zu EINEM Wert.

    Nicht der ganze Knoten (dann stuende in jeder Fundstelle dasselbe) und
    nicht nur der Wert (dann stuende dort "14.99" ohne Feldnamen, und eine
    Fundstelle ohne ihren Bezeichner belegt nichts).
    """
    o = knoten
    for teil in pfad[:-1]:
        o = (o or {}).get(teil) or {}
    letzte = pfad[-1]
    if letzte not in (o or {}):
        return ""
    return json.dumps({letzte: o[letzte]}, ensure_ascii=False)[1:-1].strip()


def tarif_aus_knoten(knoten: dict, *, anbieter: str, seiten_url: str,
                     abgerufen_am: str) -> Optional[tuple[Tarif, str]]:
    """Ein Product-Knoten wird ein Tarif - oder nichts.

    Nichts wird er, wenn er einem anderen Hersteller gehoert, keinen Namen
    traegt, keinen Betrag nennt oder in fremder Waehrung rechnet. Ein Preis
    in fremder Waehrung ist kein Vergleichswert; dieselbe Regel gilt im
    Geraetezweig (`collect/geraete/__init__._uebernimm`).
    """
    name = str(knoten.get("name") or "").strip()
    if not name:
        return None

    marke = knoten.get("brand")
    marke_name = (marke.get("name") if isinstance(marke, dict)
                  else marke) or ""
    if _marke(marke_name) != _marke(anbieter):
        log.info("ld+json-Knoten %r traegt die Marke %r und nicht %r - "
                 "das ist ein Fremdprodukt, kein Tarif dieses Anbieters",
                 name, str(marke_name), anbieter)
        return None

    angebot = knoten.get("offers")
    if isinstance(angebot, list):
        angebot = angebot[0] if angebot else None
    if not isinstance(angebot, dict):
        return None
    waehrung = str(angebot.get("priceCurrency") or "").upper()
    if waehrung and waehrung != "EUR":
        log.info("ld+json-Knoten %r rechnet in %s - kein Vergleichswert",
                 name, waehrung)
        return None
    betrag = zahl(angebot.get("price"))
    if betrag is None:
        return None

    # Der Rohtext IST der Knoten. Damit steht jede Fundstelle unten
    # woertlich darin, und `pruefe_belege()` prueft eine echte Zusage.
    rohtext = json.dumps(knoten, ensure_ascii=False)
    tarif = Tarif(anbieter=anbieter, abgerufen_am=abgerufen_am,
                  rohtext=rohtext, preistyp=PREISTYP_LIVE_SHOP,
                  # Die Seite, auf der die Zahl stand. `offers.url` waere
                  # verlockend, ist aber der Bestellweg und nicht die
                  # Fundstelle - 1&1 setzt dort dieselbe Adresse fuer alle
                  # sieben Tarife.
                  dokument_url=seiten_url)
    tarif.setze("name", name, _ausschnitt(knoten, "name"), HOCH)
    tarif.setze("grundgebuehr", betrag,
                _ausschnitt(knoten, "offers", "price"), HOCH)

    beschreibung = str(knoten.get("description") or "")
    treffer = _VOLUMEN_RE.search(beschreibung)
    if treffer:
        tarif.setze("datenvolumen_gb", zahl(treffer.group(1)),
                    _ausschnitt(knoten, "description"), HOCH)

    # Der Fingerabdruck haengt am KNOTEN, nicht an der Seite. Sieben
    # Tarife auf einer Seite haetten sonst denselben Hash: eine Aenderung
    # an einem einzigen liesse alle sieben als geaendert gelten, und der
    # Diff liefe fuer sechs Tarife, die sich nicht bewegt haben.
    hash_ = dokument_hash(rohtext)
    tarif.dokument_hash = hash_
    return tarif, hash_


def tarife_aus_html(html: str, *, anbieter: str, seiten_url: str,
                    abgerufen_am: str) -> list[tuple[Tarif, str]]:
    """Alle Tarife, die die Seite in ihren strukturierten Daten nennt."""
    out: list[tuple[Tarif, str]] = []
    gesehen: set[str] = set()
    for block in ld_json_bloecke(html):
        for knoten in _knoten(block):
            ergebnis = tarif_aus_knoten(knoten, anbieter=anbieter,
                                        seiten_url=seiten_url,
                                        abgerufen_am=abgerufen_am)
            if ergebnis is None:
                continue
            tarif, hash_ = ergebnis
            if hash_ in gesehen:
                # Derselbe Knoten zweimal in derselben Seite. Kommt vor,
                # wenn ein Shop denselben Graphen fuer Kopf- und Fussteil
                # ausliefert - zwei Saetze waeren dann eine Dublette und
                # kein zweiter Tarif.
                continue
            gesehen.add(hash_)
            out.append((tarif, hash_))
    return out
