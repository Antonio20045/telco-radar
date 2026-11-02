"""Welche Karte je Anbieter einen Punkt der Preispositionierung bekommt.

Die Auswahl ist die der Seite (`geraete_zeitreihe.band_zeilen`): Zeile des
Bandes M bei 24 Raten, ohne Näherung, frisch und von der Notbremse
zugelassen. Dazu fällt heraus, was nachweislich falsch ist
(`widerspricht_gelesenem`). Wer so fehlt, steht mit `FEHLT_TEXT` als Lücke.
"""

from __future__ import annotations

import logging

from . import geraete_notbremse as notbremse
from . import geraete_zeitreihe
from .geraete_laufzeit import LAUFZEIT_STANDARD

log = logging.getLogger(__name__)

BAND = "m"
LAUFZEIT = LAUFZEIT_STANDARD
FEHLT_TEXT = f"kein geprüfter {LAUFZEIT}-Monats-Preis"
ZUZAHLUNG_TOLERANZ = 0.005


def widerspricht_gelesenem(karte: dict, karten: list[dict]) -> bool:
    """Widerspricht eine aus der Preisliste abgeleitete Karte der gelesenen?

    1&1 leitet die Tarifstufen aus einem Grundangebot und dem Tarifaufschlag ab;
    die Ablöse hängt nur an der Gerätevariante. Steht für dieselbe Variante
    (`sku_id`) und Ratenlaufzeit eine gelesene Zeile (`vom_crawler`) mit anderer
    Zuzahlung, stammt die Ableitung aus dem falschen Grundangebot. Ohne gelesene
    Gegenzeile ist nichts zu widerlegen. Andere Anbieter rechnen die Zuzahlung je
    Tarif verschieden und fallen nicht darunter (`aus_preisliste`)."""
    zuzahlung = karte.get("zuzahlung")
    if not karte.get("aus_preisliste") or zuzahlung is None:
        return False
    return any(
        k.get("vom_crawler")
        and k.get("zuzahlung") is not None
        and k.get("anbieter") == karte.get("anbieter")
        and k.get("sku_id") == karte.get("sku_id")
        and k.get("raten_laufzeit") == karte.get("raten_laufzeit")
        and abs(k["zuzahlung"] - zuzahlung) > ZUZAHLUNG_TOLERANZ
        for k in karten
    )


def preise_je_anbieter(modell: dict | None) -> dict[str, dict]:
    """Anbieter -> Karte (Zeile des Bandes M bei 24 Raten) mit geprüftem Preis.

    Die Zeilen kommen aus `band_zeilen`; hier fällt nur heraus, was kein
    Angebot mit Preis ist (Näherung), nicht zählt oder einer gelesenen Zeile
    widerspricht. Wer so fehlt, steht mit `FEHLT_TEXT` als Lücke. Ohne Modell:
    leer."""
    if not modell:
        return {}
    alle = modell.get("karten") or []
    satz = geraete_zeitreihe.band_zeilen(modell, LAUFZEIT).get(BAND) or {}
    karten: dict[str, dict] = {}
    for karte in satz.get("zeilen") or []:
        wert = karte.get("gesamt")
        if karte.get("naeherung") or wert is None:
            continue
        if not karte.get("frisch", True) or not notbremse.zaehlt(karte):
            continue
        if widerspricht_gelesenem(karte, alle):
            log.warning(
                "Preisposition: %s %s ohne Punkt, Zuzahlung %s widerspricht der "
                "gelesenen Zeile",
                karte.get("anbieter"),
                karte.get("sku_id"),
                karte.get("zuzahlung"),
            )
            continue
        karten.setdefault(karte["anbieter"], karte)
    return karten
