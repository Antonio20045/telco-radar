"""Die Rechenweise einer Bündelmessung: welche Lesart der Anbieterantwort sie ergab.

Jede Zeile von `geraete_tco_historie.jsonl` und jeder Stand-Eintrag trägt `FELD`;
eine Zeile ohne das Feld ist `ERSTE`. Ändert sich, wie ein Adapter dieselbe Antwort
liest, steigt die Zahl seines Anbieters in `JE_ANBIETER`. Zwei Messungen verschiedener
Rechenweise sind nicht vergleichbar: der Unterschied ist ein benannter Bruch
(`BRUCH`), nie eine Preisbewegung - im Wochenblock (`report.geraete_bewegung`), in der
Zeitreihe und ihrem Rechenweg, beim Sprung zum Vortag (Regel 11) und beim Preissprung
der Abdeckung. Je Anbieter, weil sich die Lesart der übrigen nicht geändert hat: ein
Bruch bei allen hätte ihre Vergleiche ohne Grund gekappt.

Stufen:
  1  bis 07.10.2026 (Zeilen ohne Feld)
  2  Vodafone ab 07.10.2026: Online-Aktionspreis des Tarifs als Preisphase,
     `tarif_monatlich` ist der Preis in Monat 1 (`collect/geraete/vodafone_aktion.py`)
"""

from __future__ import annotations

from collections.abc import Mapping

from .geraete_model import normalisiere
from .tco_model import Buendel

FELD = "rechenweise"
ERSTE = 1
JE_ANBIETER = {"vodafone": 2}
BRUCH = "Rechenweise geändert"


def fuer_anbieter(anbieter: str) -> int:
    """Die Rechenweise, mit der heute die Bündel von `anbieter` gemessen werden."""
    return JE_ANBIETER.get(normalisiere(anbieter or ""), ERSTE)


def felder(satz: object) -> dict:
    """`{FELD: Stufe}` für die gespeicherte Messung eines Bündels, sonst `{}`."""
    if not isinstance(satz, Buendel):
        return {}
    return {FELD: fuer_anbieter(satz.anbieter)}


def der_zeile(zeile: object) -> int:
    """Die Rechenweise einer gespeicherten Zeile; ohne lesbares Feld `ERSTE`."""
    wert = zeile.get(FELD) if isinstance(zeile, Mapping) else None
    return wert if isinstance(wert, int) and not isinstance(wert, bool) else ERSTE


def gleich(*zeilen: object) -> bool:
    """Tragen alle Zeilen dieselbe Rechenweise?"""
    return len({der_zeile(z) for z in zeilen}) <= 1


def juengste(messungen: Mapping) -> dict:
    """Die Messungen `{datum: {"satz": Zeile, ...}}` der jüngsten Rechenweise.

    Ältere stehen hinter einem Bruch und zeichnen keine Stufe in die Reihe.
    """
    stufe = max((der_zeile(m.get("satz")) for m in messungen.values()), default=ERSTE)
    return {d: m for d, m in messungen.items() if der_zeile(m.get("satz")) == stufe}
