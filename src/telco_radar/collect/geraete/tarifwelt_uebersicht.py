"""Tarifwelt (Saturn/MediaMarkt): die Geraeteuebersicht `productdetail/<slug>`.

Eine Speicherstufe zaehlt nur, wenn mindestens EINE ihrer Farben `available` ist
(`hardware.variantFilter`). Die Antwort traegt ausserdem die vorgewaehlte Variante
(`hardware.variants`); sie ist nicht automatisch lieferbar. Am 10.11.2026 stand die
vorgewaehlte Stufe bei iPhone 17e 256 GB, Galaxy S26 Ultra 512 GB, Pixel 10a 128 GB
u. a. auf der Seite als "nicht verfuegbar", und trotzdem entstand ein Preis. Ohne
Nachweis der Lieferbarkeit gibt es nie einen Preis (fail-closed).
"""

from __future__ import annotations

import json


def lies_uebersicht(text: str) -> dict | None:
    """Je lieferbarer Speicherstufe Gruppen-ID, Angebots-ID und `hwi`. Jede Stufe
    hat ihr EIGENES Angebot; die vorgewaehlte Variante gilt nur, wenn ihre eigene
    Farbe lieferbar ist, sonst die erste lieferbare Farbe der Stufe. Eine Stufe
    ohne lieferbare Farbe (oder ohne Beleg dafuer) steht in `nicht_lieferbar`;
    `belegt_nicht_lieferbar` nennt davon nur die Stufen, deren Farben der Filter
    ALLE ausdruecklich mit `available: false` fuehrt - fehlt der Filter oder eine
    Angabe, ist die Stufe nicht gelesen, nicht "nicht lieferbar".
    `None`, wenn nichts lesbar ist."""
    try:
        daten = json.loads(text or "")
    except (json.JSONDecodeError, ValueError):
        return None
    if not isinstance(daten, dict):
        return None
    hardware = daten.get("hardware") or {}
    je_speicher: dict[int, dict] = {}
    gesehen: set[int] = set()
    lieferbar: set[str] = set()
    angaben: dict[int, list[object]] = {}
    for v in hardware.get("variantFilter") or []:
        if not isinstance(v, dict) or not isinstance(v.get("storage"), int):
            continue
        angaben.setdefault(v["storage"], []).append(v.get("available"))
        ogi, ofi, hwi = v.get("offerGroupId"), v.get("offerId"), v.get("hwi")
        if not (ogi and ofi and hwi):
            continue
        gesehen.add(v["storage"])
        if v.get("available"):
            lieferbar.add(hwi)
            je_speicher.setdefault(v["storage"], {"ogi": ogi, "ofi": ofi, "hwi": hwi})
    vorgewaehlt = (
        daten.get("offerGroupId"),
        daten.get("offerId"),
        hardware.get("id"),
    )
    varianten = (hardware.get("variants") or []) if all(vorgewaehlt) else []
    for v in varianten:
        if not (isinstance(v, dict) and isinstance(v.get("storage"), int)):
            continue
        hwi = f"{vorgewaehlt[2]}_{v.get('ebootisId')}"
        if v.get("ebootisId") and hwi in lieferbar:
            je_speicher[v["storage"]] = {
                "ogi": vorgewaehlt[0],
                "ofi": vorgewaehlt[1],
                "hwi": hwi,
            }
        else:
            gesehen.add(v["storage"])
    if not je_speicher and not gesehen:
        return None
    nicht_lieferbar = sorted(gesehen - set(je_speicher))
    return {
        "je_speicher": dict(sorted(je_speicher.items())),
        "nicht_lieferbar": nicht_lieferbar,
        "belegt_nicht_lieferbar": [
            s
            for s in nicht_lieferbar
            if angaben.get(s) and all(a is False for a in angaben[s])
        ],
    }
