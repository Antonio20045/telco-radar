"""1&1: Geräteraster je Tarif im Klick-Tageslauf (Pitch 2, Schnitt 4).

Lesart der ``uebersichten`` von 1&1 (``klickuebersicht.LESARTEN``): eine Adresse mit
``/details-`` ist eine Tarifdetail-Seite (``klickanschluss``), eine mit
``/smartphones-`` ein Geräteraster. Jede Kachel ``form.hardware-box`` des Rasters wird
ein Satz mit ``art`` ``ART_RASTER``: Titel aus ``data-title``, Produktlink
``a.hardware-box__heading``, Monatspreis „€/Monat*“ als ``buendel_monatlich``,
``data-hardware-months`` als Laufzeit und der Tarif aus „Inkl. …“ ohne Klammerzusatz.
Ohne Kachel, mit unvollständiger Kachel oder mit Kacheln verschiedener Tarife ist das
Raster gestört (``GeraeteAbrufFehler``).

Das Raster nennt keine Speichergröße; ``raster_roh`` misst sie: Es gilt die Größe,
deren heute gelesener Produktseiten-Satz (``PRODUKTSEITE_SLUG``, gleiche Laufzeit)
genau dem Preis der Kachel im Raster ``PRODUKTSEITE_TARIF`` entspricht. Keine oder
mehrere passende Größen, kein Produktseiten-Satz oder kein gelesenes Raster dieses
Tarifs: ``speicher_gb`` bleibt ``None`` (Lücke ``speicher_unbekannt``). Beleg der
Paarung: Tarifübersicht 29.09.2026 („Tarifdetails 1&1 All-Net-Flat S“ →
``chosenTariff=tariff-anf-s-mvl``), Klick-Erkundung 09.10.2026 (die Produktseite zeigt
immer All-Net-Flat S). Sätze dieses Rasters werden kein Rohsatz: die Produktseite
nennt denselben Tarif genauer. Der Anschluss kommt von der heute gelesenen
Tarifdetail-Seite mit demselben Tarifnamen, sonst bleibt er ``None``.

Eine Kachel, die das Gerät mit Zubehör bündelt („und Samsung Galaxy Buds 4“ in
``…-bundle-description``), trägt ``zubehoer``: ihr Preis gilt nicht für das Gerät
allein, sie misst keinen Speicher und wird kein Rohsatz (``klickrohsatz``, Lücke
``buendel_mit_zubehoer``; Regel: Bündel aus Gerät plus Zubehör werden verworfen).

Das Raster nennt die Schlusszahlung von „24+12“ nicht. Sie hängt bei 1&1 nur an der
Gerätevariante (``hwdVariantsOneOffPaymentFees.product-<Farbe>-<Speicher>`` ohne
Tarif, Karte ``config/klickkarten/1und1.yaml``): ein Rastersatz mit gemessenem Speicher
übernimmt sie vom Produktseiten-Satz, der den Speicher bestimmt hat, mit
``herleitung`` ``HERLEITUNG_SCHLUSSZAHLUNG``. Ohne diesen Satz bleibt sie ``None``.
"""

from __future__ import annotations

import html
import re
from urllib.parse import urlsplit

from ...geraete_model import Katalog, erkenne_geraet, normalisiere
from .basis import GeraeteAbrufFehler
from .einsundeins import tarifname_bereinigt
from .klickanschluss import ART_ANSCHLUSS, anschluss_saetze
from .klickergebnis import GELESENE_SEITEN
from .klickkarte import EIN_VERTRAG

ART_RASTER = "raster"
PRODUKTSEITE_SLUG = "tariff-anf-s-mvl"
PRODUKTSEITE_TARIF = "1&1 All-Net-Flat S"
CENT = 0.005
HERLEITUNG_SCHLUSSZAHLUNG = "schlusszahlung_aus_grundtarif"
BEREIT_JS = (
    "() => document.readyState === 'complete' || ("
    "location.pathname.startsWith('/smartphones-') && "
    "document.readyState === 'interactive' && "
    "document.querySelector('form.hardware-box') !== null)"
)
"""Ein Raster trägt die Kacheln im Hauptdokument; eine Tarifdetail-Seite lädt ganz."""

