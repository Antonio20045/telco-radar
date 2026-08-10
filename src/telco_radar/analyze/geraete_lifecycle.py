"""Lifecycle-Auswertung des Geraeteradars - deterministisch, ohne Modell.

Vier Fragen, alle aus der Historie gerechnet:

    Listungsdauer     Wie lange steht ein Geraet bei einem Anbieter im Regal?
    Preisverfall      Wie weit ist der Preis vom Einfuehrungspreis entfernt?
    Nachfolger-Effekt Was passiert mit dem Vorgaenger, wenn der Nachfolger
                      erscheint - nach 30, 60 und 90 Tagen?
    Portfolio-Tiefe   Wie viele Generationen fuehrt ein Anbieter gleichzeitig?

Die vierte ist der Kern von Antonios Beobachtung: Wettbewerber halten das
Vorgaengermodell als Preiseinstieg im Regal, waehrend bei Vodafone das alte
Geraet meist direkt ersetzt wird. Diese Zahl macht den Unterschied sichtbar.

KEIN LLM, und das ist keine Sparmassnahme. Jede Zahl hier laesst sich gegen
`data/state/geraete_preise.jsonl` nachrechnen; ein Modell dazwischen waere
eine Schicht, die niemand pruefen kann.

DIE EHRLICHKEIT UEBER DIE DATENBASIS
------------------------------------
In den ersten Wochen gibt es schlicht keine Historie. Aus zwei Messpunkten
laesst sich trotzdem eine Kurve zeichnen, und sie sieht gut aus - genau das
tut diese Seite nicht. Unterhalb von `MIND_PUNKTE` Messpunkten traegt jedes
Ergebnis `duenn: True` und einen Satz, der die Zahl nennt, auf der es beruht.
Ein Test haelt das fest.
"""
from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Optional

from ..geraete_model import Katalog
from .geraete_store import STATUS_AKTIV, STATUS_VERMUTLICH

log = logging.getLogger(__name__)

# Ab so vielen Messpunkten gilt die Datenbasis als tragfaehig. Zwoelf
# entspricht bei zwei Laeufen je Woche rund sechs Wochen - genug, um eine
# Preisstufe von einer Aktion zu unterscheiden.
MIND_PUNKTE = 12

# Und so viele Wochen Beobachtung nennt der Hinweis als Ziel. Bewusst eine
# runde, ehrliche Hausnummer: es ist die Zeit, in der ein Geraet ueblicherweise
# seine erste Preisstufe nimmt.
MIND_WOCHEN = 12

_FENSTER = (30, 60, 90)

_SICHTBAR = (STATUS_AKTIV, STATUS_VERMUTLICH)


