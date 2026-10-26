"""Ablage der Bündel-Preishistorie: Altdatei plus eine Datei je Messtag.

Bis 25.10.2026 wuchs alles in `data/state/geraete_tco_historie.jsonl`
(rund 5 MB je Messtag). Ab 100 MB lehnt GitHub jeden Push ab; vom 21. bis
25.10. ging deshalb kein Messtag und keine Seite mehr hinaus. Die Altdatei
bleibt seitdem unverändert stehen (nie kürzen), neue Messtage landen in
`data/state/geraete_tco_historie/<datum>.jsonl`. Gelesen wird beides, die
Altdatei zuerst, danach die Tagesdateien in Datumsfolge.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

log = logging.getLogger(__name__)

ALTDATEI = "geraete_tco_historie.jsonl"
ORDNER = "geraete_tco_historie"


def ordner(altdatei: Path) -> Path:
    """Der Ordner der Tagesdateien neben der Altdatei."""
    altdatei = Path(altdatei)
    return altdatei.parent / altdatei.name.removesuffix(".jsonl")


def tagesdatei(altdatei: Path, datum: str) -> Path:
    """Die Datei des Messtags ``datum``."""
    return ordner(altdatei) / f"{datum}.jsonl"


def dateien(altdatei: Path) -> list[Path]:
    """Alle vorhandenen Historiendateien in Lesefolge."""
    altdatei = Path(altdatei)
    out = [altdatei] if altdatei.is_file() else []
    tage = ordner(altdatei)
    if tage.is_dir():
        out.extend(sorted(tage.glob("*.jsonl")))
    return out


def vorhanden(altdatei: Path) -> bool:
    """Ob es überhaupt eine Historiendatei gibt."""
    return bool(dateien(altdatei))


def zeilen(altdatei: Path) -> list[str]:
    """Die Rohzeilen aller Historiendateien; OSError geht an den Aufrufer."""
    out: list[str] = []
    for pfad in dateien(altdatei):
        out.extend(pfad.read_text(encoding="utf-8").splitlines())
    return out


def schreibe_tag(altdatei: Path, datum: str, saetze: list[dict]) -> bool:
    """Fügt ``saetze`` in die Tagesdatei ein; (id, datum) ersetzt, nie doppelt.

    Eine unlesbare Tagesdatei wird nicht angefasst (False, protokolliert):
    das Zusammenfügen ersetzte sonst den Rest des Tages durch nur-neue Zeilen.
    Ein Schreibfehler wirft.
    """
    pfad = tagesdatei(altdatei, datum)
    zusammen: dict[tuple[str, str], dict] = {}
    if pfad.exists():
        try:
            text = pfad.read_text(encoding="utf-8")
            alt = [json.loads(z) for z in text.splitlines() if z.strip()]
        except (json.JSONDecodeError, OSError) as exc:
            log.warning("%s unlesbar (%s) - Historie NICHT angefasst", pfad.name, exc)
            return False
        if any(
            not isinstance(satz, dict)
            or not (satz.get("id") or "").strip()
            or not (satz.get("datum") or "").strip()
            for satz in alt
        ):
            log.warning("%s: Zeilen ohne (id, datum) - NICHT angefasst", pfad.name)
            return False
        for satz in alt:
            zusammen[(satz["id"], satz["datum"])] = satz
    for satz in saetze:
        zusammen[(satz["id"], satz["datum"])] = satz
    pfad.parent.mkdir(parents=True, exist_ok=True)
    pfad.write_text(
        "".join(json.dumps(s, ensure_ascii=False) + "\n" for s in zusammen.values()),
        encoding="utf-8",
    )
    return True
