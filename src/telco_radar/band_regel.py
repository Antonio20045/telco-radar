"""Die eine Regel: welches Datenvolumen ist einem Zielwert am naechsten.

Report (`report/geraete_tco_band.band_von_gb`, Vodafone-Tarifleiter) und
Sammeln (`collect/geraete/tarifwelt.waehle_je_band`, Tarifwelt-Netzauswahl)
brauchen dieselbe Regel - "naechstes Volumen, bei Gleichstand das groessere"
- duerfen sich aber nicht gegenseitig importieren (`.importlinter`:
Schichten-Vertrag, Sammeln zitiert nie Berichten). Dieses Wurzelmodul ist
der gemeinsame Ort, denselben Baustein, nicht zwei gleiche.
"""

from __future__ import annotations


def abstand_schluessel(gb: float, ziel_gb: float) -> tuple[float, float]:
    """Sortierschluessel fuer `min()`/`sorted()`: je kleiner, je naeher -
    bei gleichem Abstand gewinnt das groessere Volumen."""
    return (abs(gb - ziel_gb), -gb)
