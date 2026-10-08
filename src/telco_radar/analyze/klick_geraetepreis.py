"""Gerätepreise ohne Tarif als Gegenprobe (Datenkonzept Geräteradar §7 und §9).

Vodafone wählt den Tarif erst auf der Folgeseite; die Klick-Karte liest auf der
Produktseite Anzahlung, Rate und Ratenzahl, der Tarif bleibt ``unbekannt``, ein Bündel
wird daraus nicht (``klickrohsatz.geraetepreis``). Die Tarifseite lädt dieselbe
Schnittstelle, die der Vodafone-Adapter liest (glados ``tariff/v2/hardware``,
Erkundung 07.10.2026), und zeigt dieselben Preise: 62,61 € im Monat sind 29,61 € Tarif
(Mobil M) und 33,00 € Rate. Ein Tarifschritt im Klick brächte dieselben Zahlen einen
Schritt später.

``gegenprobe_geraet`` prüft darum jeden Gerätepreis ohne Tarif gegen die Adaptersätze
mit gleichem Anbieter, Gerät, Speicher und gleicher Ratenzahl (nur Zustand neu):
gleich, wenn mindestens einer Anzahlung und Rate auf den Cent nennt, denn der Klick
liest den Gerätepreis zum vorgewählten Tarif; sonst abweichend; ohne passenden
Adaptersatz ohne Gegenstück. Eine Anzahlung, die der Klick nicht liest, wird nicht
verglichen. Am 08.10.2026 waren 15 von 15 gleich. Abweichungen stehen mit Beispiel in
der Bilanz und als Warnung im Protokoll; ersetzt wird nichts.
"""

from __future__ import annotations

import logging
from collections import Counter
from collections.abc import Callable

from ..tco_model import laufzeit_in_monaten
from .klick_vollstaendig import CENT

BEISPIELE = 8
ZUSTAND_NEU = "neu"

Geraet = Callable[[str], tuple[str, int | None]]
Schluessel = tuple[str, str, int | None, int | None]

log = logging.getLogger(__name__)


def gegenprobe_geraet(
    geraetepreise: list[dict], adapter: list[dict], geraet: Geraet
) -> dict:
    """Gleich, abweichend und ohne Gegenstück, mit Beispielen der Abweichungen."""
    index: dict[Schluessel, list[dict]] = {}
    for satz in adapter:
        schluessel = _adapterschluessel(satz, geraet)
        if schluessel is not None:
            index.setdefault(schluessel, []).append(satz)
    zahl: Counter[str] = Counter()
    beispiele: list[str] = []
    for preis in geraetepreise:
        schluessel = (
            str(preis.get("anbieter")),
            str(preis.get("device_id")),
            preis.get("speicher_gb"),
            laufzeit_in_monaten(preis.get("laufzeit_monate")),
        )
        saetze = index.get(schluessel, [])
        if not saetze:
            zahl["ohne_gegenstueck"] += 1
        elif any(_gleich(preis, satz) for satz in saetze):
            zahl["gleich"] += 1
        else:
            zahl["abweichend"] += 1
            if len(beispiele) < BEISPIELE:
                beispiele.append(_beispiel(schluessel, preis, saetze))
    for beispiel in beispiele:
        log.warning("Gerätepreis ohne Tarif weicht ab: %s", beispiel)
    return {
        "gleich": zahl["gleich"],
        "abweichend": zahl["abweichend"],
        "ohne_gegenstueck": zahl["ohne_gegenstueck"],
        "beispiele": beispiele,
    }


def _adapterschluessel(satz: dict, geraet: Geraet) -> Schluessel | None:
    if str(satz.get("zustand") or ZUSTAND_NEU) != ZUSTAND_NEU:
        return None
    device, speicher = geraet(str(satz.get("sku_id") or ""))
    if not device:
        return None
    speicher = satz.get("speicher_gb") if speicher is None else speicher
    laufzeit = laufzeit_in_monaten(satz.get("laufzeit_monate"))
    return (str(satz.get("anbieter")), device, speicher, laufzeit)


def _gleich(preis: dict, satz: dict) -> bool:
    for feld in ("geraet_zuzahlung", "geraet_monatsrate"):
        klick, alt = preis.get(feld), satz.get(feld)
        if klick is None:
            continue
        if not isinstance(alt, int | float) or abs(klick - alt) > CENT:
            return False
    return True


def _beispiel(schluessel: Schluessel, preis: dict, saetze: list[dict]) -> str:
    gelesen = f"{preis.get('geraet_zuzahlung')} / {preis.get('geraet_monatsrate')}"
    paare = sorted(
        {(s.get("geraet_zuzahlung"), s.get("geraet_monatsrate")) for s in saetze},
        key=str,
    )
    adapter = ", ".join(f"{z} / {r}" for z, r in paare[:3])
    text = "|".join("" if teil is None else str(teil) for teil in schluessel)
    return f"{text}: Klick {gelesen}, Adapter {adapter}"
