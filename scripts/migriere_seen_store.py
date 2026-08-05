#!/usr/bin/env python3
"""Seen-Store vom alten JSON-Format (v1) auf das kompakte Zeilenformat (v2).

Warum (AUFTRAG_SKALIERUNG_1000.md 3.3): v1 legte je Meldung id, volle URL,
Titel, Quelle und Zeitstempel ab - ~300 Byte. Hochgerechnet auf 1000 Quellen
sind das ~67 MB im Jahr gegen ein hartes GitHub-Limit von 100 MB je Datei.
v2 speichert nur den Hash (17 Byte je Zeile) und kommt damit auf ~4 MB im
Jahr, ohne die Kerngarantie anzutasten.

Die Migration ist verlustfrei fuer das, was der Store leisten muss: die MENGE
der bekannten Hashes bleibt Zeichen fuer Zeichen dieselbe. Das Skript prueft
das selbst nach und bricht ab, wenn auch nur ein Hash fehlt - ein Fehler hier
waere teurer als jede fehlende Quelle, weil bereits berichtete Meldungen
zurueck in den naechsten Bericht kaemen.

Was v1 zusaetzlich enthielt (URL, Titel, Quelle je Meldung), wird vorher nach
data/state/seen_historie_je_quelle.json ausgewertet: je Quelle, wie viele
NEUE Meldungen sie ueber die Zeit geliefert hat und wann zuerst/zuletzt. Das
ist der historische Nenner der Trefferquote - kuenftig liefert ihn das
Laufprotokoll je Lauf mit ("new" je Quelle).

    python scripts/migriere_seen_store.py            # Probelauf, schreibt nichts
    python scripts/migriere_seen_store.py --schreiben
"""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

KOPFZEILE = ("# telco-radar seen-store v2 - ein Item-Hash je Zeile, '@' setzt "
             "den Zeitstempel\n")


def _lies_v1(pfad: Path) -> tuple[list[dict], list[str], int]:
    """Liefert (v1-Saetze, bereits-v2-Hashes, defekte Zeilen)."""
    saetze: list[dict] = []
    v2_hashes: list[str] = []
    defekt = 0
    stempel: str | None = None
    for zeile in pfad.read_text(encoding="utf-8").splitlines():
        zeile = zeile.strip()
        if not zeile or zeile.startswith("#"):
            continue
        if zeile.startswith("@"):
            stempel = zeile[1:]
            continue
        if zeile.startswith("{"):
            try:
                rec = json.loads(zeile)
                rec.setdefault("first_seen", stempel or "")
                saetze.append(rec)
            except (json.JSONDecodeError, KeyError):
                defekt += 1
            continue
        v2_hashes.append(zeile)
    return saetze, v2_hashes, defekt


def historie_je_quelle(saetze: list[dict]) -> dict[str, dict]:
    """Je Quelle: wie viele NEUE Meldungen, seit wann, bis wann."""
    je_quelle: dict[str, dict] = {}
    for rec in saetze:
        quelle = rec.get("source") or "?"
        eintrag = je_quelle.setdefault(quelle, {
            "quelle": quelle, "neu_gesamt": 0,
            "erste_meldung": None, "letzte_meldung": None, "laeufe": 0,
        })
        eintrag["neu_gesamt"] += 1
        ts = (rec.get("first_seen") or "")[:10]
        if ts:
            if not eintrag["erste_meldung"] or ts < eintrag["erste_meldung"]:
                eintrag["erste_meldung"] = ts
            if not eintrag["letzte_meldung"] or ts > eintrag["letzte_meldung"]:
                eintrag["letzte_meldung"] = ts
    tage: dict[str, set[str]] = defaultdict(set)
    for rec in saetze:
        tage[rec.get("source") or "?"].add((rec.get("first_seen") or "")[:10])
    for quelle, eintrag in je_quelle.items():
        eintrag["laeufe"] = len([t for t in tage[quelle] if t])
    return je_quelle


def schreibe_v2(saetze: list[dict], v2_hashes: list[str]) -> str:
    """v2-Text bauen: Hashes nach Zeitstempel gruppiert, Reihenfolge erhalten."""
    zeilen = [KOPFZEILE]
    aktueller: str | None = None
    gesehen: set[str] = set()
    for rec in saetze:
        h = rec["id"]
        if h in gesehen:
            continue
        gesehen.add(h)
        stempel = rec.get("first_seen") or ""
        if stempel != aktueller:
            zeilen.append("@" + stempel + "\n")
            aktueller = stempel
        zeilen.append(h + "\n")
    uebrig = [h for h in v2_hashes if h not in gesehen]
    if uebrig:
        zeilen.append("@\n")
        zeilen.extend(h + "\n" for h in uebrig)
    return "".join(zeilen)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--root", type=Path, default=Path("."))
    p.add_argument("--schreiben", action="store_true",
                   help="ohne dieses Flag nur rechnen, nichts aendern")
    args = p.parse_args(argv)

    state = args.root / "data" / "state"
    pfad = state / "seen.jsonl"
    if not pfad.exists():
        print(f"{pfad} gibt es nicht - nichts zu tun.")
        return 0

    vorher_bytes = pfad.stat().st_size
    saetze, v2_hashes, defekt = _lies_v1(pfad)
    if not saetze:
        print(f"Keine v1-Zeilen in {pfad} - der Store ist bereits migriert "
              f"({len(v2_hashes)} Hashes).")
        return 0

    text = schreibe_v2(saetze, v2_hashes)

    # --- Nachpruefung: die MENGE der Hashes muss identisch sein
    vorher = {r["id"] for r in saetze} | set(v2_hashes)
    nachher = {z.strip() for z in text.splitlines()
               if z.strip() and not z.startswith(("#", "@"))}
    if vorher != nachher:
        fehlend = vorher - nachher
        print(f"ABBRUCH: {len(fehlend)} Hash(es) wuerden verloren gehen "
              f"(z.B. {sorted(fehlend)[:3]}). Es wurde nichts geschrieben.")
        return 1

    historie = historie_je_quelle(saetze)
    nachher_bytes = len(text.encode("utf-8"))
    print(f"{len(vorher)} Hashes | {defekt} defekte Zeile(n) uebersprungen")
    print(f"{vorher_bytes/1024:.0f} KB  ->  {nachher_bytes/1024:.0f} KB "
          f"(Faktor {vorher_bytes/nachher_bytes:.1f}, "
          f"{nachher_bytes/max(1,len(vorher)):.0f} Byte je Eintrag)")
    print(f"Hochrechnung 233 000 Eintraege/Jahr: "
          f"{233_000*nachher_bytes/max(1,len(vorher))/1024/1024:.1f} MB/Jahr "
          f"(vorher {233_000*vorher_bytes/max(1,len(vorher))/1024/1024:.1f} MB/Jahr)")
    print(f"Historie je Quelle: {len(historie)} Quellen")

    if not args.schreiben:
        print("\nProbelauf - mit --schreiben wird es wirklich umgeschrieben.")
        return 0

    (state / "seen_historie_je_quelle.json").write_text(
        json.dumps(sorted(historie.values(), key=lambda e: -e["neu_gesamt"]),
                   ensure_ascii=False, indent=1), encoding="utf-8")
    pfad.write_text(text, encoding="utf-8")
    print(f"\nGeschrieben: {pfad} und {state/'seen_historie_je_quelle.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
