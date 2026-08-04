#!/usr/bin/env python3
"""Seen-Store vom alten JSONL ins kompakte Format ueberfuehren.

Aus je ~300 Byte (id, volle URL, Titel, Quelle, ISO-Zeitstempel) werden
~22 Byte (id, Tagesnummer). Bei 1000 Quellen ist das der Unterschied
zwischen ~67 MB und ~5 MB im Jahr - GitHubs hartes Limit je Datei liegt
bei 100 MB.

Die Pipeline uebernimmt den Altbestand notfalls von selbst (SeenStore liest
`seen.jsonl`, wenn `seen.tsv` fehlt). Dieses Skript macht dasselbe
nachvollziehbar und einmalig, damit die alte Datei danach aus dem Repo
verschwinden kann:

    python scripts/migriere_seen_store.py --probe    # nur rechnen
    python scripts/migriere_seen_store.py            # schreiben
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from telco_radar.dedupe import SeenStore  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--state", type=Path, default=Path("data/state"))
    p.add_argument("--monate", type=int, default=0,
                   help="Verfall in Monaten (0 = alles uebernehmen)")
    p.add_argument("--probe", action="store_true", help="nichts schreiben")
    args = p.parse_args(argv)

    alt = args.state / "seen.jsonl"
    neu = args.state / "seen.tsv"
    if not alt.exists():
        print(f"{alt} gibt es nicht - nichts zu tun.")
        return 0
    if neu.exists():
        print(f"{neu} gibt es bereits. Bitte erst pruefen und ggf. loeschen.")
        return 1

    alt_bytes = alt.stat().st_size
    alt_zeilen = sum(1 for line in alt.read_text(encoding="utf-8").splitlines()
                     if line.strip())

    store = SeenStore(neu, max_age_days=int(args.monate * 30.44) or None,
                      legacy_path=alt)
    print(f"gelesen    : {alt_zeilen} Zeilen, {alt_bytes / 1024:.0f} KB "
          f"({alt_bytes / max(1, alt_zeilen):.0f} Byte je Eintrag)")
    print(f"uebernommen: {len(store)} Eintraege"
          + (f", {store.verfallen} verfallen" if store.verfallen else ""))

    if args.probe:
        geschaetzt = len(store) * 22
        print(f"wuerde schreiben: ~{geschaetzt / 1024:.0f} KB "
              f"({geschaetzt / max(1, alt_bytes) * 100:.0f} % der alten Datei)")
        return 0

    store.schreibe_neu()
    neu_bytes = neu.stat().st_size
    print(f"geschrieben: {neu} - {neu_bytes / 1024:.0f} KB "
          f"({neu_bytes / max(1, alt_bytes) * 100:.0f} % der alten Datei, "
          f"{neu_bytes / max(1, len(store)):.0f} Byte je Eintrag)")
    print(f"\nDie alte Datei kann jetzt entfernt werden:  git rm {alt}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
