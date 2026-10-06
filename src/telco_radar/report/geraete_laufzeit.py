"""Die Ratenlaufzeit als erste Gruppe jedes Vergleichs (Datenkonzept Geräte 5.3/5.4).

Eine Karte mit 24 Raten wird nie gegen eine mit 36 gestellt. Sieger, Antwortsatz,
Δ zu Vodafone, Spanne, Kacheln, Grafik, Wettbewerbsradar und Export gruppieren
zuerst nach der Ratenlaufzeit N (`karte["raten_laufzeit"]`); über Laufzeiten
hinweg gibt es keinen Sieger. Jede Ansicht rechnet über H = größerer Wert aus N
und der Tarifbindung von 24 Monaten (`zeitraum`: 12 → 24, 24 → 24, 36 → 36).

Die Vodafone-Näherung (Tarif ohne Gerät plus eigener Barpreis über 24 Monate)
hat keine Ratenlaufzeit. Sie gehört zur 24er-Ansicht und ist dort nur in ihrem
eigenen Band der Maßstab, und nur, wo Vodafone kein Bündel hat (`modelle()`).
"""

from __future__ import annotations

from ..tco_model import TCO_HORIZONT
from . import geraete_notbremse as notbremse
from . import geraete_tco_karten as karten_modul

LAUFZEITEN = (12, 24, 36)
LAUFZEIT_STANDARD = karten_modul.LAUFZEIT_STANDARD
NICHT_ERFASST = "nicht erfasst"
DELTA_VF_NICHT_ERFASST = "Vodafone nicht erfasst"
DELTA_VF_OHNE_ZAHL = "Vodafone ohne Zahl"
ALLE = "alle"
ALLE_TEXT = (
    "Über alle Laufzeiten gibt es keinen Sieger: verglichen wird nur innerhalb "
    "von " + ", ".join(map(str, LAUFZEITEN[:-1])) + f" oder {LAUFZEITEN[-1]} Raten."
)


def zeitraum(laufzeit: int) -> int:
    """H der Ansicht: so viele Monate trägt jede Zahl der Ansicht `laufzeit`."""
    return max(laufzeit, TCO_HORIZONT)


def ansicht(karte: dict) -> int | None:
    """Die Laufzeit-Ansicht, in der diese Karte steht, oder `None`.

    Eine Karte ohne Ratenlaufzeit oder mit einer, die die Seite nicht als
    Ansicht führt, steht nur unter „alle“ und in keinem Vergleich (Clean Code 4).
    """
    if karte.get("naeherung"):
        return LAUFZEIT_STANDARD
    laufzeit = karte.get("raten_laufzeit")
    return laufzeit if laufzeit in LAUFZEITEN else None


def setze_ansicht(karten: list) -> None:
    """Unter welcher Wahl des Umschalters jede Zeile steht (`laufzeit_sichtbar`).

    Genau unter ihrer eigenen Ansicht: eine Zeile mit 36 Raten steht nie unter
    „24 Monate“, auch nicht als nächstgelegene (Regel 5). Eine Zeile ohne
    Ansicht steht nur unter „alle“ (`ansicht`).
    """
    for k in karten:
        laufzeit = ansicht(k)
        k["laufzeit_sichtbar"] = ALLE if laufzeit is None else str(laufzeit)


def gruppe(karte: dict) -> tuple:
    """Der Vergleichsschlüssel einer Karte: (Band, Laufzeit-Ansicht)."""
    return (karte.get("band"), ansicht(karte))


def zaehlende_eigene(karten: list) -> list:
    """Eigene Karten, die eine Referenz stellen dürfen - dieselbe Menge wie bisher."""
    return [
        k
        for k in filter(notbremse.zaehlt, karten)
        if k["eigen"] and k["belastbar"] and k["vergleichbar"] and k["frisch"]
    ]


