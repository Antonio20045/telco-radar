"""Feldleser für config/geraete_quellen.yaml, aus dem Lader ausgelagert.

`als_zahl` liest eine Zahl. `lese_erfassung` liest das Wegeverzeichnis
(Umbauplan „Eine Methode für alle Anbieter“, Schritt 1): welchen Weg ein Anbieter
heute hat, ohne etwas zu steuern. tests/test_wegeverzeichnis.py hält es gegen die
Adapter-Registry und die Klick-Tagesdatei.
"""

from __future__ import annotations

import logging

log = logging.getLogger(__name__)

ERFASSUNGEN = ("adapter", "klick", "adapter+klick", "barpreis", "aus")
ERFASSUNG_UNBEKANNT = "unbekannt"


def lese_erfassung(eintrag: dict) -> str:
    """Der Weg aus einem Anbietereintrag; fehlt er oder ist er ungültig, gilt
    `unbekannt` und die Zeile meldet sich (Clean Code 4), statt still zu raten."""
    erfassung = str(eintrag.get("erfassung") or "").strip()
    if erfassung in ERFASSUNGEN:
        return erfassung
    log.warning(
        "geraete_quellen: %s hat erfassung=%r - erlaubt sind %s; gefuehrt als %s",
        eintrag.get("name"),
        erfassung or None,
        ", ".join(ERFASSUNGEN),
        ERFASSUNG_UNBEKANNT,
    )
    return ERFASSUNG_UNBEKANNT


def als_zahl(wert, standard: float, anbieter: str, feld: str) -> float:
    """Eine unlesbare Zahl kippt nicht den Loader, sondern faellt auf den
    Standard und meldet sich. Und `0` bleibt `0`: mit `or` waere die
    ausdrueckliche Null still zum Standardwert geworden."""
    if wert is None or str(wert).strip() == "":
        return standard
    try:
        return float(str(wert).replace(",", "."))
    except (TypeError, ValueError):
        log.warning(
            "geraete_quellen: %s hat %s=%r - kein Zahlenwert, es gilt %s",
            anbieter,
            feld,
            wert,
            standard,
        )
        return standard


def lese_sammelbedarf(eintrag: dict, name: str) -> float | None:
    """`sammelbedarf_sekunden` eines Anbieters; `None` heisst unbekannt.

    Die Angabe teilt das Sammelbudget auf (`collect.geraete.sammelbudget`). Eine
    fehlende bleibt `None` und wird dort geschaetzt; eine unlesbare oder nicht
    positive meldet sich und bleibt ebenfalls `None` - eine geratene Null waere
    eine Nullzuteilung (Clean Code 3).
    """
    roh = eintrag.get("sammelbedarf_sekunden")
    if roh is None or str(roh).strip() == "":
        return None
    wert = als_zahl(roh, 0.0, name, "sammelbedarf_sekunden")
    if wert <= 0:
        log.warning(
            "geraete_quellen: %s hat sammelbedarf_sekunden=%r - keine positive "
            "Zahl, der Bedarf wird geschaetzt",
            name,
            roh,
        )
        return None
    return wert
