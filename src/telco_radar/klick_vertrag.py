"""Was Klick-Crawler, Analyse und Report über einen Klick-Lauf gemeinsam wissen.

Wurzelmodul ohne Schicht: ``collect.geraete.klicklauf`` und ``klickergebnis``
führen diese Namen weiter, ``analyze.klick_erfassung`` und ``klick_lesestand`` lesen
sie hier, damit der Report ``collect`` nicht einmal mittelbar lädt. Laufstatus
``gelesen`` und ``gestoert``; HTTP 202 (``CHALLENGE_STATUS``) und ab
``FEHLER_AB_STATUS`` stört den Abruf (``abruf_gestoert``). Die Ergebnisdateien liegen
unter ``ORDNER`` im ``FORMAT``; ``lies_ergebnisse`` liest sie, ``ganz_gelesen`` ist
die eine Definition einer heute gelesenen Seite. Fristen ``LESEFRIST_TAGE`` und
``FRISCHEGRENZE_TAGE`` erklärt ``collect.geraete.klickergebnis``.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

log = logging.getLogger(__name__)

LAUF_GELESEN = "gelesen"
LAUF_GESTOERT = "gestoert"
CHALLENGE_STATUS = 202
FEHLER_AB_STATUS = 400
FORMAT = 1
FRISCHEGRENZE_TAGE = 3
LESEFRIST_TAGE = 1
ROTATION_GELESEN = frozenset({LAUF_GELESEN})
ORDNER = Path("data") / "state" / "klick"
STAND_DATEI = "klick_stand.json"


def abruf_gestoert(status: int | None) -> str | None:
    """Grund, wenn der HTTP-Status den Abruf stört (202, 4xx, 5xx), sonst ``None``."""
    if status is None:
        return "Abruf gestört (keine Antwort)"
    if status == CHALLENGE_STATUS or status >= FEHLER_AB_STATUS:
        return f"Abruf gestört (HTTP {status})"
    return None


def ganz_gelesen(seiten: list[dict]) -> list[dict]:
    """Die Seiten, die der Lauf ganz gelesen hat (``ROTATION_GELESEN``)."""
    return [s for s in seiten if s["status"] in ROTATION_GELESEN]


def lies_ergebnisse(ordner: Path) -> tuple[list[dict], list[str]]:
    """Alle Ergebnisdateien unter ``ordner`` und die unlesbaren mit Grund.

    Artefakte liegen je Anbieter in einem Unterordner; gesucht wird darum rekursiv.
    Eine Datei ohne passendes ``format`` ist unlesbar, nicht leer; der Lesestand
    (``STAND_DATEI``) ist keine Ergebnisdatei.
    """
    daten: list[dict] = []
    unlesbar: list[str] = []
    if not ordner.is_dir():
        return daten, [f"{ordner}: kein Ordner"]
    for datei in sorted(ordner.rglob("*.json")):
        if datei.name == STAND_DATEI:
            continue
        try:
            inhalt = json.loads(datei.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as fehler:
            unlesbar.append(f"{datei.name}: {type(fehler).__name__}")
            continue
        if not isinstance(inhalt, dict) or inhalt.get("format") != FORMAT:
            unlesbar.append(f"{datei.name}: Format nicht {FORMAT}")
            continue
        daten.append(inhalt)
    for zeile in unlesbar:
        log.warning("Klick-Ergebnis unlesbar: %s", zeile)
    return daten, unlesbar
