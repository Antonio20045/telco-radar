"""Ablage der Klick-Ergebnisse im Repo und Lesestand der Rotation (Datenkonzept §8).

Der Workflow ``klick.yml`` lädt die Ergebnisdateien seiner Matrix-Jobs herunter;
``lege_ab`` schreibt jede nach ``data/state/klick/<schluessel>.json``
(``klickergebnis.ORDNER``), auch eine gestörte, leere oder ungelesene, damit der
Gerätelauf ihren Zustand sieht. Fehlt das Ergebnis eines Anbieters, bleibt seine alte
Datei liegen; der Gerätelauf nimmt nur eine Datei von heute als Messung.

Den Lesestand ``STAND_DATEI`` führt die Ablage für jede Datei fort, gleich welcher
Laufstatus: jede ganz gelesene Seite (``ROTATION_GELESEN``) bekommt das Datum der Datei.
Auch ein Lauf, der nichts erfasst hat, schiebt so die Rotation weiter; eine an der
Zeitgrenze abgeschnittene Seite bleibt vorn. Welche Klick-Messung Vorrang vor dem
Adapter hat, steht nicht hier, sondern im Bestand (``klick_zusammenfuehrung``).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from ..collect.geraete.klickergebnis import (
    ROTATION_GELESEN,
    STAND_DATEI,
    STAND_FORMAT,
    lies_stand,
    schreibe,
)

SCHLUESSEL = re.compile(r"^[a-z0-9][a-z0-9_-]*$")
"""Anbieterschlüssel wie in ``config/klick_tageslauf.yaml``; zugleich der Dateiname."""


@dataclass
class Ablage:
    """Abgelegte Anbieter, abgelehnte Dateien mit Grund und der neue Lesestand."""

    abgelegt: list[str] = field(default_factory=list)
    abgelehnt: list[str] = field(default_factory=list)
    stand: dict = field(default_factory=dict)


def lege_ab(ergebnisse: list[dict], ziel: Path) -> Ablage:
    """Schreibt die Ergebnisse nach ``ziel`` und den Lesestand daneben."""
    stand = lies_stand(ziel / STAND_DATEI)
    stand["format"] = STAND_FORMAT
    ablage = Ablage(stand=stand)
    for daten in ergebnisse:
        schluessel = str(daten.get("anbieter", ""))
        if not SCHLUESSEL.match(schluessel):
            ablage.abgelehnt.append(f"Anbieterschlüssel {schluessel!r} ungültig")
            continue
        schreibe(ziel / f"{schluessel}.json", daten)
        ablage.abgelegt.append(schluessel)
        for seite in daten.get("seiten") or []:
            if seite.get("status") in ROTATION_GELESEN:
                seiten = stand["seiten"].setdefault(str(daten.get("name")), {})
                seiten[str(seite.get("adresse"))] = str(daten.get("datum"))
    schreibe(ziel / STAND_DATEI, stand)
    return ablage
