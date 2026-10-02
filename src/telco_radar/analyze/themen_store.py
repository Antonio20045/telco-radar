"""Der Speicher der temporaeren Themen (`highlight_topics.json`).

Lesen und Schreiben ohne LLM-Import, damit `report/` die aktiven Themen
laden kann, ohne an den Analyseweg zu haengen.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

log = logging.getLogger(__name__)

STORE_NAME = "highlight_topics.json"


def store_pfad(state_dir: Path) -> Path:
    return Path(state_dir) / STORE_NAME


def lade_store(state_dir: Path) -> dict:
    """Der Themenspeicher. Fehlt oder bricht er, faengt der Lauf bei null an -
    ein unlesbarer Speicher darf nie den Lauf kippen."""
    pfad = store_pfad(state_dir)
    if not pfad.exists():
        return {"updated": "", "topics": []}
    try:
        daten = json.loads(pfad.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        log.warning("%s unlesbar - beginne mit leerem Themenspeicher", pfad)
        return {"updated": "", "topics": []}
    if not isinstance(daten, dict) or not isinstance(daten.get("topics"), list):
        return {"updated": "", "topics": []}
    return daten


def speichere_store(state_dir: Path, store: dict) -> None:
    pfad = store_pfad(state_dir)
    pfad.parent.mkdir(parents=True, exist_ok=True)
    pfad.write_text(json.dumps(store, ensure_ascii=False, indent=1), encoding="utf-8")


def aktive_themen(store: dict) -> list[dict]:
    """Die Themen, die eine Seite bekommen - neueste Aktivitaet zuerst."""
    aktiv = [
        t
        for t in (store.get("topics") or [])
        if t.get("status") == "aktiv" and t.get("items")
    ]
    return sorted(
        aktiv,
        key=lambda t: (t.get("last_active") or "", len(t.get("items") or [])),
        reverse=True,
    )


def lade_themen(state_dir: Path) -> list[dict]:
    """Die aktiven Themen zum Rendern. Einziger Einstieg fuer report/."""
    return aktive_themen(lade_store(state_dir))
