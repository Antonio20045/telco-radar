"""Tarifwelt (Saturn/MediaMarkt): Merkmale, die einen Tarif unvergleichbar machen.

Allgemeine Merkmale der Schnittstelle, keine Anbieternamen (Entscheidung des
Managers, 10.11.2026). Ein Tarif mit einem dieser Merkmale bekommt keinen Preis:
lieber eine benannte Luecke als ein Preis, der mit dem Vodafone-Buendel nichts zu
tun hat.

* Preisintervall: wechselt der Monatspreis innerhalb der 24 Monate
  (`pricingIntervals`, Rabatt nur in den ersten Monaten), ist die Summe nicht
  "24 x Monatspreis". Ein Wechsel ab Monat 25 stoert nicht.
* `cashback` ungleich 0, `seniors: true`, ein Name mit young, aktion, kids,
  senior, doppelkarte oder 2x.
* Ein Bonus an der Rufnummernmitnahme (`bullets`) wird nie eingerechnet; er steht
  als nicht eingerechnete Aktion an der Zeile ("bis -X EUR mit Rufnummernmitnahme").
"""

from __future__ import annotations

import re

from ...tco_model import AKTION_WECHSELBONUS, Aktion

LAUFZEIT_MONATE = 24
NAMENSMERKMALE = ("young", "aktion", "kids", "senior", "doppelkarte", "2x")
_BETRAG = re.compile(r"(\d+(?:[.,]\d+)?)\s*(?:€|euro)", re.IGNORECASE)


def preiswechsel(intervalle: object) -> bool | None:
    """Wechselt der Monatspreis in den ersten 24 Monaten? `None`, wenn die
    Intervalle fehlen oder nicht lesbar sind (nicht bestimmbar)."""
    liste = intervalle.get("intervals") if isinstance(intervalle, dict) else None
    if not isinstance(liste, list) or not liste:
        return None
    preise: set[float] = set()
    for i in liste:
        if not isinstance(i, dict):
            return None
        start, ende, preis = i.get("startMonth"), i.get("endMonth"), i.get("price")
        if not (isinstance(start, int) and isinstance(ende, int)):
            return None
        if not isinstance(preis, (int, float)):
            return None
        if start <= LAUFZEIT_MONATE:
            preise.add(round(float(preis), 2))
    return len(preise) > 1 if preise else None


def unvergleichbar_grund(satz: dict) -> str | None:
    """Warum dieser Tarif nicht vergleichbar ist, sonst `None`. Der Satz stammt aus
    `tarifwelt.lies_tarifliste` oder `lies_produktdetail`."""
    if satz.get("cashback") not in (0, 0.0, None):
        return f"Cashback {satz.get('cashback')}"
    if satz.get("seniors"):
        return "Seniorentarif"
    name = f"{satz.get('tarif_name') or ''} {satz.get('name') or ''}".lower()
    for merkmal in NAMENSMERKMALE:
        if merkmal in name:
            return f"Tarifname mit {merkmal}"
    if satz.get("doppelkarte"):
        return "Doppelkarte"
    wechsel = satz.get("preiswechsel")
    if wechsel is None:
        return "Preisintervalle nicht lesbar"
    return f"Preis wechselt innerhalb {LAUFZEIT_MONATE} Monaten" if wechsel else None


def wechselbonus_aktionen(hinweise: object, quelle_url: str) -> list[Aktion]:
    """Aus den Vorteilszeilen des Tarifs (`bullets`) ein Bonus, der an der
    Rufnummernmitnahme haengt: nicht eingerechnet, nur als Hinweis."""
    out: list[Aktion] = []
    for text in hinweise if isinstance(hinweise, list) else []:
        t = str(text or "").strip()
        klein = t.lower()
        if "bonus" not in klein or not ("wechsel" in klein or "rufnummer" in klein):
            continue
        treffer = _BETRAG.search(t)
        betrag = float(treffer.group(1).replace(",", ".")) if treffer else None
        out.append(
            Aktion(
                AKTION_WECHSELBONUS, t, quelle_url, betrag=betrag, eingerechnet=False
            )
        )
    return out
