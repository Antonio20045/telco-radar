"""Klick-Ergebnisse aus echten Fixtures, ohne Browser.

Die Werte jeder Kombination sind die zweite Lesung des Klick-Crawlers
(``klickantwort.lies_antwort``) über eine gespeicherte echte Antwort, mit der Karte aus
``config/klickkarten``; keine Zahl ist hier ausgedacht (Herkunft der Fixtures in
``tests/fixtures/geraete/_herkunft.json``):

- o2: ``o2_vertiefung_iphone17pro.json.gz`` (29.09.2026), ``script#pageValue`` und 14
  Konfigurationsantworten zum iPhone 17 Pro.
- Telekom: ``telekom_details_iphone17pro_512gb_20261007.json`` (07.10.2026),
  ``/v2/details`` zu iPhone 17 Pro 512 GB und MagentaMobil M.
- 1&1: ``einsundeins_produktseite_iphone_17_pro.html.gz`` (08.09.2026), die Globale
  ``hwdVariantsPrices`` der Produktseite.

Seitenadressen stehen wörtlich in ``config/klick_tageslauf.yaml``.
"""

from __future__ import annotations

import gzip
import json
import re
from pathlib import Path

from telco_radar.collect.geraete.klickantwort import Antwortlesung, lies_antwort
from telco_radar.collect.geraete.klickecho import variante_aus
from telco_radar.collect.geraete.klickergebnis import (
    FORMAT,
    laufstatus,
    seite_als_daten,
)
from telco_radar.collect.geraete.klickkarte import lade_klickkarte
from telco_radar.collect.geraete.klicklauf import ERFASST, Klicklauf, Kombiergebnis
from telco_radar.collect.geraete.klickziele import Seitenziel

WURZEL = Path(__file__).resolve().parents[1]
FIX = WURZEL / "tests" / "fixtures" / "geraete"
KARTEN = WURZEL / "config" / "klickkarten"
O2_KARTE = lade_klickkarte(KARTEN / "o2.yaml")
TELEKOM_KARTE = lade_klickkarte(KARTEN / "telekom.yaml")
EINSUNDEINS_KARTE = lade_klickkarte(KARTEN / "1und1.yaml")
O2_SEITE = Seitenziel(
    "apple-iphone-17-pro",
    256,
    "https://www.o2online.de/e-shop/apple/apple-iphone-17-pro-256gb-silber-details"
    "?ohne-tarif=nein&zielgruppe=privatkunden&ratenzahlung=36"
    "&vertragsart=ratenzahlung&tarif=o2-mobile-unlimited-m-plus",
    None,
    "iPhone 17 Pro",
)
TELEKOM_SEITE = Seitenziel(
    "apple-iphone-17-pro",
    256,
    "https://www.telekom.de/shop/geraet/apple/apple-iphone-17-pro/tiefblau-256-gb"
    "?tariffId=MF_17791&categoryId=smartphones&forwardTradeInApplied=false",
    None,
    "iPhone 17 Pro",
)
EINSUNDEINS_SEITE = Seitenziel(
    "apple-iphone-17-pro",
    256,
    "https://mobile.1und1.de/iphone-17-pro",
    None,
    "iPhone 17 Pro",
)
TELEKOM_TARIF = "MagentaMobil M"
TELEKOM_SPEICHER = "512 GB"
_PREISE = re.compile(r"hwdVariantsPrices\s*=\s*\{(.*?)\};", re.S)
_EINTRAG = re.compile(r"'([^']+)'\s*:\s*\[\s*(\d+)\s*,?\s*\]")
_LAUFZEIT = re.compile(r"window\.currentHardwareOfferDuration\s*=\s*'(\d+)'")


def o2_lesungen() -> list[Antwortlesung]:
    """Startzustand aus ``pageValue`` und je Konfigurationsantwort eine Lesung."""
    konfiguration, seite = O2_KARTE.lesequellen
    datei = FIX / "o2_vertiefung_iphone17pro.json.gz"
    antworten = json.loads(gzip.decompress(datei.read_bytes()))["antworten"]
    lesungen = []
    for url, roh in antworten.items():
        if roh.startswith("<html"):
            treffer = re.search(
                r'<script id="pageValue"[^>]*>(.*?)</script>', roh, re.S
            )
            assert treffer is not None
            lesungen.append(lies_antwort(json.loads(treffer[1]), seite))
        elif "/rest/configuration/" in url:
            lesungen.append(lies_antwort(json.loads(roh), konfiguration, url))
    return lesungen


