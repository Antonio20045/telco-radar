"""Die Rechnung an der Bündelzeile: die Summanden der Kernzahl in Worten.

Antonio, 07.10.2026: auf einen Blick sehen, wie der Preis zustande kommt. Die
Summanden rechnet `tco_kosten.kosten_ueber` (`Kosten.rechnung`), die Referenz-
rechnung `tco_kosten.tarifschritte`; hier bekommen sie ihr Wort. Die Summanden
der Referenz werden gegen ihre Tarifsumme gehalten, nie an ihre Stelle gesetzt.
"""

from __future__ import annotations

from ..tarif_model import Preisphase
from ..tco_kosten import (
    SCHRITT_ANSCHLUSS,
    SCHRITT_ANZAHLUNG,
    SCHRITT_BARPREIS,
    SCHRITT_GERAET,
    SCHRITT_TARIF,
    SCHRITT_VERTRAG,
    Kosten,
    Rechenschritt,
    tarifschritte,
)
from ..tco_model import POSTEN_ANSCHLUSS, POSTEN_BUENDEL, POSTEN_TARIF, POSTEN_ZUZAHLUNG

WORT_JE_SCHRITT = {
    SCHRITT_BARPREIS: "Gerät ohne Vertrag",
    SCHRITT_GERAET: "Gerät",
    SCHRITT_VERTRAG: "Tarif mit Gerät",
    SCHRITT_TARIF: "Tarif",
    SCHRITT_ANZAHLUNG: "Anzahlung",
    SCHRITT_ANSCHLUSS: "Anschluss",
}
WORT_JE_LUECKE = {
    POSTEN_TARIF: "Tarif",
    POSTEN_ZUZAHLUNG: "Anzahlung",
    POSTEN_ANSCHLUSS: "Anschluss",
    POSTEN_BUENDEL: "Tarif mit Gerät",
}


def zum_lesen(schritte: list[Rechenschritt]) -> list[dict]:
    """Die Summanden mit ihrem Wort für die Zeile."""
    return [
        {"anzahl": s.anzahl, "betrag": s.betrag, "wort": WORT_JE_SCHRITT[s.art]}
        for s in schritte
    ]


def luecken_zum_lesen(luecken: list[str]) -> list[str]:
    """„Tarif Monat 25–36 nicht genannt“ statt „Tarifgrundpreis Monat 25–36“."""
    fertig = []
    for luecke in luecken:
        for posten, wort in WORT_JE_LUECKE.items():
            if luecke.startswith(posten):
                luecke = wort + luecke[len(posten) :]
                break
        fertig.append(f"{luecke} nicht genannt")
    return fertig


def felder(kosten: Kosten) -> dict:
    """Die Felder der Bündelkarte: Summanden und, ohne Kernzahl, was fehlt."""
    return {
        "rechnung": zum_lesen(kosten.rechnung),
        "rechnung_luecken": luecken_zum_lesen(kosten.luecken),
    }


def referenz(ref: dict) -> list[dict]:
    """Die Summanden der Vodafone-Referenzrechnung: Barpreis plus Tarif über die
    Monate der Referenz, je Preisphase wie `phasensumme` sie zählt. Ergeben die
    Schritte nicht die Tarifsumme der Referenz (`tarif_summe`), steht sie als ein
    Betrag; leer für eine Referenz ohne diese Angaben."""
    monate, monatlich = ref.get("tarif_monate"), ref.get("monatlich")
    if not monate or monatlich is None or ref.get("geraet_betrag") is None:
        return []
    bar = ref["geraet_betrag"]
    summe = ref.get("tarif_summe")
    tarif = tarifschritte(ref.get("phasen") or [], monate)
    if summe is not None and round(sum(t.summe for t in tarif), 2) != summe:
        tarif = tarifschritte([Preisphase(1, None, monatlich)], monate)
    if summe is not None and round(sum(t.summe for t in tarif), 2) != summe:
        tarif = [Rechenschritt(SCHRITT_TARIF, None, summe, summe)]
    return zum_lesen([Rechenschritt(SCHRITT_BARPREIS, None, bar, bar), *tarif])
