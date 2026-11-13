"""Tarifwelt: eine als „nicht lieferbar“ gelesene Speicherstufe zählt nicht weiter.

Befund 13.11.2026: Der Lauf las Galaxy S26 Ultra 512 GB als nicht lieferbar, die
Lücke blieb Text im Lauf, das Bündel vom Vortag gewann auf der Seite weiter den
Vergleich. `markiere` setzt deshalb beim Sammeln an jedem Tarifwelt-Bündel derselben
Stufe, das VOR dem Lauftag abgerufen wurde, das Feld `FELD` (Lauftag, ISO);
`ist_nicht_lieferbar` liest es beim Bericht. Wieder mit Preis gelesen (abgerufen am
oder nach dem Feld) zählt das Bündel wieder. Ein unlesbares Datum zählt wie kein Feld.

Wurzelmodul: importiert keine Schicht, damit Sammeln und Bericht es teilen.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date

from .tarifwelt_bestand import PRAEFIX

FELD = "nicht_lieferbar_am"
REGEL_NICHT_LIEFERBAR = 19
"""Keine Regel der Prüfstelle, sondern die Marke, die die Seite beim Lesen setzt
(`report/geraete_sortiment.lies`, Vermerk „veraltet 19“), wie `REGEL_SORTIMENT`.
Steht darum nicht in `geraete_pruefstatus.REGELN` (Regelzähler bleiben)."""


def _datum(wert: object) -> date | None:
    """Ein ISO-Datum als Text, sonst `None` (Zahl, Liste, leer, „unbekannt“)."""
    if not isinstance(wert, str):
        return None
    try:
        return date.fromisoformat(wert)
    except ValueError:
        return None


def sku_praefix(geraet: str, speicher_gb: int) -> str:
    """Anfang jeder SKU dieser Stufe (`geraete_model.sku_id`): „<geraet>-<gb>gb-“.
    Speicher direkt hinter dem Gerät: „galaxy-s26-512gb-“ trifft kein S26 Ultra."""
    return f"{geraet}-{int(speicher_gb)}gb-"


def markiere(
    saetze: Iterable[dict], stufen: Iterable[tuple[str, int]], lauftag: str
) -> int:
    """Setzt `FELD` = `lauftag` an jedem Tarifwelt-Bündelsatz einer nicht lieferbaren
    Stufe ((device_id, Katalogspeicher)), der vor `lauftag` abgerufen wurde. Ändert
    die übergebenen Sätze (Bestand); gibt die Zahl der markierten zurück."""
    tag = _datum(lauftag)
    praefixe = tuple(sku_praefix(g, gb) for g, gb in stufen)
    if tag is None or not praefixe:
        return 0
    markiert = 0
    for satz in saetze:
        if not str(satz.get("tarif_id") or "").startswith(PRAEFIX):
            continue
        if not str(satz.get("sku_id") or "").startswith(praefixe):
            continue
        abgerufen = _datum(satz.get("abgerufen_am"))
        if abgerufen is None or abgerufen >= tag:
            continue
        satz[FELD] = tag.isoformat()
        markiert += 1
    return markiert


def ist_nicht_lieferbar(satz: dict) -> bool:
    """Wurde die Stufe NACH dem Abruf dieses Bündels als nicht lieferbar gelesen?
    Unlesbares Datum (Feld oder Abruf) heißt nein."""
    am = _datum(satz.get(FELD))
    abgerufen = _datum(satz.get("abgerufen_am"))
    return am is not None and abgerufen is not None and am > abgerufen
