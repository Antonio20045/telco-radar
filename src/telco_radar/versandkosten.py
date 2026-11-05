"""Der Pflichtversand je Anbieter: eine einmalige Zahlung in der Kernzahl.

Die Beträge stehen in `config/versandkosten.yaml` mit Quelle, Datum und Screenshot der
Messung am Original; im Code gibt es keinen Anbieter-Sonderfall. `tco_kosten` und
`tco_model` rufen `versand_fuer` und rechnen für jeden Anbieter dieselbe Regel: der
Betrag zählt einmal zu den Kosten über H Monate. Ein Anbieter ohne belegten Betrag
(fehlt in der Datei oder `betrag: null`) zählt 0 €, und `hinweis_unbelegt` benennt die
Lücke auf der Seite. Geraten wird nie.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

POSTEN_VERSAND = "Versand"
PFAD = Path(__file__).resolve().parents[2] / "config" / "versandkosten.yaml"


@dataclass(frozen=True)
class Versandangabe:
    """Der gemessene Versand eines Anbieters; `betrag` None heißt nicht belegt."""

    anbieter: str
    betrag: float | None = None
    quelle: str = ""
    datum: str = ""
    screenshot: str = ""
    hinweis: str = ""


def laden(pfad: Path = PFAD) -> dict[str, Versandangabe]:
    """Die Datei als Tabelle Anbieter (klein geschrieben) → Angabe."""
    roh = yaml.safe_load(pfad.read_text(encoding="utf-8")) or {}
    tabelle: dict[str, Versandangabe] = {}
    for name, e in (roh.get("anbieter") or {}).items():
        betrag = e.get("betrag")
        if betrag is not None and (isinstance(betrag, bool) or betrag < 0):
            raise ValueError(f"Versand von {name}: kein Betrag {betrag!r}")
        tabelle[name.casefold()] = Versandangabe(
            anbieter=name,
            betrag=None if betrag is None else round(float(betrag), 2),
            quelle=str(e.get("quelle") or ""),
            datum=str(e.get("datum") or ""),
            screenshot=str(e.get("screenshot") or ""),
            hinweis=str(e.get("hinweis") or ""),
        )
    return tabelle


_TABELLE: dict[str, Versandangabe] | None = None


def tabelle() -> dict[str, Versandangabe]:
    """Die Datei, einmal gelesen."""
    global _TABELLE
    if _TABELLE is None:
        _TABELLE = laden()
    return _TABELLE


def versand_fuer(anbieter: str) -> Versandangabe:
    """Die Angabe des Anbieters; ein unbekannter Anbieter ist nicht belegt."""
    return tabelle().get(anbieter.strip().casefold()) or Versandangabe(anbieter.strip())


def hinweis_unbelegt(anbieter: str) -> str:
    """Der Satz an der Zeile, wenn der Versand eines Anbieters nicht belegt ist."""
    return f"Versand bei {anbieter} nicht belegt"
