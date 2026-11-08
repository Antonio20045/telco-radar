"""Stammdaten der Tarifwelt-Tarife (Saturn/MediaMarkt) fuer die Band-Zuordnung.

Die Tarife dieser Quelle (`tarif_id` "mediamarkt_tarifwelt:<id>") stehen nicht
in `data/state/tarife.jsonl`: das ist der Bestand der Netzbetreiber-Crawler und
speist auch die Tarifseite, auf der ein Handelstarif nichts zu suchen hat. Ohne
Datenvolumen ordnet der Bericht einem Satz aber kein Tarifband zu. Dieser
kleine Bestand `data/state/tarifwelt_tarife.json` schliesst die Luecke: der
Tageslauf schreibt ihn, der Bericht legt ihn neben den Tarifbestand und
bestimmt das Band mit DERSELBEN Regel wie bei jedem anderen Tarif
(`report.geraete_tco_band.tarif_baender`, `band_regel.stufe_fuer`).

Wurzelmodul: importiert keine Schicht, damit Sammeln und Bericht es teilen.
"""

from __future__ import annotations

import json
from pathlib import Path

DATEINAME = "tarifwelt_tarife.json"
PRAEFIX = "mediamarkt_tarifwelt:"


def lade(pfad: Path) -> dict[str, dict]:
    """tarif_id -> Stammdaten; eine fehlende oder kaputte Datei ist leer."""
    try:
        roh = json.loads(Path(pfad).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    tarife = roh.get("tarife") if isinstance(roh, dict) else None
    if not isinstance(tarife, dict):
        return {}
    return {
        tid: satz
        for tid, satz in tarife.items()
        if tid.startswith(PRAEFIX) and isinstance(satz, dict)
    }


def schreibe(pfad: Path, neu: dict[str, dict], heute: str) -> int:
    """Die Tarife des Laufs auf den bisherigen Bestand legen (ein frueher
    gemessenes Buendel behaelt sein Band); gibt die Zahl der Tarife zurueck."""
    bestand = lade(pfad)
    bestand.update(neu)
    ordnung = dict(sorted(bestand.items()))
    Path(pfad).write_text(
        json.dumps({"updated": heute, "tarife": ordnung}, ensure_ascii=False, indent=1)
        + "\n",
        encoding="utf-8",
    )
    return len(ordnung)


def mit_tarifwelt(tarife: dict | None, zustand: Path) -> dict:
    """Der Tarifbestand der Netzbetreiber PLUS die Tarifwelt-Tarife. Die
    Schluessel sind getrennt (Praefix); ein Netzbetreiber-Tarif wird nie
    ueberschrieben."""
    zusatz = lade(Path(zustand) / DATEINAME)
    return {**zusatz, **(tarife or {})} if zusatz else dict(tarife or {})
