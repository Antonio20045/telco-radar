"""Beschriftung der veröffentlichten Folgebilder: was das Klick-Ergebnis über die
Bildfolge einer Position weiß.

Die Release-Anhänge tragen nur Gerät, Anbieter, Tag, Schritt und die Kennung der
Position im Namen (``beleg_regeln.folge_dateiname``). Text je Schritt und die Gründe
fehlender Schritte stehen im Klick-Ergebnis (``collect.geraete.klickergebnis``,
``data/state/klick``) unter ``beleg``: ``bildfolge`` (Schritt, Text) und
``bildfolge_fehlt`` (``"<schritt>: <Grund>"``). ``lies_folgen`` ordnet sie über die
Kennung (die ersten Zeichen der ``beleg_id``) zu. Kennt das Ergebnis die Position nicht
mehr (es ist rotiert), gibt es keine Beschriftung; ``beleg_manifest`` nennt den Schritt
dann ohne Text und ohne erfundenen Grund. Eine mehrdeutige Kennung gilt als unbekannt.
Stdlib, kein Netz.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any

from .beleg_regeln import KENNUNG_LAENGE


@dataclass(frozen=True)
class Folgeninfo:
    """Beschriftung einer Position: Text und Lückengrund je Schritt."""

    texte: Mapping[str, str] = field(default_factory=dict)
    fehlt: Mapping[str, str] = field(default_factory=dict)


def _gruende(zeilen: Iterable[Any]) -> dict[str, str]:
    """``"tarif: Grund"`` zu ``{"tarif": "Grund"}``; ohne Doppelpunkt kein Eintrag."""
    ergebnis: dict[str, str] = {}
    for zeile in zeilen:
        schritt, trenner, grund = str(zeile).partition(": ")
        if trenner and schritt.strip() and grund.strip():
            ergebnis[schritt.strip()] = grund.strip()
    return ergebnis


def lies_folgen(ergebnisse: Iterable[Mapping[str, Any]]) -> dict[str, Folgeninfo]:
    """``Kennung -> Folgeninfo`` aus den Klick-Ergebnissen (``klick_vertrag``)."""
    gefunden: dict[str, Folgeninfo] = {}
    mehrdeutig: set[str] = set()
    ids: dict[str, str] = {}
    for daten in ergebnisse:
        for seite in daten.get("seiten") or []:
            for kombination in seite.get("kombinationen") or []:
                beleg = kombination.get("beleg")
                if not isinstance(beleg, Mapping) or "bildfolge" not in beleg:
                    continue
                beleg_id = str(beleg.get("beleg_id") or "")
                kennung = beleg_id[:KENNUNG_LAENGE]
                if len(kennung) < KENNUNG_LAENGE:
                    continue
                if ids.setdefault(kennung, beleg_id) != beleg_id:
                    mehrdeutig.add(kennung)
                texte = {
                    str(b.get("schritt")): str(b.get("text") or "").strip()
                    for b in beleg["bildfolge"] or []
                    if isinstance(b, Mapping) and b.get("schritt")
                }
                gefunden[kennung] = Folgeninfo(
                    texte, _gruende(beleg.get("bildfolge_fehlt") or [])
                )
    return {k: v for k, v in gefunden.items() if k not in mehrdeutig}
