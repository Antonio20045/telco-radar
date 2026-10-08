"""Lesestand des Klick-Crawlers je Anbieter für ``geraete-quellen.html`` (Schnitt 5).

Aus jeder Ergebnisdatei des Klick-Tageslaufs (``klickergebnis.lies_ergebnisse``) eine
Zeile „Crawler heute: N von M Seiten gelesen (TT.MM.JJJJ)“: N sind die ganz gelesenen
Seiten (``klickergebnis.ganz_gelesen``, dieselbe Definition wie die Rotation), M alle
Seiten der Datei, das Datum ist das des Laufs. Eine unlesbare Datei steht als
benannte Lücke da, nicht als fehlende Zeile. Ohne Ordner gibt es keinen Klick-Lauf
und keine Zeile. Hier wird die Zahl gerechnet; die Vorlage zeigt nur den Satz.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from ..klick_vertrag import ORDNER, ganz_gelesen, lies_ergebnisse

SATZ = "Crawler heute: {n} von {m} Seiten gelesen ({datum})"
SATZ_UNLESBAR = "Crawler-Ergebnis unlesbar: {grund}"


def zeile(daten: dict) -> dict:
    """Eine Zeile aus einer Ergebnisdatei; ein ungültiges Datum heißt ``ValueError``."""
    seiten = daten.get("seiten") or []
    gelesen = len(ganz_gelesen(seiten))
    datum = date.fromisoformat(str(daten.get("datum"))).strftime("%d.%m.%Y")
    return {
        "anbieter": daten.get("anbieter"),
        "name": daten.get("name") or daten.get("anbieter"),
        "gelesen": gelesen,
        "seiten": len(seiten),
        "datum": datum,
        "satz": SATZ.format(n=gelesen, m=len(seiten), datum=datum),
    }


def lesestand(state_dir: Path) -> dict:
    """Zeilen je Anbieter und unlesbare Dateien unter ``state_dir/klick``."""
    ordner = Path(state_dir) / ORDNER.name
    if not ordner.is_dir():
        return {"zeilen": [], "unlesbar": []}
    dateien, unlesbar = lies_ergebnisse(ordner)
    zeilen = []
    for daten in dateien:
        try:
            zeilen.append(zeile(daten))
        except (TypeError, ValueError) as fehler:
            unlesbar.append(f"{daten.get('anbieter')}: Datum {fehler}")
    return {
        "zeilen": sorted(zeilen, key=lambda z: str(z["name"]).casefold()),
        "unlesbar": [SATZ_UNLESBAR.format(grund=g) for g in unlesbar],
    }


def mit_klick(quellenlage: dict, state_dir: Path) -> dict:
    """Die Quellenlage samt Lesestand des Klick-Crawlers unter ``klick``."""
    return {**quellenlage, "klick": lesestand(state_dir)}
