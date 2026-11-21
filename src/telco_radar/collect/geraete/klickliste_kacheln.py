"""Produktseiten aus den Kacheln der zuletzt gelesenen Übersichten (Telekom, 1&1).

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
liefert ihre Seiten aus dem Vorrat: den Kacheln, die sie zuletzt ganz gelesen hatte
(``fuehre_vorrat`` in der Ablage, ``kachelvorrat`` mit Lesedatum), höchstens
``VORRAT_HOECHSTALTER_TAGE`` alt. Jede nicht ganz gelesene Übersicht steht mit Grund in
``Kachelseiten.luecken``; sie ist nicht „leer“ und verschwindet nie still. Ohne jede
Kachel (erster Lauf nach der Umstellung, Vorrat zu alt) gelten die Produktseiten, die
die Datei selbst besucht hat (``_seiten_des_laufs``), ebenfalls als benannte Lücke.

``verteile`` legt die Seiten reihum auf die Einträge einer Gruppe (je ein Matrix-Job);
sortiert nach Gerät und Tarif, damit Seiten eines Geräts nicht im selben Job
hintereinander stehen. Rein, ohne Netz.

1&1 (seit 20.11.2026): die Geräteübersicht ``/smartphones`` liefert je Kachel den
Produktlink ``https://mobile.1und1.de/<gerät>`` ohne Tarif (``klickraster.ART_LISTE``);
die Produktseite liest jeden Tarif selbst (Tarifauswahl im Bestellweg), also eine
Seite je Produkt.
"""

from __future__ import annotations

import copy
import json
import logging
import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import TypeVar
from urllib.parse import parse_qs, urlsplit

from ...geraete_model import Katalog, erkenne_geraet, zustand_aus_titel
from ...klick_vertrag import ORDNER
from .klickergebnis import GELESENE_SEITEN

log = logging.getLogger(__name__)
T = TypeVar("T")

PRODUKTPFAD = "/shop/geraet/"
EINSUNDEINS_HOST = "mobile.1und1.de"
_EINSUNDEINS_PFAD = re.compile(r"/[a-z0-9]+(?:-[a-z0-9]+)*")
TARIF_PARAMETER = "tariffId"
ZUSTAND_UNBEKANNT = "unbekannt"
VORRAT = "kachelvorrat"
VORRAT_HOECHSTALTER_TAGE = 7
"""So viele Tage darf der Vorrat einer nicht gelesenen Übersicht älter sein als die
Ergebnisdatei; danach ist der Tarif eine benannte Lücke."""
_SPEICHER_AM_ENDE = re.compile(r"\s+\d{1,4}\s*(?:GB|TB)\s*$", re.IGNORECASE)


@dataclass
class Kachelseiten:
    """Die abgeleiteten Seiten (Rohform für ``klickziele``), Stand und Lücken."""

    seiten: list[dict] = field(default_factory=list)
    datum: str | None = None
    luecken: list[str] = field(default_factory=list)
    rueckfall: bool = False
    """Die Seiten sind die besuchten Seiten der Läufe, nicht Kacheln: die Liste kann
    so nicht wachsen, ``klickliste_auto`` ergänzt fehlende Modelle."""


