"""Teile eines Belegs je Preis: Konfigurationsbild, Rohwerte, Messzeit.

Rechnet nichts (Vertrag ``report-rechnet-nur``); die Wahl der Gegenprobe steht in
``gegenprobe_belege``, die Liste der aufbewahrten Bilder in ``gegenprobe_ablage``.
Das Konfigurationsbild ist das Bild der Gegenprobe (Modulkopf von
``geraete_preisbeleg``); fehlt es, nennt ``konfig`` den Grund.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from zoneinfo import ZoneInfo

from .. import gegenprobe as gp
from .. import gegenprobe_belege as gb
from ..gegenprobe_ablage import Liste
from .geraete_tco_grafik import euro

ZEITZONE = ZoneInfo("Europe/Berlin")

ROH_HOECHSTENS = 8
"""So viele gelesene Zeilen der Seite stehen am Beleg."""


def datum_de(iso: str | None) -> str:
    """„20.11.2026“ aus „2026-11-20“; leer bleibt leer."""
    if not iso:
        return ""
    jahr, monat, tag = iso[:10].split("-")
    return f"{tag}.{monat}.{jahr}"


def uhrzeit(iso: str | None) -> str:
    """„17:34 Uhr“ (Berlin) aus einem ISO-Zeitpunkt mit Zone; sonst leer."""
    if not iso:
        return ""
    try:
        zeit = datetime.fromisoformat(iso)
    except ValueError:
        return ""
    if zeit.tzinfo is None:
        return ""
    return f"{zeit.astimezone(ZEITZONE):%H:%M} Uhr"


def zeitpunkt(iso: str | None) -> str:
    """„20.11.2026, 03:48 Uhr“ (Berlin) aus einem ISO-Zeitpunkt; sonst leer."""
    if not uhrzeit(iso):
        return ""
    zeit = datetime.fromisoformat(iso or "").astimezone(ZEITZONE)
    return f"{zeit:%d.%m.%Y, %H:%M} Uhr"


def rohwerte(posten: Mapping | None) -> list[str]:
    """Die gespeicherten Posten der Messung („Tarif monatlich: 24,99 €“), wie der
    Sammler sie las; ein fehlender Anschlusspreis steht als „fehlt“."""
    out = []
    for feld in gp.FELDER:
        wert = (posten or {}).get(feld)
        name = gp.FELDNAMEN[feld]
        if wert is not None:
            out.append(f"{name}: {wert if feld in gp.GANZZAHLFELDER else euro(wert)}")
        elif feld == "anschlusspreis" and posten:
            out.append(f"{name}: fehlt")
    return out


def seite_roh(e: gp.Ergebnis | None) -> list[str]:
    """Was die Gegenprobe auf der Seite las, mit deren Beschriftung."""
    roh = (e.gelesen or {}).get("roh") if e is not None else None
    return [f"{k}: {v}" for k, v in (roh or {}).items()][:ROH_HOECHSTENS]


def konfig(
    e: gp.Ergebnis | None,
    liste: Liste | None = None,
    datum: str = "",
    ohne_probe: str = gb.GRUND_KEINE,
) -> tuple[dict | None, str]:
    """(Konfigurationsbild, Grund ohne Bild) einer Gegenprobe (Modulkopf); ``datum``
    ist der Stand der Seite (``gegenprobe_belege.aufbewahrt``)."""
    if e is None:
        return None, ohne_probe
    if e.status == gp.NICHT_GEGENGEPRUEFT:
        return None, f"nicht geöffnet ({e.grund})"
    if not e.bild:
        return None, e.bild_fehlt or gb.GRUND_OHNE_BILD
    if not gb.aufbewahrt(datum, e.datum):
        return None, gb.GRUND_ALT
    if liste is not None and not liste.vorhanden(e.bild, gb.MINDEST_TAGE):
        return None, gb.GRUND_GELOESCHT
    return {
        "url": e.bild,
        "datum": datum_de(e.datum),
        "art": "Gegenprobe" if e.status in gp.GEPRUEFT else "Versuch",
        "zeigt": ", ".join(e.bild_zeigt or []),
        "ohne": ", ".join(e.bild_ohne or []),
        "nur_preis": e.bild_zeigt is None,
    }, ""


def messzeit(abgerufen_am: str, e: gp.Ergebnis | None) -> str:
    """Messtag des Sammlers, mit Uhrzeit, wenn die Gegenprobe den Messlauf kennt."""
    if e is not None and e.gemessen_um and e.gemessen_um[:10] == abgerufen_am:
        return zeitpunkt(e.gemessen_um) or datum_de(abgerufen_am)
    return datum_de(abgerufen_am)
