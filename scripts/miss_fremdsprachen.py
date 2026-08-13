#!/usr/bin/env python3
"""Messaufgabe 1: Wie viele fremdsprachige Meldungen fallen wirklich an?

Arbeitet auf den VORHANDENEN Berichten (data/reports/*.json), startet also
weder die Pipeline noch einen Modellaufruf.

WICHTIG - die Grenze dieser Messung: im Berichts-JSON steht als einziges Feld
in der ORIGINALSPRACHE das `title`. Das Feld `summary` ist bereits die
deutsche Fassung des Analysten, `seen.jsonl` traegt seit dem v2-Format nur
noch Hashes. Gemessen wird hier also NUR auf der Ueberschrift, und das ist
genau die Messung, vor der das Konzept warnt: eine Ueberschrift ist kurz,
traegt viele Eigennamen und wird von jedem Sprachraten schlecht getroffen.

Diese Zahl ist deshalb die UNTERE Schranke fuer den Trend ueber die Ausgaben.
Die belastbare Zahl liefert scripts/miss_volltext_quellen.py, das die Feeds
wirklich abruft und auf Titel PLUS echtem Teaser misst.
"""
from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

import py3langid

ROOT = Path(__file__).resolve().parents[1]
BEKANNT = {"de", "en"}


def erkenne(text: str) -> tuple[str, float]:
    text = " ".join((text or "").split())
    if len(text) < 12:
        return "?", 0.0
    sprache, wert = py3langid.classify(text)
    return sprache, float(wert)


def meldungen(pfad: Path):
    daten = json.loads(pfad.read_text(encoding="utf-8"))
    for region in (daten.get("regions") or {}).values():
        for h in (region.get("highlights") or []):
            yield h


def main() -> int:
    berichte = sorted((ROOT / "data" / "reports").glob("*.json"))
    if not berichte:
        print("Keine Berichte in data/reports/ - nichts zu messen.")
        return 1

    je_ausgabe: list[tuple[str, int, int]] = []
    sprachen_titel = Counter()
    sprachen_beides = Counter()
    fremd_je_origin = Counter()
    uneinig: list[tuple[str, str, str, str]] = []
    beispiele = defaultdict(list)
    gesamt = 0
    ohne_teaser = 0

    for pfad in berichte:
        fremd = 0
        anzahl = 0
        for h in meldungen(pfad):
            titel = h.get("title") or ""
            # NICHT h["summary"] - das ist die deutsche Analystenfassung.
            teaser = ""
            if not titel:
                continue
            anzahl += 1
            gesamt += 1
            if not teaser.strip():
                ohne_teaser += 1

            s_beides, wert = erkenne(titel)
            sprachen_titel[s_beides] += 1
            sprachen_beides[s_beides] += 1
            if wert > -60 and s_beides not in BEKANNT and len(uneinig) < 25:
                uneinig.append((s_beides, f"{wert:.0f}", titel[:70],
                                (h.get("source") or "?")))

            if s_beides not in BEKANNT and s_beides != "?":
                fremd += 1
                fremd_je_origin[h.get("origin") or "?"] += 1
                if len(beispiele[s_beides]) < 3:
                    beispiele[s_beides].append(
                        (h.get("source") or h.get("source_name") or "?",
                         titel[:64], round(wert, 1)))
        je_ausgabe.append((pfad.stem, anzahl, fremd))

    print("=" * 72)
    print("MESSAUFGABE 1 - fremdsprachige Meldungen je Ausgabe")
    print("=" * 72)
    print(f"{'Ausgabe':<14}{'Meldungen':>10}{'fremdsprachig':>15}{'Anteil':>9}")
    for name, anzahl, fremd in je_ausgabe:
        quote = f"{fremd / anzahl * 100:.1f}%" if anzahl else "-"
        print(f"{name:<14}{anzahl:>10}{fremd:>15}{quote:>9}")
    summe_fremd = sum(f for _, _, f in je_ausgabe)
    print("-" * 72)
    print(f"{'SUMME':<14}{gesamt:>10}{summe_fremd:>15}"
          f"{(summe_fremd / gesamt * 100 if gesamt else 0):>8.1f}%")
    schnitt = summe_fremd / len(je_ausgabe) if je_ausgabe else 0
    print(f"\nSchnitt je Ausgabe: {schnitt:.1f} fremdsprachige Meldungen")
    print("Gemessen wurde NUR auf der Ueberschrift - siehe Modulkopf.")

    print("\nSprachen (auf Titel+Teaser gemessen):")
    for sprache, n in sprachen_beides.most_common(14):
        marke = "  " if sprache in BEKANNT else " *"
        print(f"{marke} {sprache:<5}{n:>6}   ({n / gesamt * 100:.1f}%)")
    print("   * = wuerde eine Uebersetzung bekommen")

    print("\nFremdsprachige je Herkunft (origin):")
    for origin, n in fremd_je_origin.most_common():
        print(f"   {origin:<16}{n:>5}")

    print(f"\nUnsichere Treffer (schwacher Score, also Ratefaelle): {len(uneinig)}")
    for sprache, wert, titel, quelle in uneinig[:25]:
        print(f"   {sprache:>3} ({wert:>5}) [{quelle[:22]:<22}] {titel}")

    if beispiele:
        print("\nBeispiele je erkannter Fremdsprache:")
        for sprache, eintraege in sorted(beispiele.items()):
            print(f"  {sprache}:")
            for quelle, titel, wert in eintraege:
                print(f"     [{quelle[:24]:<24}] {titel}  (score {wert})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
