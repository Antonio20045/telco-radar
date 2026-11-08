"""Die Pflichtanbieter des Abdeckungs-Wächters, mit vorbereiteten Quellen.

`config/geraete_abdeckung.yaml` führt `pflicht_anbieter` (immer) und
`pflicht_anbieter_wenn_aktiv` (Quellenname -> Anbieterzeilen): diese gelten
erst, wenn die Quelle in `config/geraete_quellen.yaml` `aktiv: true` trägt.
So ist die Verdrahtung vorbereitet, Aktivschalten bleibt EIN Config-Wert, und
solange die Quelle aus ist, misst der Wächter sie nicht (sonst wäre er rot,
bevor sie das erste Bündel liefert). Fehlt die Quellendatei, gilt nichts davon.

`pflicht_modelle_wenn_aktiv` (Quellenname -> Modelle) legt für die Zeilen einer
solchen Quelle fest, welche Pflichtmodelle der Wächter prüft: nur die, die der
Leser der Quelle tatsächlich erfasst. Das gilt ausschließlich für vorbereitete
Quellen; ein Pflichtanbieter aus `pflicht_anbieter` (die Netzbetreiber) wird immer
gegen ALLE `pflicht_modelle` geprüft, die Liste kann dort nichts lockern. Eine
Modell-Liste ohne vorbereitete Quelle oder mit einem Modell außerhalb von
`pflicht_modelle` ist ein Konfigurationsfehler (ValueError), kein stilles Weglassen.
"""

from __future__ import annotations

from pathlib import Path

import yaml


def _aktive_quellen(abdeckung_pfad: Path) -> set[str] | None:
    """Namen der Quellen mit `aktiv: true`; `None`, wenn die Quellendatei fehlt."""
    try:
        roh = yaml.safe_load(
            (abdeckung_pfad.parent / "geraete_quellen.yaml").read_text(encoding="utf-8")
        )
    except OSError:
        return None
    return {
        str(a.get("name") or "").strip()
        for a in (roh or {}).get("anbieter") or []
        if a.get("aktiv", True)
    }


def pflichtanbieter(daten: dict, abdeckung_pfad: Path) -> list[str]:
    """Die festen Pflichtanbieter plus die der aktiven vorbereiteten Quellen."""
    anbieter = list(daten.get("pflicht_anbieter") or [])
    vorbereitet = daten.get("pflicht_anbieter_wenn_aktiv") or {}
    if not vorbereitet:
        return anbieter
    aktiv = _aktive_quellen(abdeckung_pfad)
    if aktiv is None:
        return anbieter
    for quelle, zeilen in vorbereitet.items():
        if str(quelle).strip() in aktiv:
            anbieter += [z for z in zeilen or [] if z not in anbieter]
    return anbieter


def pflichtmodelle_je_anbieter(
    daten: dict, abdeckung_pfad: Path
) -> dict[str, list[str]]:
    """Anbieterzeile -> die Pflichtmodelle, die für sie gelten (nur Zeilen aktiver
    vorbereiteter Quellen mit eigener Liste; alle anderen gelten für
    `pflicht_modelle`). Ungültige Angaben: ValueError, auch bei inaktiver Quelle."""
    je_quelle = daten.get("pflicht_modelle_wenn_aktiv") or {}
    if not je_quelle:
        return {}
    vorbereitet = daten.get("pflicht_anbieter_wenn_aktiv") or {}
    alle = set(daten.get("pflicht_modelle") or [])
    for quelle, modelle in je_quelle.items():
        if quelle not in vorbereitet:
            raise ValueError(
                f"pflicht_modelle_wenn_aktiv: '{quelle}' steht nicht in "
                "pflicht_anbieter_wenn_aktiv (nur vorbereitete Quellen, "
                "nie die Netzbetreiber)"
            )
        fremd = sorted(set(modelle or []) - alle)
        if fremd or not modelle:
            raise ValueError(
                f"pflicht_modelle_wenn_aktiv '{quelle}': leer oder Modelle außerhalb "
                f"von pflicht_modelle: {fremd}"
            )
    aktiv = _aktive_quellen(abdeckung_pfad)
    if not aktiv:
        return {}
    return {
        zeile: list(modelle)
        for quelle, modelle in je_quelle.items()
        if str(quelle).strip() in aktiv
        for zeile in vorbereitet[quelle] or []
    }


def modelle_fuer(pflicht: dict, anbieter: str) -> list[str]:
    """Die Pflichtmodelle EINES Anbieters: seine eigene Liste (nur Händlerzeilen
    vorbereiteter Quellen, `pflichtmodelle_je_anbieter`), sonst alle."""
    return (pflicht.get("modelle_je_anbieter") or {}).get(anbieter, pflicht["modelle"])
