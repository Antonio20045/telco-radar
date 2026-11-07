"""Pflichtmodelle zuerst in die Buendel-Vertiefung.

`vertiefe_buendel` (siehe `o2.py`) teilt ihr Zeitbudget ueber ALLE Geraete
eines Katalogs, in Katalogreihenfolge. Ohne eigene Reihenfolge verbraucht
sich das Budget an Geraeten ohne Pflichtzelle (Befund 07.11.2026, o2:
einige Pflichtmodelle blieben bei einer Speichergroesse stehen, waehrend
andere Geraete alle Speicher und Laufzeiten bekamen). Die Reihenfolge kommt
aus `config/geraete_abdeckung.yaml` - derselben Liste, gegen die der
Waechter schon misst, keine neue Sonderliste.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml

_ABDECKUNG_PFAD = (
    Path(__file__).resolve().parents[4] / "config" / "geraete_abdeckung.yaml"
)


@lru_cache(maxsize=1)
def pflicht_modelle() -> frozenset[str]:
    """`pflicht_modelle` aus der Abdeckung-Config. Eine fehlende Datei ist
    eine leere Liste, kein Fehler - dieselbe Konvention wie bei den anderen
    Loadern dieses Pakets."""
    try:
        daten = yaml.safe_load(_ABDECKUNG_PFAD.read_text(encoding="utf-8")) or {}
    except OSError:
        return frozenset()
    return frozenset(daten.get("pflicht_modelle") or [])


def nach_prioritaet(gemappt: list[dict]) -> list[dict]:
    """Pflichtmodelle stabil nach vorn - innerhalb jeder Gruppe bleibt die
    Katalogreihenfolge."""
    prioritaet = pflicht_modelle()
    if not prioritaet:
        return gemappt
    return sorted(gemappt, key=lambda satz: satz.get("device_id") not in prioritaet)