_KACHEL = re.compile(r'<form class="hardware-box\b.*?</form>', re.S)
_TITEL = re.compile(r'data-title="([^"]*)"')
_LINK = re.compile(r'<a href="([^"]+)"[^>]*class="hardware-box__heading"')
_EURO = re.compile(r'class="price__euro"[^>]*>\s*(\d+)\s*<')
_CENT = re.compile(r'class="price__decimals\b[^"]*"[^>]*>\s*([0-9]{2}|[–-])\s*<')
_EINHEIT = re.compile(r'class="price__unit"[^>]*>\s*€/Monat\*\s*<')
_MONATE = re.compile(r'data-hardware-months="(\d+)"')
_TARIF = re.compile(r"Inkl\.\s*([^<]+)")
_ZUBEHOER = re.compile(
    r'-bundle-description"[^>]*>\s*(?:<br\s*/?>)?\s*und\s+([^<]*\S)\s*<'
)


def einsundeins_saetze(text: str, adresse: str) -> list[dict]:
    """Sätze einer 1&1-Übersicht nach ihrer Seitenart (siehe Modulkopf)."""
    pfad = urlsplit(adresse).path
    if pfad.startswith("/details-"):
        return anschluss_saetze(text, adresse)
    if pfad.startswith("/smartphones-"):
        return raster_saetze(text)
    raise GeraeteAbrufFehler(f"1&1-Übersicht ohne bekannte Seitenart: {pfad}")


def raster_saetze(text: str) -> list[dict]:
    """Je Kachel ein Satz; gestört ohne Kachel oder mit mehreren Tarifen."""
    saetze = [_kachel(kachel) for kachel in _KACHEL.findall(text)]
    if not saetze:
        raise GeraeteAbrufFehler("1&1-Geräteraster ohne hardware-box-Kachel")
    tarife = sorted({s["tarif_name"] for s in saetze})
    if len(tarife) != 1:
        raise GeraeteAbrufFehler(f"1&1-Geräteraster mit Tarifen {', '.join(tarife)}")
    return saetze


def _kachel(kachel: str) -> dict:
    titel, link = _TITEL.search(kachel), _LINK.search(kachel)
    euro, cent = _EURO.search(kachel), _CENT.search(kachel)
    monate, tarif = _MONATE.search(kachel), _TARIF.search(kachel)
    if not (titel and link and euro and cent and monate and tarif):
        raise GeraeteAbrufFehler("1&1-Geräteraster mit unvollständiger Kachel")
    if not _EINHEIT.search(kachel):
        raise GeraeteAbrufFehler(f"1&1-Kachel {titel[1]!r} ohne „€/Monat*“")
    rest = 0 if cent[1] in "–-" else int(cent[1])
    return {
        "art": ART_RASTER,
        "titel": " ".join(html.unescape(titel[1]).split()),
        "url": html.unescape(link[1]),
        "tarif_name": tarifname_bereinigt(tarif[1]),
        "laufzeit_monate": int(monate[1]),
        "buendel_monatlich": (int(euro[1]) * 100 + rest) / 100,
        "zubehoer": _zubehoer(kachel),
    }


def _zubehoer(kachel: str) -> str | None:
    """Das Zubehör, das die Kachel mit dem Gerät bündelt („und Galaxy Buds 4“)."""
    treffer = _ZUBEHOER.search(kachel)
    return None if treffer is None else " ".join(html.unescape(treffer[1]).split())


