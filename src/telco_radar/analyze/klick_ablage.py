"""Ablage der Klick-Ergebnisse im Repo und Lesestand der Rotation (Datenkonzept §8).

Der Workflow ``klick.yml`` lädt die Ergebnisdateien seiner Matrix-Jobs herunter;
``lege_ab`` schreibt jede nach ``data/state/klick/<schluessel>.json``
(``klickergebnis.ORDNER``) und führt den Lesestand ``STAND_DATEI`` fort: für jede Datei
mit Laufstatus ``gelesen`` das Datum jeder gelesenen Seite (Rotation des Tageslaufs)
und jeder erfassten Variante (Ersetzung über die Rotation im Gerätelauf). Eine
gestörte, leere oder ungelesene Datei wird ebenso abgelegt, damit der Gerätelauf ihren
Zustand sieht, und lässt den Lesestand unberührt. Fehlt das Ergebnis eines Anbieters,
bleibt seine alte Datei liegen und verliert nach ``FRISCHEGRENZE_TAGE`` jede Wirkung.
Varianten jenseits der Frischegrenze fallen aus dem Lesestand; Seiten bleiben, denn
ihr Datum ordnet die Rotation.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from ..collect.geraete.klickergebnis import (
    FRISCHEGRENZE_TAGE,
    GELESENE_SEITEN,
    STAND_DATEI,
    STAND_FORMAT,
    lies_stand,
    schreibe,
)
from ..collect.geraete.klicklauf import LAUF_GELESEN
from ..collect.geraete.klickrohsatz import ausbeute
from ..geraete_model import Katalog
from .klick_zusammenfuehrung import alter_tage, klickschluessel, schluesseltext

SCHLUESSEL = re.compile(r"^[a-z0-9][a-z0-9_-]*$")
"""Anbieterschlüssel wie in ``config/klick_tageslauf.yaml``; zugleich der Dateiname."""


@dataclass
class Ablage:
    """Abgelegte Anbieter, abgelehnte Dateien mit Grund und der neue Lesestand."""

    abgelegt: list[str] = field(default_factory=list)
    abgelehnt: list[str] = field(default_factory=list)
    stand: dict = field(default_factory=dict)


def lege_ab(ergebnisse: list[dict], ziel: Path, katalog: Katalog, heute: str) -> Ablage:
    """Schreibt die Ergebnisse nach ``ziel`` und den Lesestand daneben."""
    stand = lies_stand(ziel / STAND_DATEI)
    ablage = Ablage(stand=stand)
    for daten in ergebnisse:
        schluessel = str(daten.get("anbieter", ""))
        if not SCHLUESSEL.match(schluessel):
            ablage.abgelehnt.append(f"Anbieterschlüssel {schluessel!r} ungültig")
            continue
        schreibe(ziel / f"{schluessel}.json", daten)
        ablage.abgelegt.append(schluessel)
        if daten.get("laufstatus") == LAUF_GELESEN:
            _merke(stand, daten, katalog)
    _kuerze(stand, heute)
    schreibe(ziel / STAND_DATEI, stand)
    return ablage


def _merke(stand: dict, daten: dict, katalog: Katalog) -> None:
    """Lesedatum der gelesenen Seiten und der erfassten Varianten einer Datei."""
    datum = str(daten.get("datum"))
    name = str(daten.get("name"))
    seiten = stand["seiten"].setdefault(name, {})
    for seite in daten.get("seiten") or []:
        if seite.get("status") in GELESENE_SEITEN:
            seiten[str(seite.get("adresse"))] = datum
    varianten = stand["varianten"].setdefault(name, {})
    for satz in ausbeute(daten, katalog).rohsaetze:
        varianten[schluesseltext(klickschluessel(satz))] = datum


def _kuerze(stand: dict, heute: str) -> None:
    """Varianten jenseits der Frischegrenze wirken nicht mehr und fallen weg."""
    stand["format"] = STAND_FORMAT
    for anbieter, varianten in stand["varianten"].items():
        stand["varianten"][anbieter] = {
            k: d for k, d in varianten.items() if _frisch(alter_tage(d, heute))
        }


def _frisch(alter: int | None) -> bool:
    return alter is not None and alter < FRISCHEGRENZE_TAGE
