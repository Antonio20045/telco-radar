"""Produktseiten aus den Kacheln der zuletzt gelesenen Übersichten (Telekom).

Die Telekom-Produktseiten standen von Hand in ``config/klick_tageslauf.yaml``, je
Gerät mit einer festen Farbe in der Adresse. Ein Gerät, das die Telekom nur noch in
anderer Farbe oder als „Erneuert“ führt, leitete dann auf die Markenübersicht um und
galt als ausgelistet (iPhone 15, 20.11.2026: Kachel ``apple-iphone-15-erneuert/
zufallsfarbe-128-gb``, feste Adresse ``apple-iphone-15/blau-128-gb``); ein neues Gerät
(Xiaomi 18 Pro, iPhone 14) bekam nie eine Seite, weil ``klickliste_auto`` nur drei
Familien mit acht Plätzen ableitet.

Hier kommt jede Seite aus einer Kachel der Übersichten, die der Klick-Lauf ohnehin
liest (``klickuebersicht``, ``telekom_liste``), auch aus einer Kachel ohne lesbaren
Preis: je Produkt und Tarif genau eine Seite,
Adresse wörtlich der Produktlink der Kachel (nie zusammengesetzt, CLAUDE.md Regel 4),
also mit ihrer Farbe und ihrer ``tariffId``. Quelle ist die Ergebnisdatei des Eintrags,
der die Übersichten liest (``data/state/klick/<schluessel>.json``), also die
Übersichten des letzten abgelegten Laufs: die Matrix-Jobs eines Laufs laufen
gleichzeitig, die Übersichten des eigenen Laufs liegen erst danach vor. Ein neues Gerät
bekommt seine Seite darum am Tag nach seiner ersten Kachel.

Das Gerät kommt über den Titel aus dem Katalog (``erkenne_geraet``), der Zustand aus
dem Titel (``zustand_aus_titel``: „Erneuert“ ist ``refurbished``); ein unbekanntes Gerät
oder ein unbestimmbarer Zustand bekommt keine Seite (Protokoll). Den Modellnamen für
den Kanarienwert schreibt die Kachel (``_modellname``). Eine nicht gelesene Übersicht
liefert keine Seite und steht mit Grund in ``Kachelseiten.luecken``; sie ist nicht
„leer“.

``verteile`` legt die Seiten reihum auf die Einträge einer Gruppe (je ein Matrix-Job);
sortiert nach Gerät und Tarif, damit Seiten eines Geräts nicht im selben Job
hintereinander stehen. Rein, ohne Netz.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import TypeVar
from urllib.parse import parse_qs, urlsplit

from ...geraete_model import Katalog, erkenne_geraet, zustand_aus_titel
from ...klick_vertrag import ORDNER
from .klickergebnis import GELESENE_SEITEN

log = logging.getLogger(__name__)
T = TypeVar("T")

PRODUKTPFAD = "/shop/geraet/"
TARIF_PARAMETER = "tariffId"
ZUSTAND_UNBEKANNT = "unbekannt"
_SPEICHER_AM_ENDE = re.compile(r"\s+\d{1,4}\s*(?:GB|TB)\s*$", re.IGNORECASE)


class KachelquelleFehler(ValueError):
    """Die Ergebnisdatei der Übersichten ist da, aber nicht lesbar."""


@dataclass
class Kachelseiten:
    """Die abgeleiteten Seiten (Rohform für ``klickziele``), Stand und Lücken."""

    seiten: list[dict] = field(default_factory=list)
    datum: str | None = None
    luecken: list[str] = field(default_factory=list)


def lies_kachelseiten(root: Path, schluessel: str, katalog: Katalog) -> Kachelseiten:
    """Die Seiten aus ``data/state/klick/<schluessel>.json``; fehlt die Datei, keine
    Seite mit Lücke. Ist sie unlesbar, wirft ``KachelquelleFehler``."""
    pfad = root / ORDNER / f"{schluessel}.json"
    try:
        daten = json.loads(pfad.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return Kachelseiten(luecken=[f"{pfad}: keine Ergebnisdatei der Übersichten"])
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as fehler:
        raise KachelquelleFehler(f"{pfad}: nicht lesbar ({fehler})") from fehler
    if not isinstance(daten, dict):
        raise KachelquelleFehler(f"{pfad}: keine Zuordnung")
    return seiten_aus_kacheln(daten, katalog)


def seiten_aus_kacheln(daten: dict, katalog: Katalog) -> Kachelseiten:
    """Je Produkt und Tarif eine Seite aus den Sätzen der gelesenen Übersichten."""
    ergebnis = Kachelseiten(datum=daten.get("datum"))
    je_seite: dict[tuple[str, str], dict] = {}
    for uebersicht in daten.get("uebersichten") or []:
        if uebersicht.get("status") not in GELESENE_SEITEN:
            grund = uebersicht.get("grund") or uebersicht.get("status")
            ergebnis.luecken.append(f"{uebersicht.get('adresse')}: {grund}")
            continue
        for satz in _kacheln(uebersicht):
            seite = _seite(satz, katalog)
            if seite is None:
                continue
            schluessel = (seite.pop("_produkt"), seite.pop("_tarif"))
            bisher = je_seite.get(schluessel)
            if bisher is None or _kleiner(seite, bisher):
                je_seite[schluessel] = seite
    ergebnis.seiten = [
        je_seite[s] for s in sorted(je_seite, key=lambda s: (je_seite[s]["geraet"], s))
    ]
    return ergebnis


def verteile(seiten: list[T], anzahl: int) -> list[list[T]]:
    """Die Seiten reihum auf ``anzahl`` Einträge, in der Reihenfolge der Liste."""
    return [seiten[stelle::anzahl] for stelle in range(anzahl)]


def _kacheln(uebersicht: dict) -> list[dict]:
    """Jede Kachel mit Produktlink (``telekom_liste``: ``seiten[].liste.kacheln``),
    dazu die Sätze mit Preis; Dateien vor dem 20.11.2026 kennen nur die Sätze."""
    kacheln = [
        k
        for seite in uebersicht.get("seiten") or []
        for k in (seite.get("liste") or {}).get("kacheln") or []
    ]
    return kacheln + list(uebersicht.get("saetze") or [])


def _seite(satz: dict, katalog: Katalog) -> dict | None:
    titel = " ".join(str(satz.get("titel") or "").split())
    adresse = str(satz.get("url") or "")
    teile = urlsplit(adresse)
    if not teile.path.startswith(PRODUKTPFAD):
        return None
    tarif = (parse_qs(teile.query).get(TARIF_PARAMETER) or [""])[0].strip()
    produkt = teile.path.removeprefix(PRODUKTPFAD).split("/")
    if not tarif or len(produkt) < 2:
        return None
    geraet = erkenne_geraet(titel, katalog)
    zustand = zustand_aus_titel(titel)
    if geraet is None or zustand == ZUSTAND_UNBEKANNT:
        log.info("Kachelseiten: %r ohne Katalogeintrag oder Zustand", titel)
        return None
    gb = satz.get("speicher_gb")
    name = _SPEICHER_AM_ENDE.sub("", titel)
    return {
        "geraet": geraet.device_id,
        "speicher_gb": gb if gb in (geraet.speicher or []) else None,
        "url": adresse,
        "modell": _modellname(name, geraet.hersteller, geraet.modell),
        "zustand": zustand,
        "_produkt": "/".join(produkt[:2]),
        "_tarif": tarif,
    }


def _modellname(name: str, hersteller: str, modell: str) -> str:
    """Der Name für den Kanarienwert in der Schreibweise der Kachel, ohne den
    Hersteller davor: Telekom schreibt ihn in Kachel und Energielabel verschieden
    („Motorola edge 70“, Klick-Lauf 11.10.2026), das Modell gleich. Steht der
    Katalogname in der Kachel, gilt seine Fundstelle, sonst der ganze Titel. Der
    Hersteller fällt nur weg, wenn der Rest Buchstaben und Ziffern trägt („Fairphone 6“
    bleibt, „6“ allein träfe jede Seite)."""
    stelle = name.casefold().find(modell.casefold()) if modell else -1
    treffer = name[stelle : stelle + len(modell)] if stelle >= 0 else name
    erstes, _, rest = treffer.partition(" ")
    eindeutig = any(z.isalpha() for z in rest) and any(z.isdigit() for z in rest)
    if erstes.casefold() == hersteller.casefold() and eindeutig:
        return rest
    return treffer


def _kleiner(neu: dict, bisher: dict) -> bool:
    """Die kleinere bekannte Speicherstufe gewinnt; die Seite liest ohnehin alle."""

    def rang(seite: dict) -> tuple[bool, int]:
        gb = seite["speicher_gb"]
        return (gb is None, gb if gb is not None else 0)

    return rang(neu) < rang(bisher)