def lies_kachelseiten(
    root: Path,
    schluessel: str,
    katalog: Katalog,
    geschwister: Sequence[str] = (),
) -> Kachelseiten:
    """Die Seiten aus ``data/state/klick/<schluessel>.json``; fehlt die Datei oder ist
    sie unlesbar, keine Seite und die Lücke mit Grund (nie eine Ausnahme: der Plan
    der übrigen Anbieter hängt nicht an dieser Datei). ``geschwister`` sind die
    übrigen Einträge derselben Quelle; ihre Dateien zählen nur im Rückfall ohne
    Kachel (``_seiten_des_laufs``)."""
    pfad = root / ORDNER / f"{schluessel}.json"
    try:
        daten = json.loads(pfad.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return Kachelseiten(
            luecken=[f"{pfad.name}: keine Ergebnisdatei der Übersichten"]
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as fehler:
        return Kachelseiten(luecken=[f"{pfad.name}: nicht lesbar ({fehler})"])
    if not isinstance(daten, dict):
        return Kachelseiten(luecken=[f"{pfad.name}: keine Zuordnung"])
    weitere = [_lies(root / ORDNER / f"{g}.json") for g in geschwister]
    return seiten_aus_kacheln(daten, katalog, [w for w in weitere if w is not None])


def _lies(pfad: Path) -> dict | None:
    """Eine Geschwisterdatei; fehlt sie oder ist sie unlesbar, zählt sie nicht."""
    try:
        daten = json.loads(pfad.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as fehler:
        log.info("Seiten des Laufs: %s nicht lesbar (%s)", pfad.name, fehler)
        return None
    return daten if isinstance(daten, dict) else None


def seiten_aus_kacheln(
    daten: dict, katalog: Katalog, weitere: Sequence[dict] = ()
) -> Kachelseiten:
    """Je Produkt und Tarif eine Seite aus den Kacheln jeder Übersicht: der ganz
    gelesenen, sonst ihres Vorrats (``fuehre_vorrat``), wenn er höchstens
    ``VORRAT_HOECHSTALTER_TAGE`` älter als die Datei ist; jede nicht ganz gelesene
    Übersicht ist eine benannte Lücke. Ohne jede Kachel die besuchten Seiten dieser
    Datei und der ``weitere`` (Geschwister derselben Quelle)."""
    ergebnis = Kachelseiten(datum=daten.get("datum"))
    je_seite: dict[tuple[str, str], dict] = {}
    for uebersicht in daten.get("uebersichten") or []:
        kacheln = _kacheln(uebersicht) if _gelesen(uebersicht) else []
        if not _ganz(uebersicht):
            kacheln += _vorrat(uebersicht, daten.get("datum"), ergebnis.luecken)
        for satz in kacheln:
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
    if not ergebnis.seiten:
        ergebnis.seiten = _seiten_des_laufs(
            [daten, *weitere], katalog, ergebnis.luecken
        )
        ergebnis.rueckfall = bool(ergebnis.seiten)
    return ergebnis


def _seiten_des_laufs(
    dateien: list[dict], katalog: Katalog, luecken: list[str]
) -> list[dict]:
    """Rückfall ohne jede Kachel (erster Lauf nach der Umstellung, Übersicht und
    Vorrat fehlen): die Produktseiten, die die Dateien dieser Quelle besucht haben,
    Adresse und Gerät wörtlich, jede Adresse einmal; die Lücke nennt es. Alle
    Einträge der Quelle zählen: nur die erste Datei hieße, die Liste halbiert sich mit
    jedem Lauf (1&1, 21.11.2026: 42 Seiten am 20.11., 21 für den 22.11.)."""
    daten = dateien[0]
    seiten: list[dict] = []
    gesehen: set[str] = set()
    for seite in (s for d in dateien for s in d.get("seiten") or []):
        adresse, geraet = str(seite.get("adresse") or ""), seite.get("geraet")
        if _produkt_und_tarif(adresse) is None or katalog.nach_id(str(geraet)) is None:
            continue
        if adresse in gesehen:
            continue
        gesehen.add(adresse)
        gb = seite.get("speicher_gb")
        seiten.append({"geraet": geraet, "speicher_gb": gb, "url": adresse})
    if seiten:
        tag = _tag(daten.get("datum"))
        luecken.append(f"keine Kachel, {len(seiten)} Seiten des Laufs vom {tag}")
    return seiten


def fuehre_vorrat(neu: dict, alt: dict | None) -> dict:
    """``neu`` mit ``kachelvorrat`` an jeder nicht ganz gelesenen Übersicht: die
    Kacheln derselben Übersicht in ``alt`` (der abgelegten Datei davor), wenn sie dort
    ganz gelesen war, sonst deren Vorrat, beides mit Lesedatum. Eine ganz gelesene
    Übersicht braucht keinen; sie ist selbst der nächste Vorrat."""
    vorher = {u.get("adresse"): u for u in (alt or {}).get("uebersichten") or []}
    ergebnis = copy.deepcopy(neu)
    for uebersicht in ergebnis.get("uebersichten") or []:
        frueher = vorher.get(uebersicht.get("adresse"))
        if _ganz(uebersicht) or frueher is None:
            continue
        if _ganz(frueher):
            vorrat = {
                "datum": (alt or {}).get("datum"),
                "tarif": _tarifname(frueher),
                "kacheln": [_knapp(k) for k in _kacheln(frueher)],
            }
        else:
            vorrat = frueher.get(VORRAT)
        if isinstance(vorrat, dict):
            uebersicht[VORRAT] = vorrat
    return ergebnis


def _gelesen(uebersicht: dict) -> bool:
    return uebersicht.get("status") in GELESENE_SEITEN


def _ganz(uebersicht: dict) -> bool:
    """Gelesen, vollständig und mit mindestens einer Kachel."""
    return (
        _gelesen(uebersicht)
        and uebersicht.get("vollstaendig") is not False
        and bool(_kacheln(uebersicht))
    )


def _vorrat(uebersicht: dict, datum: object, luecken: list[str]) -> list[dict]:
    """Die Kacheln des Vorrats, wenn er jung genug ist; die Lücke immer mit Grund."""
    grund = uebersicht.get("grund") or uebersicht.get("unvollstaendig")
    roh = uebersicht.get(VORRAT)
    vorrat: dict = roh if isinstance(roh, dict) else {}
    name = vorrat.get("tarif") or _tarifname(uebersicht) or uebersicht.get("adresse")
    kopf = f"Übersicht {name} am {_tag(datum)} nicht ganz gelesen ({grund or 'leer'})"
    alter = _tage(vorrat.get("datum"), datum)
    if alter is None or not 0 <= alter <= VORRAT_HOECHSTALTER_TAGE:
        jung = f"keine Kacheln jünger als {VORRAT_HOECHSTALTER_TAGE} Tage"
        luecken.append(f"{kopf}, {jung}")
        return []
    luecken.append(f"{kopf}, Seiten aus den Kacheln vom {_tag(vorrat['datum'])}")
    return [k for k in vorrat.get("kacheln") or [] if isinstance(k, dict)]


def _tarifname(uebersicht: dict) -> str | None:
    namen = [s.get("tarif_name") for s in uebersicht.get("saetze") or []]
    return next((n for n in namen if isinstance(n, str) and n), None)


def _knapp(kachel: dict) -> dict:
    return {f: kachel.get(f) for f in ("titel", "speicher_gb", "url")}


def _tage(von: object, bis: object) -> int | None:
    try:
        return (date.fromisoformat(str(bis)) - date.fromisoformat(str(von))).days
    except ValueError:
        return None


def _tag(datum: object) -> str:
    try:
        return date.fromisoformat(str(datum)).strftime("%d.%m.%Y")
    except ValueError:
        return str(datum)


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
    schluessel = _produkt_und_tarif(adresse)
    if schluessel is None:
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
        "_produkt": schluessel[0],
        "_tarif": schluessel[1],
    }


def _produkt_und_tarif(adresse: str) -> tuple[str, str] | None:
    """Produkt und Tarif einer Kacheladresse: Telekom ``/shop/geraet/<marke>/<gerät>/…
    ?tariffId=…``, 1&1 ``https://mobile.1und1.de/<gerät>`` (Tarif leer); sonst
    ``None``."""
    teile = urlsplit(adresse)
    if teile.path.startswith(PRODUKTPFAD):
        tarif = (parse_qs(teile.query).get(TARIF_PARAMETER) or [""])[0].strip()
        produkt = teile.path.removeprefix(PRODUKTPFAD).split("/")
        if not tarif or len(produkt) < 2:
            return None
        return "/".join(produkt[:2]), tarif
    einzeln = _EINSUNDEINS_PFAD.fullmatch(teile.path)
    if teile.netloc == EINSUNDEINS_HOST and einzeln and not teile.query:
        return teile.path.strip("/"), ""
    return None


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
