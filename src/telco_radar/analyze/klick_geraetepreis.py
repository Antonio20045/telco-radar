"""Gerätepreise ohne Tarif als Gegenprobe (Datenkonzept Geräteradar §7 und §9).

Vodafone wählt den Tarif erst auf der Folgeseite; die Klick-Karte liest auf der
Produktseite Anzahlung, Rate und Ratenzahl, der Tarif bleibt ``unbekannt``, ein Bündel
wird daraus nicht (``klickrohsatz.geraetepreis``). Die Tarifseite lädt dieselbe
Schnittstelle, die der Vodafone-Adapter liest (glados ``tariff/v2/hardware``,
Erkundung 07.10.2026), und zeigt dieselben Preise: 62,61 € im Monat sind 29,61 € Tarif
(Mobil M) und 33,00 € Rate. Ein Tarifschritt im Klick brächte dieselben Zahlen einen
Schritt später.

``gegenprobe_geraet`` prüft darum jeden Gerätepreis ohne Tarif gegen die Adaptersätze
mit gleichem Anbieter, Gerät, Speicher und gleicher Ratenzahl (nur Zustand neu, mit
Rate): gleich, wenn mindestens einer die Rate und, wo beide sie nennen, die Anzahlung
auf den Cent trifft, denn der Klick liest den Gerätepreis zum vorgewählten Tarif;
sonst abweichend; ohne solchen Adaptersatz ohne Gegenstück. Eine unbekannte Ratenzahl
fällt aus dem Vergleich (``ohne_ratenzahl``). Am 08.10.2026 waren 15 von 15 gleich.
Ersetzt wird nichts. Die Zahlen stehen in der Klick-Bilanz und als eine Zeile im
Protokoll, als Warnung, sobald eine abweicht oder ohne Gegenstück ist; jede Abweichung
steht mit Beispiel darunter.
"""

from __future__ import annotations

import logging
from collections import Counter
from collections.abc import Callable

from ..tco_model import laufzeit_in_monaten
from .klick_vollstaendig import CENT

BEISPIELE = 8
ZUSTAND_NEU = "neu"
ANZAHLUNG = "geraet_zuzahlung"
RATE = "geraet_monatsrate"
ZAEHLER = ("gleich", "abweichend", "ohne_gegenstueck", "ohne_ratenzahl")

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
        if schluessel is not None and _betrag(satz.get(RATE)):
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
        if schluessel[3] is None:
            zahl["ohne_ratenzahl"] += 1
        elif not saetze:
            zahl["ohne_gegenstueck"] += 1
        elif any(_gleich(preis, satz) for satz in saetze):
            zahl["gleich"] += 1
        else:
            zahl["abweichend"] += 1
            if len(beispiele) < BEISPIELE:
                beispiele.append(_beispiel(schluessel, preis, saetze))
    ergebnis = {f: zahl[f] for f in ZAEHLER}
    if geraetepreise:
        stufe = (
            logging.WARNING
            if zahl["abweichend"] or zahl["ohne_gegenstueck"]
            else logging.INFO
        )
        log.log(stufe, "Gerätepreise ohne Tarif gegen Adapter: %s", ergebnis)
    for beispiel in beispiele:
        log.warning("Gerätepreis ohne Tarif weicht ab: %s", beispiel)
    return {**ergebnis, "beispiele": beispiele}


def _adapterschluessel(satz: dict, geraet: Geraet) -> Schluessel | None:
    if str(satz.get("zustand") or ZUSTAND_NEU) != ZUSTAND_NEU:
        return None
    device, speicher = geraet(str(satz.get("sku_id") or ""))
    laufzeit = laufzeit_in_monaten(satz.get("laufzeit_monate"))
    if not device or laufzeit is None:
        return None
    speicher = satz.get("speicher_gb") if speicher is None else speicher
    return (str(satz.get("anbieter")), device, speicher, laufzeit)


def _gleich(preis: dict, satz: dict) -> bool:
    for feld in (ANZAHLUNG, RATE):
        klick, alt = preis.get(feld), satz.get(feld)
        if _betrag(klick) and _betrag(alt) and abs(klick - alt) > CENT:
            return False
    return _betrag(preis.get(RATE))


def _betrag(wert: object) -> bool:
    return isinstance(wert, int | float) and not isinstance(wert, bool)


def _beispiel(schluessel: Schluessel, preis: dict, saetze: list[dict]) -> str:
    gelesen = f"{preis.get('geraet_zuzahlung')} / {preis.get('geraet_monatsrate')}"
    paare = sorted(
        {(s.get("geraet_zuzahlung"), s.get("geraet_monatsrate")) for s in saetze},
        key=str,
    )
    adapter = ", ".join(f"{z} / {r}" for z, r in paare[:3])
    text = "|".join("" if teil is None else str(teil) for teil in schluessel)
    return f"{text}: Klick {gelesen}, Adapter {adapter}"
