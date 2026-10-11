"""Redaktionelle Inhalte der KI-Seite (Pitch 9, Schnitt 13).

Die Muster-Prompts stehen in ``content/ki/muster-prompts.json`` neben den
Rechtstexten: eine Liste von [Thema, [[Titel, Text], …]]. Fehlt die Datei oder
bricht ihr Format, kommt ein ``error`` mit Grund zurück und ``anzahl`` ist
None; die Seite nennt den Ausfall, statt den Abschnitt leer zu lassen.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

log = logging.getLogger(__name__)

PROMPTS_DATEI = "content/ki/muster-prompts.json"


class PromptsFormatFehler(ValueError):
    """Die Datei ist lesbar, folgt aber nicht [Thema, [[Titel, Text], …]]."""


def _themen(roh: object) -> list[dict]:
    if not isinstance(roh, list) or not roh:
        raise PromptsFormatFehler("keine Liste von Themen")
    themen = []
    for eintrag in roh:
        if not (isinstance(eintrag, list) and len(eintrag) == 2):
            raise PromptsFormatFehler("Thema ist kein Paar [Name, Prompts]")
        name, prompts = eintrag
        if not isinstance(name, str) or not isinstance(prompts, list) or not prompts:
            raise PromptsFormatFehler(f"Thema {name!r} ohne Prompts")
        if not all(
            isinstance(p, list) and len(p) == 2 and all(isinstance(s, str) for s in p)
            for p in prompts
        ):
            raise PromptsFormatFehler(f"Thema {name!r}: Prompt ist kein [Titel, Text]")
        themen.append(
            {"name": name, "prompts": [{"titel": t, "text": x} for t, x in prompts]}
        )
    return themen


def lade_prompts(root: Path) -> dict:
    """Themen mit Prompts, Gesamtzahl und ``error`` (None, wenn gelesen)."""
    pfad = Path(root) / PROMPTS_DATEI
    try:
        themen = _themen(json.loads(pfad.read_text(encoding="utf-8")))
    except FileNotFoundError:
        grund = f"{PROMPTS_DATEI} fehlt"
    except (OSError, json.JSONDecodeError, PromptsFormatFehler) as fehler:
        grund = f"{PROMPTS_DATEI} unlesbar ({fehler})"
    else:
        anzahl = sum(len(t["prompts"]) for t in themen)
        return {"themen": themen, "anzahl": anzahl, "error": None}
    log.error("Muster-Prompts nicht geladen: %s", grund)
    return {"themen": [], "anzahl": None, "error": grund}