def _datum(wert) -> Optional[date]:
    try:
        return datetime.strptime(str(wert or "").strip(), "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None


# --------------------------------------------------------------------------
# Listungsdauer
# --------------------------------------------------------------------------

def listungsdauer(eintrag: dict) -> Optional[int]:
    """Tage von der ersten bis zur letzten BESTAETIGUNG.

    Bewusst `last_verified` und nicht `ended_since`: die zwei Fehltreffer, die
    die Auslistungslogik braucht, sind kein Portfoliozeitraum. Sonst haette
    jedes ausgelistete Geraet zwei Laufabstaende geschenkt bekommen.
    """
    von, bis = _datum(eintrag.get("first_seen")), _datum(eintrag.get("last_verified"))
    if von is None or bis is None or bis < von:
        return None
    return (bis - von).days


# --------------------------------------------------------------------------
# Preisverfall
# --------------------------------------------------------------------------

def _aktueller_preis(eintrag: dict, art: str) -> Optional[float]:
    feld = "preis_ohne_vertrag" if art == "ohne_vertrag" else "zuzahlung"
    wert = eintrag.get(feld)
    return float(wert) if wert is not None else None


def preisverfall(eintrag: dict) -> Optional[dict]:
    """Heutiger Preis gegen den Einfuehrungspreis, absolut und in Prozent.

    Gerechnet wird ausschliesslich innerhalb EINER Preisart. Ein
    Einfuehrungspreis von 1449 Euro ohne Vertrag gegen eine spaetere
    Zuzahlung von 49,95 Euro ergaebe 96,6 Prozent "Verfall" - die zwei
    Preisarten in einer Rechnung, genau was Teil C4 verbietet.
    """
    erst = eintrag.get("erstpreis")
    art = eintrag.get("erstpreis_art") or "ohne_vertrag"
    if erst in (None, 0):
        return None
    jetzt = _aktueller_preis(eintrag, art)
    if jetzt is None:
        return None
    erst = float(erst)
    return {
        "erstpreis": erst,
        "erstpreis_am": eintrag.get("erstpreis_am", ""),
        "aktuell": jetzt,
        "art": art,
        "absolut": round(jetzt - erst, 2),
        "prozent": round((jetzt - erst) / erst * 100.0, 1),
    }


# --------------------------------------------------------------------------
# Nachfolger-Effekt
# --------------------------------------------------------------------------

def _preis_am(punkte: list, stichtag: date, art: str = "preis_ohne_vertrag") -> Optional[float]:
    """Der zuletzt gemessene Preis AM oder VOR dem Stichtag.

    Eine Treppenfunktion, keine Interpolation: zwischen zwei
    Aenderungspunkten galt der aeltere Preis. Interpoliert waere eine Zahl,
    die nie ausgezeichnet war.
    """
    gueltig = None
    for p in sorted(punkte, key=lambda x: x.get("datum", "")):
        tag = _datum(p.get("datum"))
        if tag is None or tag > stichtag:
            continue
        if p.get(art) is not None:
            gueltig = float(p[art])
    return gueltig


def nachfolger_effekt(device_id: str, katalog: Katalog, punkte: list,
                      heute: Optional[str] = None) -> Optional[dict]:
    """Was der Marktstart des Nachfolgers mit dem Preis des Vorgaengers macht.

    Gibt None, wenn es keinen Nachfolger im Katalog gibt, wenn dessen
    `marktstart` fehlt (ein geratenes Datum waere schlimmer als keines) oder
    wenn wir vor dem Start noch gar nicht gemessen haben.
    """
    nachfolger = katalog.nachfolger_von(device_id)
    if nachfolger is None:
        return None
    start = _datum(nachfolger.marktstart)
    if start is None:
        return None
    eigene = [p for p in punkte if p.get("device_id") == device_id] or punkte
    basis = _preis_am(eigene, start)
    if basis is None or basis == 0:
        return None
    stand = _datum(heute) or date.today()

    nach: dict = {}
    prozent: dict = {}
    for tage in _FENSTER:
        stichtag = start.fromordinal(start.toordinal() + tage)
        if stichtag > stand:
            nach[tage] = None
            prozent[tage] = None
            continue
        wert = _preis_am(eigene, stichtag)
        nach[tage] = wert
        prozent[tage] = round((wert - basis) / basis * 100.0, 1) if wert else None
    return {
        "device_id": device_id,
        "nachfolger": nachfolger.device_id,
        "nachfolger_modell": nachfolger.modell,
        "marktstart": nachfolger.marktstart,
        "basis": basis,
        "nach": nach,
        "prozent": prozent,
    }


# --------------------------------------------------------------------------
# Portfolio-Tiefe
# --------------------------------------------------------------------------

def portfolio_tiefe(eintraege: list, katalog: Katalog) -> list:
    """Wie viele GERAETE-Generationen fuehrt ein Anbieter gleichzeitig?

    Gezaehlt werden verschiedene device_ids, nicht SKUs: acht Farben eines
    Modells sind ein Regalplatz, drei Generationen sind eine Strategie.
    """
    je_anbieter: dict[str, dict] = {}
    for e in eintraege:
        if e.get("status") not in _SICHTBAR:
            continue
        name = e.get("anbieter") or ""
        eintrag = je_anbieter.setdefault(name, {
            "anbieter": name, "anbieter_typ": e.get("anbieter_typ", ""),
            "geraete": set(), "skus": set(), "modelle": []})
        eintrag["geraete"].add(e.get("device_id"))
        eintrag["skus"].add(e.get("sku_id"))

    out = []
    for name, roh in je_anbieter.items():
        modelle = []
        for gid in sorted(roh["geraete"]):
            g = katalog.nach_id(gid)
            modelle.append({
                "device_id": gid,
                "modell": g.modell if g else gid,
                "hersteller": g.hersteller if g else "",
                "generation": g.generation if g else None,
            })
        out.append({
            "anbieter": name,
            "anbieter_typ": roh["anbieter_typ"],
            "generationen": len(roh["geraete"]),
            "skus": len(roh["skus"]),
            "modelle": sorted(modelle, key=lambda m: (m["hersteller"],
                                                      -(m["generation"] or 0))),
        })
    return sorted(out, key=lambda t: (-t["generationen"], t["anbieter"]))


# --------------------------------------------------------------------------
# Die Gesamtauswertung
# --------------------------------------------------------------------------

def auswertung(eintraege: list, punkte: list, katalog: Katalog,
               heute: Optional[str] = None) -> dict:
    """Alles zusammen, mitsamt der Aussage ueber die eigene Datenbasis."""
    stand = _datum(heute) or date.today()
    daten = [d for d in (_datum(p.get("datum")) for p in punkte) if d]
    wochen = max(1, (stand - min(daten)).days // 7) if daten else 0
    duenn = len(punkte) < MIND_PUNKTE

    dauern = []
    for e in eintraege:
        tage = listungsdauer(e)
        if tage is None:
            continue
        g = katalog.nach_id(e.get("device_id"))
        dauern.append({
            "device_id": e.get("device_id"),
            "modell": g.modell if g else e.get("device_id"),
            "anbieter": e.get("anbieter"),
            "tage": tage,
            "status": e.get("status"),
        })

    verfaelle = []
    for e in eintraege:
        v = preisverfall(e)
        if v is None:
            continue
        g = katalog.nach_id(e.get("device_id"))
        verfaelle.append({**v, "device_id": e.get("device_id"),
                          "modell": g.modell if g else e.get("device_id"),
                          "anbieter": e.get("anbieter")})
    verfaelle.sort(key=lambda v: v["prozent"])

    effekte = []
    for gid in sorted({e.get("device_id") for e in eintraege if e.get("device_id")}):
        ergebnis = nachfolger_effekt(gid, katalog, punkte, heute)
        if ergebnis is not None:
            g = katalog.nach_id(gid)
            effekte.append({**ergebnis,
                            "modell": g.modell if g else gid})

    if duenn:
        hinweis = (f"Datenbasis noch dünn: Preisverlauf seit {wochen} "
                   f"{'Woche' if wochen == 1 else 'Wochen'} beobachtet, "
                   f"{len(punkte)} Messpunkte. Belastbare Aussagen über "
                   f"Preisverfall und Nachfolger-Effekt gibt es ab etwa "
                   f"{MIND_WOCHEN} Wochen - bis dahin steht hier, was gemessen "
                   f"wurde, und keine Kurve.")
    else:
        hinweis = (f"Preisverlauf seit {wochen} Wochen beobachtet, "
                   f"{len(punkte)} Messpunkte ueber {len(dauern)} Listungen.")

    return {
        "duenn": duenn,
        "punkte": len(punkte),
        "wochen": wochen,
        "hinweis": hinweis,
        "dauern": sorted(dauern, key=lambda d: -d["tage"]),
        "verfaelle": verfaelle,
        # Ein Trend wird nur ausgewiesen, wenn die Datenbasis ihn traegt.
        # Sonst steht die Messung da, aber nicht die Behauptung.
        "trends": [] if duenn else verfaelle[:12],
        "nachfolger": effekte,
        "portfolio": portfolio_tiefe(eintraege, katalog),
    }
