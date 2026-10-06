"""Kennzahlen der Prüfstelle je Anbieter und Lauf, für die Quellen-Seite.

Gezählt wird beim Prüfen (``geraete_pruefstelle.vermerke``) aus den vollen Befunden
jedes Bündels; keine Regel wird hier ein zweites Mal geprüft. Der Lauf-Eintrag steht
als ``pruefung`` in ``geraete_tco.json``, die Quellen-Seite liest ihn über
``aufbereiten``. Je Anbieter:

    Abdeckung je Laufzeit  gültige Bündel je Ratenlaufzeit (6, 12, 24, 36); ohne ein
                           einziges Bündel dieser Laufzeit ist sie nicht erfasst
    Frische                Anteil der Bündel, die Regel 16 bestehen
    Quarantänequote        Anteil der Bündel im Status Quarantäne
    Konfliktquote          Anteil mit Widerspruch zwischen Text und Antwort (Regel 9)
    Belegquote             Anteil, dessen Beleglink die Variante zeigt (Regel 13)

Eine Quote zählt nur Bündel, an denen ihre Regel prüfbar war; „nicht prüfbar“ steht
daneben, und ohne ein prüfbares Bündel ist ihr Prozentwert None, nie 0. ``ohne_daten``
nennt die Regeln, die an keinem Bündel des Anbieters prüfbar waren; die Zeilen je Regel
zählen „nicht prüfbar“ über alle Bündel. Bündel ohne Feld sind nie geprüft worden,
Bündel mit Status ``unbekannt`` sind an einer gescheiterten Prüfung hängen geblieben;
beide stehen getrennt und in keiner Quote.
"""

from __future__ import annotations

import json
import logging
from collections import Counter
from collections.abc import Iterable, Mapping
from pathlib import Path

from .geraete_pruefstatus import (
    ERLAUBTE_RATENLAUFZEITEN,
    GUELTIG,
    QUARANTAENE,
    REGELN,
    STATUS,
    UNBEKANNT,
    VERALTET,
    status_aus_feld,
)
from .geraete_regeln import erfassungsluecken

log = logging.getLogger(__name__)

ALLE = "Alle"
DATEI = "geraete_tco.json"


