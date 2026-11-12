"""Tarifwelt: die Pruefungen, die aus einer Antwort einen Preis oder eine
benannte Luecke machen (`tarifwelt_lauf` ruft nur `pruefe`).

Eine Antwort wird nur dann zum Preis, wenn sie GENAU die bestellte Zeile
beschreibt: derselbe Tarif, dasselbe Geraet, derselbe Speicher, dieselbe
Hardware (`hwi`), ein Bestand groesser null und eine Zuzahlung, die dem
Barpreis derselben Variante entspricht. Alles andere ist eine Luecke mit
Grund, nie ein stilles leeres Ergebnis (Clean Code 5).
"""

from __future__ import annotations

import logging

from ... import versandkosten
from . import tarifwelt
from .tarifwelt_merkmale import unvergleichbar_grund

log = logging.getLogger(__name__)

LAUFZEIT_MONATE = 24
MONAT_TOLERANZ = 0.01


def _vergleichsname(wert: str | None) -> str:
    """Modellname ohne Leerzeichen, Bindestriche und Gross-/Kleinschreibung -
    "Galaxy Z Fold8" und "Galaxy Z Fold 8" sind dasselbe Geraet."""
    return "".join((wert or "").split()).replace("-", "").casefold()


def pruefe(
    satz: dict | None, gewollt: dict, speicher: int, name: str, hwi: str
) -> tuple[str | None, bool]:
    """(Grund fuer eine Luecke oder `None`, ob der Tarif nur "nicht waehlbar"
    ist). `None` heisst: genau die verlangte Variante - dasselbe Geraet,
    derselbe Speicher, derselbe Tarif, und lieferbar."""
    if satz is None:
        return "Tarif fuer dieses Geraet nicht waehlbar (leere Antwort)", True
    if satz["tarif_id"] != gewollt["tarif_id"]:
        return "Antwort traegt einen anderen Tarif", True
    if _falscher_speicher(satz, speicher):
        return f"Tarif nicht fuer {speicher} GB waehlbar (anderer Speicher)", True
    if grund := _pruefe_variante(satz, name, hwi):
        return grund, False
    if satz.get("geraeteposten") != 1:
        return f"{satz.get('geraeteposten')} Geraeteposten statt 1", False
    if satz["laufzeit_monate"] != LAUFZEIT_MONATE:
        return f"Laufzeit {satz['laufzeit_monate']} statt {LAUFZEIT_MONATE}", False
    if grund := unvergleichbar_grund(satz):
        return f"nicht vergleichbar: {grund}", False
    for feld in ("grundgebuehr", "geraet_zuzahlung", "anschlusspreis"):
        if satz[feld] is None:
            return f"{feld} fehlt", False
    bar = satz.get("variante_preis")
    if bar is None or round(abs(bar - satz["geraet_zuzahlung"]), 2) > MONAT_TOLERANZ:
        return (
            f"Zuzahlung {satz['geraet_zuzahlung']} weicht vom Geraetepreis "
            f"{bar} derselben Variante ab",
            False,
        )
    return _pruefe_kosten(satz)


def _falscher_speicher(satz: dict, speicher: int) -> bool:
    """Die gelieferte Variante nennt ihren Speicher als Zahl; das Text-Label
    des Kostenpostens nennt ihn noch einmal. Beide muessen die verlangte
    Stufe tragen."""
    if satz.get("variantenzahl") == 1 and satz.get("variante_speicher") != speicher:
        return True
    return f"{speicher} GB" not in (satz.get("geraet_label") or "")


def _pruefe_variante(satz: dict, name: str, hwi: str) -> str | None:
    """Die Antwort muss GENAU die bestellte Hardware beschreiben und sie muss
    lieferbar sein. Ohne diese Pruefung belegt nur das freie Text-Label des
    Kostenpostens, zu welchem Geraet der Preis gehoert, und die
    Lieferbarkeit stammt allein aus der frueher gelesenen Uebersicht."""
    if satz.get("variantenzahl") != 1:
        return f"Antwort mit {satz.get('variantenzahl')} Varianten statt 1"
    if satz.get("variante_hwi") != hwi:
        return (
            f"Antwort traegt eine andere Hardware ({satz.get('variante_hwi')} "
            f"statt {hwi})"
        )
    if _vergleichsname(satz.get("geraet_name")) != _vergleichsname(name):
        return f"Antwort traegt das Geraet {satz.get('geraet_name')!r} statt {name!r}"
    bestand = satz.get("variante_bestand")
    if bestand is None:
        return "kein Beleg fuer die Lieferbarkeit (Bestand unbekannt)"
    if bestand <= 0:
        return f"nicht lieferbar (Bestand {bestand})"
    return None


def _pruefe_kosten(satz: dict) -> tuple[str | None, bool]:
    """Die Antwort muss zu sich selbst und zur Config passen: Monatspreis gleich
    der Summe der monatlichen Posten (hoechstens `MONAT_TOLERANZ` Abweichung),
    Versandposten gleich dem Betrag in `config/versandkosten.yaml` (Abweichung:
    Luecke und Warnung, Config bleibt unveraendert - sie aendert nur eine
    neue Messung)."""
    summe = satz.get("monat_posten")
    if summe is None:
        return "monatliche Kostenposten fehlen", False
    if round(abs(summe - satz["grundgebuehr"]), 2) > MONAT_TOLERANZ:
        return (
            f"Monatspreis {satz['grundgebuehr']} weicht von der Summe der "
            f"Monatsposten {summe} ab",
            False,
        )
    zeile = tarifwelt.anbieter_zeile(satz.get("netz")) or ""
    erwartet = versandkosten.versand_fuer(zeile).betrag
    if erwartet is not None and satz.get("versand") != erwartet:
        grund = (
            f"Versand {satz.get('versand')} weicht von versandkosten.yaml "
            f"({erwartet}) ab"
        )
        log.warning("Tarifwelt: %s: %s - Luecke, neu messen", zeile, grund)
        return grund, False
    return None, False