def referenzen(karten: list) -> dict:
    """{(Band, Laufzeit): Referenz} - je Gruppe die günstigste eigene Karte."""
    beste: dict = {}
    for k in zaehlende_eigene(karten):
        schluessel = gruppe(k)
        if schluessel[1] is None or k["gesamt"] is None:
            continue
        if schluessel not in beste or k["gesamt"] < beste[schluessel]["gesamt"]:
            beste[schluessel] = k
    return {s: karten_modul._referenz_aus_buendel(k) for s, k in beste.items()}


def _ohne_referenz(karte: dict, karten: list) -> dict | None:
    """Der benannte Zustand einer Zeile, deren Gruppe keine Vodafone-Zahl hat."""
    if not karten_modul.zeile_vergleichbar(karte):
        return None
    if gesperrt := notbremse.zustand(karte):
        return gesperrt
    band, laufzeit = gruppe(karte)
    if laufzeit is None:
        return {
            "kurz": karten_modul.DELTA_ANDERE_LAUFZEIT,
            "satz": (
                "Kein Abstand zur Vodafone-Referenz: zu dieser Ratenlaufzeit "
                "führt die Seite keinen Vergleich."
            ),
        }
    vodafone = [
        k
        for k in karten
        if k["eigen"] and k.get("sku_id") and gruppe(k) == (band, laufzeit)
    ]
    if vodafone:
        return {
            "kurz": DELTA_VF_OHNE_ZAHL,
            "satz": (
                f"Kein Abstand: das Vodafone-Bündel mit {laufzeit} Raten in "
                f"diesem Band hat keine vollständige, aktuelle Zahl."
            ),
        }
    return {
        "kurz": DELTA_VF_NICHT_ERFASST,
        "satz": (
            f"Kein Abstand: ein Vodafone-Bündel mit {laufzeit} Raten ist in "
            f"diesem Band {NICHT_ERFASST}."
        ),
    }


def setze_deltas(
    karten: list, naeherung: dict | None, band_je_tarif: dict, heute: str
) -> dict:
    """Δ jeder Karte gegen die Vodafone-Karte mit gleichem Band und gleicher Laufzeit.

    Gibt die Referenzen je Gruppe zurück. Die Näherung ergänzt nur die
    24er-Gruppe ihres eigenen Bandes und nur, solange beide Summanden frisch sind.
    """
    massstab = referenzen(karten)
    if naeherung is not None and karten_modul.referenz_ist_frisch(naeherung, heute):
        band = band_je_tarif.get(naeherung.get("tarif_id") or "")
        massstab.setdefault((band, LAUFZEIT_STANDARD), naeherung)
    for k in karten:
        ref = massstab.get(gruppe(k))
        k["delta"] = karten_modul._delta(k, ref)
        k["delta_zustand"] = (
            karten_modul.delta_zustand(k, ref)
            if ref is not None
            else _ohne_referenz(k, karten)
        )
    return massstab


def spannen(karten: list) -> dict:
    """{Laufzeit: [kleinste, größte]} der zählenden, frischen Angebote je Ansicht."""
    je: dict = {}
    for k in filter(notbremse.zaehlt, karten):
        laufzeit = ansicht(k)
        if (
            laufzeit is None
            or k["naeherung"]
            or not (k["belastbar"] and k["vergleichbar"] and k["frisch"])
            or k["gesamt"] is None
        ):
            continue
        je.setdefault(laufzeit, []).append(k["gesamt"])
    return {lz: [min(werte), max(werte)] for lz, werte in sorted(je.items())}


def modell_referenz(massstab: dict, naeherung: dict | None) -> dict | None:
    """Die Referenz des Modells für die Standardansicht (24 Raten), sonst die
    Näherung - der Maßstab, den Katalogzeile und Radar als Vodafone-Basis nennen."""
    standard = [ref for (_band, lz), ref in massstab.items() if lz == LAUFZEIT_STANDARD]
    eigene = [ref for ref in standard if ref.get("aus_buendel")]
    if eigene:
        return min(eigene, key=lambda r: r["gesamt"])
    return naeherung