def aufbereiten(state_dir: Path) -> dict:
    """Die Kennzahlen des letzten Gerätelaufs für die Quellen-Seite.

    Liest den Lauf-Eintrag ``pruefung`` aus ``geraete_tco.json`` (``vermerke``).
    ``vorhanden`` ist falsch, solange kein Gerätelauf geprüft hat. Eine unlesbare
    Datei oder ein Lauf ohne Kennzahlen ist ein Ausfall und steht als ``fehler`` auf
    der Seite.
    """
    pfad = Path(state_dir) / DATEI
    leer = {"vorhanden": False, "fehler": "", "lauf": ""}
    if not pfad.exists():
        return leer
    try:
        roh = json.loads(pfad.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        log.error("Prüfkennzahlen: %s unlesbar: %s", DATEI, exc)
        return {**leer, "fehler": f"{DATEI} unlesbar: {exc}"}
    lauf = roh.get("pruefung") if isinstance(roh, dict) else None
    if not isinstance(lauf, dict):
        return leer
    if "summe" not in lauf:
        fehler = str(lauf.get("fehler") or "Kennzahlen fehlen")
        return {**leer, "lauf": str(lauf.get("lauf") or ""), "fehler": fehler}
    return {**lauf, "vorhanden": True, "fehler": ""}


def quote(zahl: int, von: int, nicht_pruefbar: int = 0) -> dict:
    """``zahl`` von ``von`` als ganze Prozent; ohne Nenner None, nie 0."""
    prozent = round(100 * zahl / von) if von else None
    return {
        "zahl": zahl,
        "von": von,
        "prozent": prozent,
        "nicht_pruefbar": nicht_pruefbar,
    }


def kennzahlen(saetze: Iterable[Mapping], felder: Mapping[str, Mapping]) -> dict:
    """Je Anbieter eine Zeile, dazu die Summe über alle und eine Zeile je Regel.

    ``felder`` ordnet jeder Bündel-ID ihr Feld aus ``Pruefergebnis.als_feld`` oder
    ``fehlerfeld`` zu; ein Satz ohne Feld ist nie geprüft worden.
    """
    alle = [(s, felder.get(str(s.get("id") or ""))) for s in saetze]
    je_anbieter: dict[str, list[tuple[Mapping, Mapping | None]]] = {}
    for satz, feld in alle:
        je_anbieter.setdefault(str(satz.get("anbieter") or ""), []).append((satz, feld))
    luecken = erfassungsluecken(s for s, _ in alle)
    return {
        "anbieter": [
            _zeile(name, liste, luecken.get(name, []))
            for name, liste in sorted(je_anbieter.items())
        ],
        "summe": _zeile(ALLE, alle, [s for t in luecken.values() for s in t]),
        "regeln": _regeln([f for _, f in alle], luecken),
        "laufzeiten": list(ERLAUBTE_RATENLAUFZEITEN),
    }


def _zeile(
    name: str, paare: list[tuple[Mapping, Mapping | None]], luecken: list[str]
) -> dict:
    felder = [f for _, f in paare]
    status = Counter(status_aus_feld(f) for f in felder)
    geprueft = _gepruefte(felder)
    n = len(geprueft)
    fehler = (f.get("fehler") for f in felder if isinstance(f, Mapping))
    verletzt, nicht = _je_regel(geprueft)
    gueltig_je = Counter(
        s.get("laufzeit_monate") for s, f in paare if status_aus_feld(f) == GUELTIG
    )
    gesamt_je = Counter(s.get("laufzeit_monate") for s, _ in paare)
    return {
        "name": name,
        "buendel": len(paare),
        "geprueft": n,
        "nie_geprueft": status[None],
        "gescheitert": status[UNBEKANNT],
        "fehler": next((str(f) for f in fehler if f), ""),
        "gueltig": status[GUELTIG],
        "quarantaene": status[QUARANTAENE],
        "veraltet": status[VERALTET],
        "abdeckung": [
            {"monate": m, "gueltig": gueltig_je[m], "erfasst": gesamt_je[m] > 0}
            for m in ERLAUBTE_RATENLAUFZEITEN
        ],
        "frische": quote(n - nicht[16] - verletzt[16], n - nicht[16], nicht[16]),
        "quarantaenequote": quote(status[QUARANTAENE], n),
        "konfliktquote": quote(verletzt[9], n - nicht[9], nicht[9]),
        "belegquote": quote(n - nicht[13] - verletzt[13], n - nicht[13], nicht[13]),
        "ohne_daten": [r for r in REGELN if n and nicht[r] == n],
        "erfassungsluecken": luecken,
    }


def _regeln(felder: list[Mapping | None], luecken: Mapping[str, list[str]]) -> list:
    geprueft = _gepruefte(felder)
    verletzt, nicht = _je_regel(geprueft)
    lueckenzahl = Counter(r for f in geprueft for r in set(f.get("luecken") or []))
    lueckenzahl[12] = sum(len(t) for t in luecken.values())
    return [
        {
            "nr": nr,
            "name": name,
            "verletzt": verletzt[nr],
            "luecke": lueckenzahl[nr],
            "nicht_pruefbar": nicht[nr],
        }
        for nr, name in REGELN.items()
    ]


def _gepruefte(felder: Iterable[Mapping | None]) -> list[Mapping]:
    """Die Felder mit einem der drei Status."""
    return [
        f for f in felder if isinstance(f, Mapping) and status_aus_feld(f) in STATUS
    ]


def _je_regel(geprueft: list[Mapping]) -> tuple[Counter[int], Counter[int]]:
    """Je Regelnummer: an wie vielen Bündeln verletzt, an wie vielen nicht prüfbar."""
    verletzt = Counter(
        r for f in geprueft for r in {g.get("regel") for g in f.get("gruende") or []}
    )
    nicht = Counter(r for f in geprueft for r in set(f.get("nicht_pruefbar") or []))
    return verletzt, nicht
