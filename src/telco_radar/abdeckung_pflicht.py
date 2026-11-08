"""Die Pflichtanbieter des Abdeckungs-Wächters, mit vorbereiteten Quellen.

`config/geraete_abdeckung.yaml` führt `pflicht_anbieter` (immer) und
`pflicht_anbieter_wenn_aktiv` (Quellenname -> Anbieterzeilen): diese gelten
erst, wenn die Quelle in `config/geraete_quellen.yaml` `aktiv: true` trägt.
So ist die Verdrahtung vorbereitet, Aktivschalten bleibt EIN Config-Wert, und
solange die Quelle aus ist, misst der Wächter sie nicht (sonst wäre er rot,
bevor sie das erste Bündel liefert). Fehlt die Quellendatei, gilt nichts davon.
"""

from __future__ import annotations

from pathlib import Path

import yaml


def pflichtanbieter(daten: dict, abdeckung_pfad: Path) -> list[str]:
    """Die festen Pflichtanbieter plus die der aktiven vorbereiteten Quellen."""
    anbieter = list(daten.get("pflicht_anbieter") or [])
    vorbereitet = daten.get("pflicht_anbieter_wenn_aktiv") or {}
    if not vorbereitet:
        return anbieter
    try:
        roh = yaml.safe_load(
            (abdeckung_pfad.parent / "geraete_quellen.yaml").read_text(encoding="utf-8")
        )
    except OSError:
        return anbieter
    aktiv = {
        str(a.get("name") or "").strip()
        for a in (roh or {}).get("anbieter") or []
        if a.get("aktiv", True)
    }
    for quelle, zeilen in vorbereitet.items():
        if str(quelle).strip() in aktiv:
            anbieter += [z for z in zeilen or [] if z not in anbieter]
    return anbieter
