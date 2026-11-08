"""Alternativ-Bänder eines Anbieters, der in einem Band fehlt (aus
`geraete_luecken` ausgelagert, Zeilenbegrenzung der Wächter)."""

from __future__ import annotations

from ..tco_model import TCO_HORIZONT, zeitraum_vergleichbar
from . import geraete_notbremse as notbremse
from .geraete_laufzeit import ansicht
from .geraete_rechenweg import _zeitraum_wort
from .geraete_tco_band import band_label


def _alternativen(
    karten: list, band: str, anbieter: str, laufzeit: int | None = None
) -> list[dict]:
    """Die besten Bänder EINES Anbieters, der im gewählten Band fehlt.

    §4.5: „fehlende Anbieter MIT NAMEN und Alternativ-Bändern samt Betrag
    in Klammern" - der Leser sieht nicht nur DASS einer fehlt, sondern wo
    er steht. Nur ECHTE Karten (Bündel mit SKU oder die Näherung) sagen
    etwas darüber, wo ein Anbieter steht; die Leerkarte der Festanbieter
    ist kein Angebot. Und seit A3 nur FRISCHE: ein altes Angebot ist keine
    Alternative von heute (`geraete_tco_karten.ist_frisch`, Clean Code 7 -
    dieselbe Definition wie Zeilen und Kacheln). Und nur Karten, die
    zaehlen: eine Schätzung ist auch als Alternative kein Preis.

    P0-B-z1: jede Alternative traegt ihren ZEITRAUM mit
    (`leitzahl_monate`, gelesen). Ohne ihn stand im Luecken-Satz ein
    36-Monats-Betrag als „mittel 2.019,54 €" mitten unter
    24-Monats-Zahlen. Und die Wahl der guenstigsten je Band vergleicht
    nur INNERHALB eines Zeitraums: der Zeitraum des Horizonts zuerst,
    sonst der kuerzeste gemessene - ein Minimum ueber zwei Laufzeiten
    waere dieselbe Rangfolge, die das Tor verbietet. Seit Datenkonzept
    Geräte Schritt 2 nennt eine Ansicht nur Alternativen IHRER Ratenlaufzeit.
    """
    beste: dict[str, dict] = {}
    for karte in karten:
        if karte.get("anbieter") != anbieter:
            continue
        if laufzeit is not None and ansicht(karte) != laufzeit:
            continue
        if not karte.get("frisch", True) or not notbremse.zaehlt(karte):
            continue
        if not (karte.get("sku_id") or karte.get("naeherung")):
            continue
        b = karte.get("band")
        if (
            b is None
            or not karte.get("vergleichbar")
            or karte.get("gesamt") is None
            or b == band
        ):
            continue
        monate = karte.get("leitzahl_monate")
        rang = (
            0 if zeitraum_vergleichbar(monate, TCO_HORIZONT) else 1,
            monate if monate is not None else 10**6,
            karte["gesamt"],
        )
        if b not in beste or rang < beste[b]["rang"]:
            beste[b] = {"rang": rang, "tco": karte["gesamt"], "monate": monate}
    return [
        {"band": b, "tco": v["tco"], "monate": v["monate"]}
        for b, v in sorted(beste.items())
    ]


def _andere_laufzeiten(alle: list, band: str, laufzeit: int | None) -> list:
    """Die Ratenlaufzeiten, mit denen der Anbieter erfasst ist: im Band die
    gemessenen Raten (Telekom A17 L nur mit 6), sonst die Ansichten."""
    im_band = {
        k["raten_laufzeit"]
        for k in alle
        if k.get("band") == band
        and k.get("raten_laufzeit")
        and ansicht(k) not in (None, laufzeit)
    }
    if im_band:
        return sorted(im_band)
    return sorted({a for k in alle if (a := ansicht(k)) is not None} - {laufzeit})


def _alt_zeitraum(monate, h: int = TCO_HORIZONT) -> str:
    """ " über 36 Monate" - der Zeitraum eines Alternativ-Betrags, oder "".

    Nur bei ABWEICHUNG vom Horizont: eine 24 hinter jeder Zahl in einem
    Satz, der ohnehin von 24 Monaten spricht, waere dieselbe Angabe
    zweimal am selben Ort. Ein unlesbarer Zeitraum wird BENANNT, nie als
    Horizont angenommen (Clean Code 4).
    """
    if zeitraum_vergleichbar(monate, h):
        return ""
    if monate is None:
        return " über eine nicht gemessene Laufzeit"
    return f" über {_zeitraum_wort([monate])}"


def _stufe(band_labels: dict, band: str) -> str:
    """Der Name der Stufe ("XS") aus dem Katalog, sonst aus dem Schluessel."""
    return (band_labels.get(band) or {}).get("label") or band_label(band)
