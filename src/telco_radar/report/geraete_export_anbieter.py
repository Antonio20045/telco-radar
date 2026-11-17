"""`tco_anbieter`: je Anbieter die Zeilenzahl des Kosten-Exports, davon mit
Gesamtpreis - neben `schreibe_exporte`/`leer`, ohne `geraete_export.py` über
seine Dateigrenze zu heben (dieselbe Lehre wie bei `geraete_regel11` zu
`geraete_regeln`: ein eigenes Modul statt einer wachsenden Datei).

Clean Code 1: EINE Stelle, an der diese Zahl entsteht - sonst zählt jede
Abnahme sie von Hand aus der CSV neu und hält dabei leicht zwei verschiedene
Regeln (Tagesdatei, Exportansicht) für vergleichbar (Befund 17.11.2026,
arbeit/ursache-rueckgang-1717.md: „Telekom 1069 → 503“ verglich beide).

Html.py ruft `schreibe_exporte`/`leer` über diesen Namen statt direkt aus
`geraete_export` auf - der EINE Umweg, der die Zahl daneben schreibt, ohne
den Rest des Moduls zu berühren.
"""

from __future__ import annotations

from pathlib import Path

from . import geraete_export
from .geraete_laufzeit import LAUFZEIT_STANDARD, export_je_laufzeit


def je_anbieter(tco: dict) -> list[dict]:
    """Je Anbieter die Zeilenzahl von `geraete-tco-24.csv` und, wie viele davon
    einen Gesamtpreis tragen (`tco24` gesetzt, wie `tco_csv` ihn in die
    Spalte „Kosten über …“ schreibt).

    Dieselbe Menge wie der danebenstehende Knopf „Kosten mit Tarif 24
    Monate“: beide gehen über `export_je_laufzeit` auf dieselbe
    Standard-Ansicht (Clean Code 1, keine zweite Zählregel), samt der
    SIM-only-Zeilen, die `tco_csv` dort mitschreibt."""
    zeilen = export_je_laufzeit(tco or {}).get(LAUFZEIT_STANDARD, {})
    zaehler: dict[str, dict] = {}
    for z in [*zeilen.get("buendel", []), *zeilen.get("sim_only", [])]:
        anbieter = z.get("anbieter") or ""
        eintrag = zaehler.setdefault(
            anbieter, {"anbieter": anbieter, "zeilen": 0, "mit_gesamtpreis": 0}
        )
        eintrag["zeilen"] += 1
        if z.get("tco24") is not None:
            eintrag["mit_gesamtpreis"] += 1
    return sorted(zaehler.values(), key=lambda e: e["anbieter"])


def schreibe_exporte(
    site_dir: Path,
    eintraege: list,
    punkte: list,
    katalog,
    stand: str = "",
    tco: dict | None = None,
    radar: dict | None = None,
    modelle: list | None = None,
) -> dict:
    """Wie `geraete_export.schreibe_exporte`, samt `tco_anbieter` daneben."""
    ergebnis = geraete_export.schreibe_exporte(
        site_dir, eintraege, punkte, katalog, stand, tco, radar, modelle
    )
    ergebnis["tco_anbieter"] = je_anbieter(tco or {})
    return ergebnis


def leer() -> dict:
    """Wie `geraete_export.leer`, samt leerem `tco_anbieter`."""
    ergebnis = geraete_export.leer()
    ergebnis["tco_anbieter"] = []
    return ergebnis
