#!/usr/bin/env python3
"""Bilder fuer einen bereits erzeugten Bericht nachholen und einstempeln.

Die Bildbeschaffung ist eine Stufe der Pipeline und laeuft dort automatisch
mit. Dieses Skript ist der Weg, sie NACHTRAEGLICH auf eine fertige Ausgabe
anzuwenden - ohne Sammelphase, ohne LLM, ohne den Seen-Store anzufassen.
Gebraucht wurde es am 06.08.2026: der Bericht dieses Tages war fertig, aber
mit dem alten Deckel entstanden (40 statt 193 versuchte Meldungen).

    python scripts/bilder_nachholen.py                 # neuester Bericht
    python scripts/bilder_nachholen.py 2026-08-06
    python scripts/bilder_nachholen.py --trocken       # nur messen

Schreibt `image`, `image_w` und `image_h` in die Berichtsdatei zurueck. Die
Masse gehoeren mit hinein: die Titelseite entscheidet anhand der BREITE, ob
eine Meldung gross stehen darf, und ein Renderlauf soll dafuer nicht 190
Dateien oeffnen muessen.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from telco_radar.report import bilder as report_bilder  # noqa: E402

_DATUM = re.compile(r"\d{4}-\d{2}-\d{2}")


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("datum", nargs="?", help="Berichtsdatum (Vorgabe: neuester)")
    p.add_argument("--root", default=".", help="Projektwurzel")
    p.add_argument("--trocken", action="store_true",
                   help="nur messen, Bericht nicht zurueckschreiben")
    args = p.parse_args()

    root = Path(args.root).resolve()
    reports = root / "data" / "reports"
    if args.datum:
        pfad = reports / f"{args.datum}.json"
    else:
        kandidaten = sorted(f for f in reports.glob("*.json")
                            if _DATUM.fullmatch(f.stem))
        if not kandidaten:
            print("Kein Bericht gefunden.", file=sys.stderr)
            return 1
        pfad = kandidaten[-1]
    if not pfad.exists():
        print(f"Nicht gefunden: {pfad}", file=sys.stderr)
        return 1

    bericht = json.loads(pfad.read_text(encoding="utf-8"))
    highlights = [h for r in (bericht.get("regions") or {}).values()
                  for h in r.get("highlights") or []]
    vorher = sum(1 for h in highlights if h.get("image"))
    print(f"{pfad.name}: {len(highlights)} Meldungen, {vorher} mit Bild")

    t0 = time.monotonic()
    bilanz = report_bilder.hole_bilder(highlights, root)
    dauer = time.monotonic() - t0

    nachher = sum(1 for h in highlights if h.get("image"))
    print(f"\nDauer: {dauer:.1f}s")
    for k in sorted(bilanz):
        print(f"  {k:18s} {bilanz[k]}")
    print(f"\n{nachher} von {len(highlights)} Meldungen mit Bild "
          f"({100 * nachher / max(1, len(highlights)):.0f} %)")

    if args.trocken:
        print("\n--trocken: Bericht nicht geaendert.")
        return 0

    # Das Laufprotokoll muss mitziehen. Sonst steht auf transparenz.html
    # weiter "31 von 40 Meldungen mit Bild", waehrend die Seite 147 zeigt -
    # genau die Sorte Zahl, die dieses Projekt nicht dulden darf.
    phasen = ((bericht.get("run") or {}).get("phases")) or []
    for phase in phasen:
        if phase.get("name") == "Bilder":
            phase["seconds"] = round(dauer, 1)
            phase["detail"] = (f"{nachher} von {len(highlights)} Meldungen "
                               f"mit Bild (nachtraeglich beschafft)")
            break

    pfad.write_text(json.dumps(bericht, ensure_ascii=False, indent=2),
                    encoding="utf-8")
    print(f"\n{pfad} aktualisiert (Bericht und Laufprotokoll).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
