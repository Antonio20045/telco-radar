"""1&1: wann eine Stufe der Preiskarte ueber ihre Laufzeit belegt ist.

`hwdVariantsHardwarePrices` (Markup seit 20.11.2026, Kopf von
`einsundeins.py`) nennt je Variante und Laufzeit eine "fix"- und eine
"flex"-Stufe mit Geraeterate, Ratensumme und Tarifphasen. Ein Betrag zaehlt
nur, wenn die Tarifrate ueber die ganze Laufzeit flach ist und die
Ratensumme genau diese Zahl von Raten ergibt - sonst ist er die Zahl einer
anderen Laufzeit (etwa "24 + 12 Monate Flex") und bleibt offen.

Bis zum 20.11.2026 stand hier die Gegenprobe der hergeleiteten Tarifstufen
(Rasteraufschlag S->M auf alle Speicher). Die Herleitung ist entfallen: der
Tarifnachlass der Seite haengt an Speicher und Laufzeit, ein uebertragener
Aufschlag ist nicht belegt.
"""

from __future__ import annotations

from ...tarif_model import zahl


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


def raten(stufe: dict, hardwarerate: float) -> int | None:
    """Die Zahl der Geraeteraten einer Stufe; `None`, wenn sie nicht glatt
    aufgeht oder die Rate fehlt (dann ist `hardwareTotalPrice` keine
    Ratensumme dieser Rate)."""
    gesamt = zahl(str(stufe.get("hardwareTotalPrice")))
    if gesamt is None or not hardwarerate:
        return None
    anzahl = gesamt / hardwarerate
    if abs(anzahl - round(anzahl)) > 1e-6 or round(anzahl) <= 0:
        return None
    return int(round(anzahl))
