#!/usr/bin/env python3
"""Bereits veroeffentlichte Berichte mit 0 bewerteten Meldungen heilen (E3B).

`pipeline.run()` traegt seit dem 05.09.2026 selbst dafuer Sorge, dass eine
leere Bewertungsrunde die letzte gueltige Redaktion uebernimmt statt eine
leere Titelseite oder einen Roh-Digest zu veroeffentlichen (siehe
src/telco_radar/analyze/redaktion_kontinuitaet.py). Das greift nur fuer
LAEUFE, die NACH diesem Fix geschrieben werden - Berichte, die schon vorher
mit 0 bewerteten Meldungen im Archiv liegen, bleiben ohne dieses Skript
kaputt, weil kein Lauf sie neu schreibt.

Genau das ist am 04.09.2026 passiert (Lauf 33884961931, siehe
E3B_KONTEXT.md): `data/reports/2026-09-04.json` traegt 0 bewertete
Meldungen und einen unverdichteten Roh-Digest. Dieses Skript wendet
dieselbe Uebernahme-Logik nachtraeglich auf jeden schon vorliegenden
Bericht an, der sie noch nicht hat - ein einmaliger Heilungslauf uebers
Archiv, keine neue Dauerstufe der Pipeline.

`stats` und `run` (das Laufprotokoll) bleiben unangetastet: sie sind die
ehrliche Bilanz DER DAMALIGEN Runde und duerfen es bleiben. Nur `regions`,
`briefing_md` und `competitors` werden ersetzt, und nur, wenn eine gueltige
vorherige Redaktion im Archiv liegt.

    python scripts/heile_ausgefallene_redaktion.py            # Probelauf
    python scripts/heile_ausgefallene_redaktion.py --schreiben
    python scripts/heile_ausgefallene_redaktion.py --schreiben --datum 2026-09-04

Ohne `--datum` findet der Probelauf typischerweise MEHRERE alte Kandidaten
(jede Ausgabe im Archiv, die je mit 0 bewerteten Meldungen geschrieben
wurde). Das heilt jede fuer sich richtig, verlinkt aber ab dann dieselben
Meldungen unter mehreren Archivdaten - fuer die eine akute Reparatur reicht
in aller Regel `--datum <die kaputte Ausgabe>`.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path

_DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from telco_radar.analyze import editor  # noqa: E402
from telco_radar.analyze import redaktion_kontinuitaet as rk  # noqa: E402

# Dieselben zwei Formulierungen wie in pipeline.py - siehe dort fuer die
# Unterscheidung (keine neuen Meldungen vs. eine gescheiterte Bewertung).
_GRUND_KEIN_STOFF = "es gab keine neuen Meldungen zu bewerten"
_GRUND_AUSFALL = "eine vorübergehende Störung des Analyse-Dienstes"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--schreiben", action="store_true",
                     help="Aenderungen wirklich schreiben (sonst Probelauf)")
    ap.add_argument("--reports-dir", type=Path,
                     default=ROOT / "data" / "reports")
    ap.add_argument("--datum", help="nur diese eine Ausgabe pruefen/heilen "
                                    "(YYYY-MM-DD), sonst das ganze Archiv")
    args = ap.parse_args()

    reports_dir: Path = args.reports_dir
    if args.datum:
        kandidaten = [reports_dir / f"{args.datum}.json"]
    else:
        kandidaten = sorted(f for f in reports_dir.glob("*.json")
                            if _DATE_RE.fullmatch(f.stem))

    geheilt = 0
    for pfad in kandidaten:
        report = json.loads(pfad.read_text(encoding="utf-8"))
        if report.get("redaktion_ausfall"):
            continue  # schon geheilt (oder ein spaeterer Lauf hat es selbst getan)
        if rk.bewertete_meldungen(report) > 0:
            continue  # diese Ausgabe hat selbst etwas geliefert

        grund = (_GRUND_AUSFALL if report.get("stats", {}).get("new")
                else _GRUND_KEIN_STOFF)
        regional, body, competitors, ausfall = rk.uebernehmen(
            report.get("regions") or {}, report.get("briefing_md") or "",
            report.get("competitors") or [], reports_dir, report["date"],
            grund)
        if ausfall is None:
            print(f"{pfad.name}: 0 bewertete Meldungen, aber keine gueltige "
                  f"vorherige Redaktion im Archiv - bleibt unveraendert")
            continue

        print(f"{pfad.name}: uebernimmt Stand vom {ausfall['stand']}")
        geheilt += 1
        if not args.schreiben:
            continue

        report["regions"] = regional
        report["briefing_md"] = body
        report["competitors"] = competitors
        report["redaktion_ausfall"] = ausfall
        # Dieselbe ehrliche Zahl, die pipeline.py seit dem 05.09.2026 VOR der
        # Uebernahme in stats.bewertete festhaelt (siehe html.py: n_bewertet
        # auf transparenz.html). Hier ist sie per Vorbedingung 0 - genau das
        # hat den Bericht erst zum Heilungskandidaten gemacht.
        report.setdefault("stats", {})["bewertete"] = 0
        pfad.write_text(json.dumps(report, ensure_ascii=False, indent=1),
                        encoding="utf-8")

        md_pfad = pfad.with_suffix(".md")
        if md_pfad.exists():
            header = editor.report_header(
                date.fromisoformat(report["date"]), report.get("stats", {}))
            md_pfad.write_text(header + body, encoding="utf-8")

    if not args.schreiben and geheilt:
        print(f"\n{geheilt} Bericht(e) wuerden geheilt - mit --schreiben "
              f"wirklich schreiben.")
    elif not geheilt:
        print("Nichts zu heilen.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
