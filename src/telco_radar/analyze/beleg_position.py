"""Welche Preisposition zeigt das Belegbild eines Paares (Gerät, Anbieter)?

Das Bild trägt Gerät, Anbieter und Tag, keinen Tarif. Das Veröffentlichen legt je Paar
das Bild des Klick-Rohsatzes mit den niedrigsten Gesamtkosten ab
(``beleg_schluessel.ist_besser``); dieselbe Wahl über die Sätze des Bestands nennt die
Position, wenn sie sich daraus beweisen lässt. Reines Modul ohne Netz und ohne
Collect-Importe, damit die Seite es nutzen darf (Schicht ``report``). Die Gründe stehen
nur dort, wo die Liste kein Zeilenbild zeigt: sie sagen, warum keine Zeile eines hat,
nie, was ein Bild zeigt.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..tco_kosten import kosten_ueber
from ..tco_model import TCO_HORIZONT
from .geraete_pruefstatus import buendel_aus_satz


def gesamt_kosten(satz: dict[str, Any]) -> float | None:
    """Die Gesamtkosten eines Bestands- oder Rohsatzes über ``TCO_HORIZONT`` Monate."""
    return kosten_ueber(buendel_aus_satz(satz), TCO_HORIZONT).gesamt


GRUND_KEIN_KLICKSATZ = "keine Klick-Messung dieses Paares im Bestand"
GRUND_BESTAND_NEUER = "Bestand neuer als das Bild: der Bildsatz kann ersetzt sein"
GRUND_KEIN_SATZ_VOM_TAG = "kein Satz vom Tag des Bildes"
GRUND_KEINE_KOSTEN = "am Tag des Bildes hat die günstigste Position keine Gesamtkosten"
GRUND_GLEICHSTAND = "gleich teure Positionen: das Bild lässt sich keiner zuordnen"


@dataclass(frozen=True)
class Bildposition:
    """Welche Preisposition ein Paar-Bild zeigt: ihr Bestandssatz oder der Grund,
    warum keiner genannt wird. Genau eins von beiden ist gesetzt."""

    satz: dict[str, Any] | None
    grund: str = ""


def position_des_bildes(saetze: Iterable[dict[str, Any]], bildtag: str) -> Bildposition:
    """Die Position, die das Paar-Bild vom ``bildtag`` zeigt (fail-closed).

    ``belege_veroeffentlichen`` legt je (Gerät, Anbieter) das Bild des Rohsatzes mit den
    niedrigsten Gesamtkosten ab (``ist_besser``), der Dateiname trägt keinen Tarif.
    Dieselbe Wahl über die Klick-Sätze des Paares im Bestand nennt die Position, wenn
    sie sich nur aus dem Bestand beweisen lässt: Sätze mit ``beleg_id`` vom Tag des
    Bildes, nichts Neueres im Paar (ein späterer Abruf kann den Bildsatz ersetzt
    haben), ein einziger Spitzenreiter mit Gesamtkosten. Sonst ``satz=None`` mit
    benanntem Grund; geraten wird nie, auch nicht per Tie-Break nach ``beleg_id``.
    """
    klick = [s for s in saetze if s.get("beleg_id")]
    if not klick:
        return Bildposition(None, GRUND_KEIN_KLICKSATZ)
    if any(str(s.get("abgerufen_am") or "")[:10] > bildtag for s in klick):
        return Bildposition(None, GRUND_BESTAND_NEUER)
    vom_tag = [s for s in klick if str(s.get("abgerufen_am") or "")[:10] == bildtag]
    if not vom_tag:
        return Bildposition(None, GRUND_KEIN_SATZ_VOM_TAG)
    bewertet: list[tuple[float | None, str, dict[str, Any]]] = []
    for satz in vom_tag:
        try:
            gesamt = gesamt_kosten(satz)
        except (TypeError, ValueError, KeyError):
            gesamt = None
        bewertet.append((gesamt, str(satz["beleg_id"]), satz))
    bewertet.sort(key=lambda b: (b[0] is None, b[0] or 0.0, b[1]))
    erste = bewertet[0]
    if erste[0] is None:
        return Bildposition(None, GRUND_KEINE_KOSTEN)
    if len(bewertet) > 1 and bewertet[1][0] == erste[0]:
        return Bildposition(None, GRUND_GLEICHSTAND)
    return Bildposition(erste[2])


def lies_buendel(datei: Path) -> list[dict[str, Any]]:
    """Die Bündelsätze aus ``geraete_tco.json``; ohne Datei keine, kaputt: Fehler."""
    try:
        return json.loads(datei.read_text(encoding="utf-8"))["buendel"]
    except FileNotFoundError:
        return []
    except (OSError, ValueError, KeyError, TypeError) as fehler:
        raise ValueError(f"{datei.name}: {fehler}") from fehler
