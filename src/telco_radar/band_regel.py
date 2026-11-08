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


def stufe_fuer(gb: float | None, stufen) -> str | None:
    """Der Schluessel der Stufe, in die ein Datenvolumen faellt - oder `None`.

    `stufen` ist eine Folge `(key, gb)` (die Vodafone-Tarifleiter). `inf`
    (unbegrenzt) faellt nur in eine Stufe, die selbst unbegrenzt ist; jedes
    endliche Volumen in die naechste endliche Stufe (`abstand_schluessel`,
    Gleichstand: die groessere). Fehlendes Volumen oder keine passende
    Stufe heisst `None`: nicht zuordenbar, nie eine geratene Stufe."""
    if gb is None or gb != gb:
        return None
    if gb == float("inf"):
        return next((k for k, g in stufen if g is not None and g == float("inf")), None)
    endlich = [(k, g) for k, g in stufen if g is not None and g != float("inf")]
    if not endlich:
        return None
    return min(endlich, key=lambda s: abstand_schluessel(s[1], gb))[0]
