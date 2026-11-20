"""1&1: GERAETERATEN gegen MINDESTBINDUNG - die Gegenprobe des Rasters.

Die Geraeteraster (`/smartphones-<tarif>`) bewerben seit dem 20.11.2026
die Flex-Finanzierung: `data-hardware-months="48"` auf JEDER der 41
Kacheln, iPhone 17 Pro 37,99 statt 59,99 (Geraete-Lauf 44728882384).
Diese Zahl ist NICHT die Mindestbindung - die bleibt laut Datalayer der
Geraeteseite (`tariff.contractduration`) 24 - sondern die Zahl der
GERAETERATEN des beworbenen Angebots. Die Gegenprobe in
`einsundeins.ergaenze_tarifstufen` hat sie bis dahin gegen
`laufzeit_monate` des Satzes geprueft und deshalb ALLE 41 Geraete
verworfen ("41 Geraete ohne passende Gegenprobe", keine einzige
hergeleitete Tarifstufe).

Auf der Geraeteseite steht dieselbe Zahl nur mittelbar: als
`hardwareTotalPrice / hardwarePricePerMonth` je Stufe der Preiskarte
("36 + 12 Monate Flex" = 1200,00 / 25,00 = 48 Raten). Genau darueber
laesst sich ein Rasterpreis gegen die Geraeteseite pruefen - und nur
dafuer liest `geraeteraten_preise` auch "flex". VEROEFFENTLICHT wird
weiter allein der Betrag aus `einsundeins._fixpreis` zur Mindestbindung
plus Tarifaufschlag; eine "flex"-Zahl ist hier Beleg, nie Preis.
"""

from __future__ import annotations

from ...tarif_model import zahl

_STUFEN = ("fix", "flex")


def flache_tarifrate(stufe: dict, monate: int) -> float | None:
    """Die Tarifrate einer Stufe, wenn sie ueber `monate` FLACH belegt ist.

    Belegt heisst: der erste Eintrag von `tariffMonthlyPrices` beginnt in
    Monat 1, nennt denselben Betrag wie `tariffPricePerMonth` und deckt
    mindestens `monate` (`end` 0 oder fehlend = bis auf Weiteres). Sonst
    `None` - lieber keine Zahl als eine 24+12-Zahl (Kopf von
    `einsundeins.py`).
    """
    tarifrate = zahl(str(stufe.get("tariffPricePerMonth")))
    monatspreise = stufe.get("tariffMonthlyPrices")
    if tarifrate is None or not monatspreise:
        return None
    erster = monatspreise[0]
    flach_bis = erster.get("end")
    deckt = flach_bis in (0, None) or flach_bis >= monate
    betrag = round(float(erster.get("amount", -1)), 2)
    if erster.get("begin") != 1 or not deckt or betrag != round(tarifrate, 2):
        return None
    return tarifrate


def _raten(stufe: dict, hardwarerate: float) -> int | None:
    """Die Zahl der Geraeteraten einer Stufe; `None`, wenn sie nicht glatt
    aufgeht (dann ist `hardwareTotalPrice` keine Ratensumme)."""
    gesamt = zahl(str(stufe.get("hardwareTotalPrice")))
    if gesamt is None:
        return None
    raten = gesamt / hardwarerate
    if abs(raten - round(raten)) > 1e-6 or round(raten) <= 0:
        return None
    return int(round(raten))


def geraeteraten_preise(karteneintrag: dict) -> dict:
    """{Zahl der Geraeteraten: Monatsbetrag} EINER Variante der Preiskarte.

    Gelesen werden beide Stufen jeder Finanzierungsdauer, aber nur mit
    ueber ihre eigene Ratenzahl flacher Tarifrate (Modulkopf).
    """
    out: dict = {}
    for stufen in (karteneintrag or {}).values():
        if not isinstance(stufen, dict):
            continue
        for name in _STUFEN:
            stufe = stufen.get(name)
            if not isinstance(stufe, dict):
                continue
            hardwarerate = zahl(str(stufe.get("hardwarePricePerMonth")))
            if not hardwarerate:
                continue
            raten = _raten(stufe, hardwarerate)
            tarifrate = flache_tarifrate(stufe, raten) if raten else None
            if raten is None or tarifrate is None:
                continue
            out.setdefault(raten, round(hardwarerate + tarifrate, 2))
    return out


def gegenwert(vorher: dict | None, raten: int | None) -> float | None:
    """Der Betrag, gegen den ein Rasterpreis zu pruefen ist - oder `None`.

    Zwei Belege, und immer nur EINER von beiden gilt:

    * Nennt die Geraeteseite einen eigenen angezeigten Preis, der von
      ihrem Preiskarten-Betrag ABWEICHT, dann gilt dieser - er enthaelt
      dasselbe wie die Rasterkachel (am 29.09.2026 die Galaxy Buds am
      S26 Ultra: 44,99 angezeigt, 42,99 Buendel).
    * Sonst (seit K1 der Regelfall: `_angezeigter_preis` faellt auf den
      Preiskarten-Betrag zurueck) gilt der Betrag der Preiskarte zu
      GENAU der Ratenzahl der Kachel.
    """
    if not vorher or raten is None:
        return None
    angezeigt = vorher.get("angezeigt_monatlich")
    betrag = vorher.get("buendel_monatlich")
    if angezeigt is None:
        return None
    if betrag is None or round(angezeigt * 100) != round(betrag * 100):
        return angezeigt
    return (vorher.get("raten_preise") or {}).get(raten)
