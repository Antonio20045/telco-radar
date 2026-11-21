"""Leser der Soll-Zählung: je Anbieter die eigene Übersicht als Liste von Funden.

Ein Fund ist ein Gerät, das der Anbieter in seiner eigenen Liste führt (Titel und
Adresse), noch ohne Katalogzuordnung. Diese Leser sind bewusst eigener Code und
importieren keinen Parser und keinen Adapter des Sammlers
(``tests/test_geraete_soll_leser.py`` prüft das an den Importen): eine Zählung, die
mit dem Code des Sammlers liest, fände dessen Fehler nie.

Was die Listen hergeben, ist am 21.11.2026 je einmal abgerufen und geprüft
(Fixtures unter ``tests/fixtures/geraete_soll/``):

* congstar ``/sitemap/devices.xml``: eine Adresse je Produkt, ohne Speicher.
* 1&1 ``/smartphones``: eine Kachel je Gerät (``form.hardware-box``) ohne Speicher.
* Vodafone: die Geräteliste der Schnittstelle der Übersichtsseite (``hardwareType``).
* o2: der Gerätekatalog der Shop-Schnittstelle; ein Eintrag „… mit <Zubehör>“ ist ein
  Paket (``nur_paket``), sein Preis gilt für beides.

Ein Leser wirft ``LeserFehler``, wenn die Antwort nicht die erwartete Form hat; eine
leere Liste ist kein Ergebnis, sondern ein Fehler (Clean Code 5).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from html import unescape
from urllib.parse import urlsplit

NICHT_SMARTPHONE = frozenset(
    {
        "airpods",
        "anio",
        "buds",
        "gigacube",
        "headphone",
        "hyperbox",
        "hypermobile",
        "imoo",
        "ipad",
        "kids",
        "kidswatch",
        "kinder",
        "meta",
        "navee",
        "onetouch",
        "router",
        "scooter",
        "sinus",
        "smartwatch",
        "speedphone",
        "speedport",
        "tab",
        "tablet",
        "tv",
        "watch",
        "xplora",
        "zyxel",
    }
)
"""Wortteile einer Adresse, die kein Smartphone meinen (Uhr, Tablet, Router, TV)."""

NICHT_SMARTPHONE_ANFANG = ("airpods", "buds", "ipad", "kids", "tab", "watch")
"""Wortanfänge mit Modellnummer dahinter („buds4“, „watch9“, „tablet“)."""

KATALOG_ANFRAGE = re.compile(r"(\d)(plus)\b|(pro)(plus)\b")
"""Adressen schreiben „s26plus“ und „proplus“ zusammen; der Katalog trennt."""

SCHREIBWEISE = {"iphone": "iPhone", "ipad": "iPad", "5g": "5G"}
"""Wörter, die ``lesbar`` nicht einfach groß schreibt."""

_LOC = re.compile(r"<loc>\s*([^<\s]+)\s*</loc>")
_KACHEL = re.compile(r'<form class="hardware-box[^"]*"(.*?)</form>', re.S)
_TITEL = re.compile(r'data-title="([^"]*)"')
_LINK = re.compile(r'href="(https://mobile\.1und1\.de/[^"?#]+)"')
_PAKET = re.compile(r"\smit\s", re.I)


class LeserFehler(ValueError):
    """Die Antwort des Anbieters hat nicht die Form, die der Leser kennt."""


@dataclass(frozen=True)
class Fund:
    """Ein Gerät aus der Liste des Anbieters: Titel, Adresse, nur als Paket."""

    titel: str
    url: str
    nur_paket: bool = False


def _orte(text: str) -> list[str]:
    orte = [unescape(o) for o in _LOC.findall(text or "")]
    if not orte:
        raise LeserFehler("Sitemap ohne <loc>-Eintrag")
    return orte


def _woerter(slug: str) -> list[str]:
    return [w for w in re.split(r"[-_/]+", slug.lower()) if w]


def ist_smartphone(slug: str) -> bool:
    """Kein Wortteil der Adresse meint Uhr, Tablet, Router oder Fernseher."""
    return not any(
        w in NICHT_SMARTPHONE or w.startswith(NICHT_SMARTPHONE_ANFANG)
        for w in _woerter(slug)
    )


def titel_aus_slug(slug: str) -> str:
    """„samsung-galaxy-s26plus“ -> „samsung galaxy s26 plus“ (Suchtext, Katalog)."""
    text = " ".join(_woerter(slug))
    return KATALOG_ANFRAGE.sub(
        lambda m: f"{m.group(1) or m.group(3)} {m.group(2) or m.group(4)}", text
    )


def lesbar(titel: str) -> str:
    """Ein Titel aus einer Adresse in Kleinschrift („apple iphone 13 refurbished
    basic“) wird lesbar („Apple iPhone 13 Refurbished Basic“); ein Titel mit
    Großbuchstaben bleibt, wie die Quelle ihn schreibt."""
    if titel != titel.lower():
        return titel
    return " ".join(SCHREIBWEISE.get(w, w.capitalize()) for w in titel.split())


def _ohne_duplikat(funde: list[Fund]) -> list[Fund]:
    if not funde:
        raise LeserFehler("Liste ohne einen Eintrag")
    gesehen: dict[str, Fund] = {}
    for fund in funde:
        gesehen.setdefault(fund.url, fund)
    return list(gesehen.values())


def congstar_sitemap(text: str) -> list[Fund]:
    """``/geraete/<marke>/<produkt>/`` je Smartphone der Geräte-Sitemap."""
    funde = []
    for ort in _orte(text):
        teile = [t for t in urlsplit(ort).path.split("/") if t]
        if len(teile) != 3 or teile[0] != "geraete" or not ist_smartphone(teile[2]):
            continue
        funde.append(Fund(titel_aus_slug(teile[2]), ort))
    return _ohne_duplikat(funde)


def einsundeins_kacheln(text: str) -> list[Fund]:
    """Je Kachel der Übersicht ``/smartphones`` Titel und Produktlink."""
    funde = []
    for kachel in _KACHEL.findall(text or ""):
        titel = _TITEL.search(kachel)
        produkt = _LINK.search(kachel)
        if titel is None or produkt is None:
            raise LeserFehler("Kachel ohne Titel oder Produktlink")
        funde.append(Fund(unescape(titel.group(1)).strip(), produkt.group(1)))
    return _ohne_duplikat(funde)


def _json(text: str) -> object:
    try:
        return json.loads(text or "")
    except ValueError as fehler:
        raise LeserFehler(f"kein JSON: {fehler}") from fehler


def vodafone_liste(text: str) -> list[Fund]:
    """``data.devices[]`` mit ``hardwareType`` „Smartphone“; Adresse: Hubseite."""
    daten = _json(text)
    inhalt = daten.get("data") if isinstance(daten, dict) else None
    geraete = inhalt.get("devices") if isinstance(inhalt, dict) else None
    if not isinstance(inhalt, dict) or not isinstance(geraete, list):
        raise LeserFehler("Geräteliste ohne data.devices[]")
    zahl = inhalt.get("numberOfDevices")
    if zahl != len(geraete):
        raise LeserFehler(f"Liste nennt {zahl} Geräte, enthält {len(geraete)}")
    funde = []
    for g in geraete:
        if g.get("hardwareType") != "Smartphone":
            continue
        hub = (g.get("hubpage") or {}).get("href") or ""
        funde.append(
            Fund(str(g.get("modelName") or ""), f"https://www.vodafone.de{hub}")
        )
    return _ohne_duplikat(funde)


def o2_katalog(text: str) -> list[Fund]:
    """``hardware[]`` des Katalogs; ein Folgeverweis (``loadNextRestLink``) heißt,
    dass die Antwort nicht alles enthält - dann ist die Liste nicht zählbar."""
    daten = _json(text)
    if not isinstance(daten, dict) or not isinstance(daten.get("hardware"), list):
        raise LeserFehler("Katalog ohne hardware[]")
    if daten.get("loadNextRestLink") is not None:
        raise LeserFehler("Katalog hat eine Folgeseite, die nicht gelesen ist")
    funde = []
    for h in daten["hardware"]:
        titel = str(h.get("description") or "")
        adresse = f"https://www.o2online.de/e-shop/{h.get('urlName') or ''}"
        paket = bool(_PAKET.search(titel))
        funde.append(Fund(_PAKET.split(titel)[0].strip(), adresse, nur_paket=paket))
    return _ohne_duplikat(funde)
