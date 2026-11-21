"""Die Lauf-Datei des Gerätelaufs: ``data/state/geraete_lauf/<datum>.json``.

Bis zum 21.11.2026 gab ``run_geraete_stage`` seine Bilanz nur ins Log; ``main()`` warf
sie weg. Jetzt schreibt der Nachtlauf (``geraete_nachtlauf``) je Messtag eine Datei:
``format``, ``datum``, ``bilanz`` (das Dict der Stufe) und ``vollstaendigkeit``
(``geraete_vollstaendigkeit.baue``). Seite und Wächter lesen sie nur.

Rein, ohne Netz; die Seite darf dieses Modul importieren (Vertrag report-rechnet-nur:
kein Store, kein ``collect``). Eine fehlende Datei ist ``None`` (die Seite nennt den
Ausfall), eine unlesbare wirft ``LaufDateiFehler`` - nicht gelesen ist nicht leer.
"""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path

ORDNER = "geraete_lauf"
FORMAT = 1


class LaufDateiFehler(ValueError):
    """Die Lauf-Datei ist da, aber nicht lesbar oder hat ein fremdes Format."""


def pfad(state_dir: Path, datum: str) -> Path:
    """Die Datei des Messtags ``datum`` (ISO)."""
    return Path(state_dir) / ORDNER / f"{datum}.json"


def _json_wert(wert: object) -> object:
    if dataclasses.is_dataclass(wert) and not isinstance(wert, type):
        return dataclasses.asdict(wert)
    if isinstance(wert, (set, frozenset, tuple)):
        return sorted(wert, key=str)
    raise TypeError(f"nicht als JSON schreibbar: {type(wert).__name__}")


def schreibe(state_dir: Path, datum: str, inhalt: dict) -> Path:
    """Schreibt die Datei des Messtags vollständig neu (``format`` wird gesetzt)."""
    ziel = pfad(state_dir, datum)
    ziel.parent.mkdir(parents=True, exist_ok=True)
    daten = {"format": FORMAT, "datum": datum, **inhalt}
    text = json.dumps(daten, ensure_ascii=False, indent=1, default=_json_wert)
    zwischen = ziel.with_suffix(".json.neu")
    zwischen.write_text(text + "\n", encoding="utf-8")
    zwischen.replace(ziel)
    return ziel


def lies(state_dir: Path, datum: str) -> dict | None:
    """Die Datei des Messtags; ``None``, wenn es keine gibt."""
    ziel = pfad(state_dir, datum)
    try:
        daten = json.loads(ziel.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (OSError, ValueError) as fehler:
        raise LaufDateiFehler(f"{ziel.name}: {fehler}") from fehler
    if not isinstance(daten, dict) or daten.get("format") != FORMAT:
        raise LaufDateiFehler(f"{ziel.name}: unbekanntes Format")
    return daten


def juengster_tag(state_dir: Path) -> str | None:
    """Der jüngste Messtag mit Lauf-Datei; ``None`` ohne jede Datei."""
    tage = sorted(p.stem for p in (Path(state_dir) / ORDNER).glob("*.json"))
    return tage[-1] if tage else None
