"""Welche Karte je Anbieter einen Punkt der Preispositionierung bekommt.

Die Auswahl ist die der Seite (`geraete_zeitreihe.band_zeilen`): Zeile des
Bandes M bei 24 Raten, ohne Näherung, frisch und von der Notbremse
zugelassen. Was eine gelesene Zeile widerlegt, ist schon aus den Bündeln der Seite
entfernt (`analyze.geraete_widerspruch`). Wer so fehlt, steht mit `FEHLT_TEXT` als
Lücke.
"""

from __future__ import annotations

from . import geraete_notbremse as notbremse
from . import geraete_zeitreihe
from .geraete_laufzeit import LAUFZEIT_STANDARD

BAND = "m"
LAUFZEIT = LAUFZEIT_STANDARD
FEHLT_TEXT = f"kein geprüfter {LAUFZEIT}-Monats-Preis"


def preise_je_anbieter(modell: dict | None) -> dict[str, dict]:
    """Anbieter -> Karte (Zeile des Bandes M bei 24 Raten) mit geprüftem Preis.

    Die Zeilen kommen aus `band_zeilen`; hier fällt nur heraus, was kein
    Angebot mit Preis ist (Näherung) oder nicht zählt. Wer so fehlt, steht mit
    `FEHLT_TEXT` als Lücke. Ohne Modell: leer."""
    if not modell:
        return {}
    satz = geraete_zeitreihe.band_zeilen(modell, LAUFZEIT).get(BAND) or {}
    karten: dict[str, dict] = {}
    for karte in satz.get("zeilen") or []:
        wert = karte.get("gesamt")
        if karte.get("naeherung") or wert is None:
            continue
        if not karte.get("frisch", True) or not notbremse.zaehlt(karte):
            continue
        karten.setdefault(karte["anbieter"], karte)
    return karten
