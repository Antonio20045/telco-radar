"""Belegte Lücken (`config/geraete_abdeckung.yaml`) in der Modellansicht.

Eine belegte Lücke (Gerät oder Speicherstufe „nicht im Sortiment“, mit Prüfdatum)
gilt für alle Anbieter gleich:

* Ein Preis, der nicht jünger ist als die Prüfung der Lücke (`abgerufen_am` <=
  `geprueft`, oder unlesbar), ist veraltet und wird zur Lücke (fail-closed).
* Ein Preis, der jünger ist als die Prüfung, widerspricht ihr: er bleibt stehen,
  die Lücke gilt dann als falsch und wird gemeldet (`widersprueche`), nie still
  angezeigt.
* Eine Lücke gilt erst ab ihrem Prüfdatum: ein älterer Stand (`heute` davor)
  kennt sie nicht.
* Fehlt dem Modell danach jeder neue Preis des Anbieters, nennt die Zeile des
  Anbieters den Grund samt Prüfdatum statt „Noch nicht erfasst“.

Gültig ist ein Beleg wie in der Portfolio-Ansicht (`geraete_portfolio.beleg_fuer`:
Sortiments-Aussage im Grund, heute <= `bis`). Kein Abruf, nur Config und Bündel.
"""

from __future__ import annotations

import logging
from datetime import date

from ..analyze.buendel_abdeckung import modell_und_speicher
from .geraete_portfolio import beleg_fuer

log = logging.getLogger(__name__)

KURZ = "Nicht im Sortiment (geprüft {geprueft})"
SATZ = "{grund}. Geprüft {geprueft}, gültig bis {bis}."


def _tag(wert) -> str:
    return f"{wert.day:02d}.{wert.month:02d}."


def _voll(wert) -> str:
    return f"{_tag(wert)}{wert.year}"


def stufe(speicher_gb) -> str | None:
    """Speicherstufe im Format der Config ("512gb"), `None` ohne Angabe."""
    return f"{int(speicher_gb)}gb" if speicher_gb else None


def _gueltig(belege: dict, anbieter, modell: str, heute: str, gb) -> dict | None:
    """Der gültige Beleg (`beleg_fuer`) - und nur, wenn die Prüfung am Stichtag
    schon stattgefunden hat: ein Stand vor der Prüfung kennt die Lücke nicht."""
    beleg, _ = beleg_fuer(belege, str(anbieter or ""), modell, heute, gb)
    return beleg if beleg and beleg["geprueft"].isoformat() <= heute else None


def _jung_genug(abgerufen, geprueft: date) -> bool:
    """Der Preis ist NACH der Prüfung abgerufen; unlesbar heißt nein (fail-closed)."""
    try:
        return date.fromisoformat(str(abgerufen)) > geprueft
    except ValueError:
        return False


def ohne_widerlegte(buendel: list[dict], belege: dict, heute: str) -> list[dict]:
    """Die Bündel ohne neue Preise, die eine gültige belegte Lücke überholt hat.

    Nur Neugeräte; Aufarbeitungen sind ein anderes Sortiment. Ein jüngerer Preis
    bleibt und wird mit Warnung genannt."""
    if not belege or not heute:
        return buendel
    behalten, widerspruch = [], set()
    for b in buendel:
        modell, speicher = modell_und_speicher(str(b.get("sku_id") or ""))
        beleg = None
        if modell and (b.get("zustand") or "neu") == "neu":
            beleg = _gueltig(belege, b.get("anbieter"), modell, heute, speicher)
        if beleg and not _jung_genug(b.get("abgerufen_am"), beleg["geprueft"]):
            continue
        if beleg:
            widerspruch.add((b.get("anbieter"), modell, speicher))
        behalten.append(b)
    for anbieter, modell, speicher in sorted(widerspruch, key=str):
        log.warning(
            "Belegte Lücke widerlegt: %s führt %s %s mit Preis nach der Prüfung - "
            "Lücke in config/geraete_abdeckung.yaml prüfen",
            anbieter,
            modell,
            speicher,
        )
    return behalten


def fuer_modell(belege: dict, modell: dict, heute: str) -> dict[str, dict]:
    """{Anbieter: Lücke} für ein Modell der Seite: gültig belegt und ohne jeden
    neuen Preis des Anbieters in diesem Modell."""
    device_id, gb = modell.get("device_id"), stufe(modell.get("speicher"))
    mit_preis = {
        k.get("anbieter")
        for k in modell.get("karten") or []
        if (k.get("zustand") or "neu") == "neu" and k.get("sku_id")
    }
    aus: dict[str, dict] = {}
    for anbieter in {k[0] for k in belege}:
        if anbieter in mit_preis or not device_id:
            continue
        beleg = _gueltig(belege, anbieter, device_id, heute, gb)
        if beleg:
            aus[anbieter] = {
                "kurz": KURZ.format(geprueft=_tag(beleg["geprueft"])),
                "satz": SATZ.format(
                    grund=str(beleg["grund"]).rstrip(". "),
                    geprueft=_voll(beleg["geprueft"]),
                    bis=_voll(beleg["bis"]),
                ),
            }
    return aus