def raster_roh(daten: dict, produktsaetze: list[dict], katalog: Katalog) -> list[dict]:
    """Die Rastersätze für ``klickrohsatz.uebersicht_rohsatz`` mit gemessenem
    Speicher und gelesenem Anschluss (siehe Modulkopf); nur bei ``ein_vertrag``."""
    if daten.get("vertragsform") != EIN_VERTRAG:
        return []
    gelesen = [
        roh
        for u in daten.get("uebersichten") or []
        if u.get("status") in GELESENE_SEITEN
        for roh in u.get("saetze") or []
    ]
    raster = [r for r in gelesen if r.get("art") == ART_RASTER]
    ohne_zubehoer = [r for r in raster if not r.get("zubehoer")]
    anschluss = {
        _tarif(r.get("tarif_name")): r.get("anschlusspreis")
        for r in gelesen
        if r.get("art") == ART_ANSCHLUSS and r.get("tarif_name")
    }
    basis = _tarif(PRODUKTSEITE_TARIF)
    speicher = _speicher(
        [r for r in ohne_zubehoer if _tarif(r["tarif_name"]) == basis],
        produktsaetze,
        katalog,
    )
    saetze = []
    for roh in raster:
        if _tarif(roh["tarif_name"]) == basis:
            continue
        geraet = _geraet(roh, katalog)
        gb = _gemessen(speicher, geraet)
        satz = {
            **roh,
            "speicher_gb": gb,
            "anschlusspreis": anschluss.get(_tarif(roh["tarif_name"])),
        }
        zahlung = _schlusszahlung(produktsaetze, geraet, gb, roh["laufzeit_monate"])
        if zahlung is not None:
            satz.update(geraet_zuzahlung=zahlung, herleitung=HERLEITUNG_SCHLUSSZAHLUNG)
        saetze.append(satz)
    return saetze


def _schlusszahlung(
    produktsaetze: list[dict], geraet: str | None, gb: int | None, monate: object
) -> float | None:
    """Die Zuzahlung des Produktseiten-Satzes (Grundtarif), der den Speicher bestimmt;
    ohne genau einen solchen Satz mit Zuzahlung ``None``."""
    slug = _tarif(PRODUKTSEITE_SLUG)
    werte = {
        satz["geraet_zuzahlung"]
        for satz in produktsaetze
        if geraet is not None
        and gb is not None
        and satz.get("device_id") == geraet
        and satz.get("speicher_gb") == gb
        and _tarif(satz.get("tarif_name")) == slug
        and str(satz.get("laufzeit_monate")) == str(monate)
        and satz.get("geraet_zuzahlung") is not None
    }
    return werte.pop() if len(werte) == 1 else None


def _gemessen(speicher: dict[str, int], geraet: str | None) -> int | None:
    """Die gemessene Größe eines erkannten Geräts; unbekanntes Gerät ``None``."""
    return None if geraet is None else speicher.get(geraet)


def _speicher(
    basis: list[dict], produktsaetze: list[dict], katalog: Katalog
) -> dict[str, int]:
    """Je Gerät die eine Größe, deren Produktseiten-Satz den Rasterpreis trifft."""
    preise: dict[str, set[tuple[float, object]]] = {}
    for roh in basis:
        geraet = _geraet(roh, katalog)
        if geraet:
            eintrag = (roh["buendel_monatlich"], roh["laufzeit_monate"])
            preise.setdefault(geraet, set()).add(eintrag)
    slug = _tarif(PRODUKTSEITE_SLUG)
    treffer: dict[str, set[int]] = {}
    for satz in produktsaetze:
        geraet = str(satz.get("device_id"))
        if _tarif(satz.get("tarif_name")) != slug or len(preise.get(geraet, ())) != 1:
            continue
        ((preis, monate),) = preise[geraet]
        betrag = satz.get("buendel_monatlich")
        if (
            str(satz.get("laufzeit_monate")) == str(monate)
            and betrag is not None
            and abs(betrag - preis) < CENT
        ):
            treffer.setdefault(geraet, set()).add(satz["speicher_gb"])
    return {geraet: gb.pop() for geraet, gb in treffer.items() if len(gb) == 1}


def _geraet(roh: dict, katalog: Katalog) -> str | None:
    geraet = erkenne_geraet(str(roh.get("titel") or ""), katalog)
    return None if geraet is None else geraet.device_id


def _tarif(name: object) -> str:
    return normalisiere(tarifname_bereinigt(str(name or "")))