def o2_lesung(speicher: str, tarif_anfang: str, laufzeit: int) -> Antwortlesung:
    """Die eine o2-Lesung zu Speicher, Tarifanfang und Laufzeit."""
    treffer = [
        lesung
        for lesung in o2_lesungen()
        if lesung.variante["speicher"] == speicher
        and lesung.variante["laufzeit"] == laufzeit
        and " ".join(str(lesung.variante["tarif"]).split()).startswith(tarif_anfang)
    ]
    assert len(treffer) == 1, (speicher, tarif_anfang, laufzeit, len(treffer))
    return treffer[0]


def telekom_lesung(laufzeit: str, anzahlung: str) -> Antwortlesung:
    """``/v2/details`` je Laufzeit und Anzahlungsstufe der Seite."""
    details = json.loads(
        (FIX / "telekom_details_iphone17pro_512gb_20261007.json").read_text("utf-8")
    )
    platz = {
        "speicher": TELEKOM_SPEICHER,
        "tarif": TELEKOM_TARIF,
        "laufzeit": laufzeit,
        "anzahlung_gewaehlt": anzahlung,
    }
    return lies_antwort(details, TELEKOM_KARTE.lesequellen[0], None, platz)


def einsundeins_lesung(speicher: str = "256") -> Antwortlesung:
    """Bündelbetrag aus ``hwdVariantsPrices`` der gespeicherten Produktseite."""
    datei = FIX / "einsundeins_produktseite_iphone_17_pro.html.gz"
    html = gzip.decompress(datei.read_bytes()).decode("utf-8")
    preise = _PREISE.search(html)
    laufzeit = _LAUFZEIT.search(html)
    assert preise is not None and laufzeit is not None
    globale = {
        "hwdVariantsPrices": {k: [int(v)] for k, v in _EINTRAG.findall(preise[1])},
        "currentHardwareOfferDuration": laufzeit[1],
    }
    platz = {
        "speicher": speicher,
        "tarif": "tariff-anf-s-mvl",
        "laufzeit": "36",
        "farbe": "COSMIC_ORANGE",
    }
    return lies_antwort(globale, EINSUNDEINS_KARTE.antwort, None, platz)


def erfasst(
    lesung: Antwortlesung,
    speicher: object = None,
    tarif: object = None,
    laufzeit: object = None,
) -> Kombiergebnis:
    """Eine erfasste Kombination mit den Werten der Lesung; Variante wie gelesen."""
    v = lesung.variante
    speicher = v.get("speicher") if speicher is None else speicher
    tarif = v.get("tarif") if tarif is None else tarif
    laufzeit = v.get("laufzeit") if laufzeit is None else laufzeit
    auswahl = tuple(None if x is None else str(x) for x in (speicher, tarif, laufzeit))
    return Kombiergebnis(
        variante_aus(speicher, tarif, laufzeit),
        ERFASST,
        werte=lesung.werte,
        auswahl=auswahl,
        buendel=lesung.buendel if lesung.buendel.buendelbetrag is not None else None,
        antwortwerte=lesung.werte,
    )


def lauf(seite: Seitenziel, ergebnisse: list[Kombiergebnis], **felder) -> Klicklauf:
    """Ein Klicklauf über ``seite`` mit ``ergebnisse``; Status gelesen, wenn nicht
    anders angegeben."""
    return Klicklauf(
        anbieter="", adresse=seite.adresse, ergebnisse=list(ergebnisse), **felder
    )


def ergebnisdatei(
    name: str,
    schluessel: str,
    seiten: list[tuple[Seitenziel, Klicklauf]],
    datum: str,
    vertragsform: str = "tarif_plus_ratenkauf",
) -> dict:
    """Eine Ergebnisdatei wie aus dem Tageslauf, Laufstatus aus den Seiten."""
    daten = [seite_als_daten(ziel, klicklauf) for ziel, klicklauf in seiten]
    status, grund = laufstatus(daten)
    return {
        "format": FORMAT,
        "anbieter": schluessel,
        "name": name,
        "datum": datum,
        "karte": f"{schluessel}.yaml",
        "vertragsform": vertragsform,
        "laufstatus": status,
        "grund": grund,
        "seiten": daten,
    }
