"""Der Erfassungsgrund eines gestörten Klick-Laufs für die Geräteseite.

Grundlage ist der Bilanzeintrag einer Klick-Ergebnisdatei (``klick_zusammenfuehrung``,
``bilanz["dateien"]``). Ein Lauf mit Status ``gestoert``, jünger als
``FRISCHEGRENZE_TAGE``, ergibt je Anbieter einen Satz wie „Telekom nicht erfasst:
Seite sperrt automatisches Lesen (HTTP 202, 08.10.2026)“; Anbieter, HTTP-Status und
Datum stammen aus der Datei. HTTP 202, 4xx oder eine Challenge heißen Sperre, alles
andere Störung. Ein gelesener, veralteter oder datumloser Lauf hat keinen Grund.
"""

from __future__ import annotations

import re
from datetime import date

from ..collect.geraete.klickergebnis import FRISCHEGRENZE_TAGE
from ..collect.geraete.klicklauf import (
    CHALLENGE_STATUS,
    FEHLER_AB_STATUS,
    LAUF_GESTOERT,
)

SATZ = "{anbieter} nicht erfasst: {art} ({angaben})"
ART_SPERRE = "Seite sperrt automatisches Lesen"
ART_STOERUNG = "Lesen gestört"
SERVERFEHLER_AB = 500
CHALLENGE = "Challenge"
_HTTP = re.compile(r"HTTP (\d{3})")


def erfassungsgrund(eintrag: dict) -> str | None:
    """Der Satz zu einem Bilanzeintrag, ``None`` ohne frische Störung."""
    alter = eintrag.get("alter_tage")
    if eintrag.get("laufstatus") != LAUF_GESTOERT or alter is None:
        return None
    if not 0 <= alter < FRISCHEGRENZE_TAGE:
        return None
    grund = str(eintrag.get("grund") or "")
    treffer = _HTTP.search(grund)
    status = int(treffer[1]) if treffer else None
    gesperrt = status == CHALLENGE_STATUS or (
        status is not None and FEHLER_AB_STATUS <= status < SERVERFEHLER_AB
    )
    datum = date.fromisoformat(str(eintrag.get("datum"))).strftime("%d.%m.%Y")
    angaben = datum if status is None else f"HTTP {status}, {datum}"
    return SATZ.format(
        anbieter=eintrag.get("anbieter"),
        art=ART_SPERRE if gesperrt or CHALLENGE in grund else ART_STOERUNG,
        angaben=angaben,
    )


def erfassungsgruende(bilanz: dict | None) -> dict[str, str]:
    """Je Anbieter mit frisch gestörtem Klick-Lauf sein Erfassungsgrund."""
    gruende = {}
    for eintrag in (bilanz or {}).get("dateien", []):
        if (satz := erfassungsgrund(eintrag)) is not None:
            gruende[str(eintrag.get("anbieter"))] = satz
    return gruende


def ohne_karte(gruende: dict[str, str], karten: list[dict]) -> dict[str, str]:
    """Die Gründe der Anbieter ohne Karte mit Betrag im Modell: wer die Seite gelesen
    hat, zeigt seine Zeile statt des Grundes; ein Platzhalter zählt nicht."""
    mit_karte = {k.get("anbieter") for k in karten if k.get("gesamt") is not None}
    return {a: satz for a, satz in gruende.items() if a not in mit_karte}
