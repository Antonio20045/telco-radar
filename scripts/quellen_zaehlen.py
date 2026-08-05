#!/usr/bin/env python3
"""Wie viele Quellen hat der Radar? Eine Zahl, eine Definition.

Warum es dieses Skript gibt: "Quelle" war im Projekt nie definiert, und es gab
keinen Zaehler. Je nachdem was man zaehlt, sind es fuer denselben Bestand 94,
167, 172, 187 oder 87 - und jede Session hat sich eine andere Zahl gegriffen.
Am 05.08.2026 stand deshalb in einer Schlussliste "138 Quellen" (aus einem
groben `grep -c "url:"`, das die nicht crawlbaren official-Referenzen und eine
Kommentarzeile mitzaehlte), waehrend der Lauf desselben Tages 167 protokolliert
hat.

DIE ZAHL ist die crawlbare: Betreiberquellen + Fachpresse + Themenquellen.
Also das, was ein Lauf wirklich abfragt. Genau diese Zahl schreibt die
Pipeline in jedem Bericht unter stats.sources_total mit; dieses Skript
rechnet sie aus der Konfiguration aus und prueft beides gegeneinander.

NICHT mitgezaehlt, und zwar jeweils mit Grund:
  official-Referenzen  bot-geschuetzte Newsrooms, die nur als verifizierter
                       Link auf der Quellenseite stehen und nie abgerufen
                       werden. Sie liefern nichts, also zaehlen sie nicht.
  Promo-Seiten         zweiter Anwendungsfall (deutsche Tarif-/Aktionsuebersicht)
                       mit eigener Pipeline, eigenem State und eigener Seite.
  Betreiber            sind Firmen, keine Quellen. Ein Betreiber kann drei
                       Kanaele haben oder keinen.

    python scripts/quellen_zaehlen.py
    python scripts/quellen_zaehlen.py --verlauf     # ueber das Berichtsarchiv
"""
from __future__ import annotations

import argparse
import glob
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from telco_radar.config import load_config  # noqa: E402


def zaehle(root: Path) -> dict:
    cfg = load_config(root)
    betreiber_quellen = [s for op in cfg.operators for s in op.crawled_sources]
    official = [s for op in cfg.operators for s in op.sources if not s.crawlable]
    themen = [s for s in cfg.tech_sources if s.crawlable]

    promo = 0
    promo_pfad = root / "config" / "promo_sources.yaml"
    if promo_pfad.exists():
        import yaml
        roh = yaml.safe_load(promo_pfad.read_text(encoding="utf-8")) or {}
        promo = len(roh.get("brands") or [])

    return {
        "betreiberquellen": len(betreiber_quellen),
        "fachpresse": len(cfg.news_sources),
        "themenquellen": len(themen),
        "crawlbar_gesamt": len(betreiber_quellen) + len(cfg.news_sources) + len(themen),
        "betreiber": len(cfg.operators),
        "regionen": len(cfg.region_names) - 1,
        "themenfelder": len(cfg.theme_names),
        "official_referenzen": len(official),
        "promo_seiten": promo,
    }


def verlauf(root: Path) -> list[dict]:
    """Was die Laeufe selbst protokolliert haben - die einzige Rueckschau,
    die nicht von der heutigen Konfiguration abhaengt."""
    aus = []
    for pfad in sorted(glob.glob(str(root / "data" / "reports" / "*.json"))):
        try:
            d = json.loads(Path(pfad).read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        s = d.get("stats") or {}
        aus.append({"datum": d.get("date", "?"),
                    "quellen": s.get("sources_total"),
                    "betreiber": s.get("operators"),
                    "themenfelder": s.get("themes"),
                    "gesammelt": s.get("collected"),
                    "neu": s.get("new")})
    return aus


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--root", type=Path, default=Path("."))
    p.add_argument("--verlauf", action="store_true",
                   help="Entwicklung ueber alle protokollierten Laeufe")
    p.add_argument("--json", action="store_true")
    args = p.parse_args(argv)

    z = zaehle(args.root.resolve())
    if args.json:
        print(json.dumps(z, ensure_ascii=False, indent=1))
        return 0

    print(f"\n  QUELLEN: {z['crawlbar_gesamt']}\n")
    print(f"    {z['betreiberquellen']:>4}  Betreiberquellen "
          f"({z['betreiber']} Betreiber in {z['regionen']} Regionen)")
    print(f"    {z['fachpresse']:>4}  Fachpresse")
    print(f"    {z['themenquellen']:>4}  Themenquellen "
          f"(in {z['themenfelder']} Themenfeldern)")
    print(f"    {'':>4}  " + "-" * 40)
    print(f"    {z['crawlbar_gesamt']:>4}  crawlbar gesamt  <- DIESE ZAHL\n")
    print("  nicht mitgezaehlt:")
    print(f"    {z['official_referenzen']:>4}  official-Referenzen "
          "(bot-geschuetzt, werden nie abgerufen)")
    print(f"    {z['promo_seiten']:>4}  Promo-Seiten "
          "(eigener Anwendungsfall, eigene Pipeline)")

    lauf = verlauf(args.root.resolve())
    if lauf:
        letzter = lauf[-1]
        stimmt = letzter["quellen"] == z["crawlbar_gesamt"]
        print(f"\n  letzter Lauf ({letzter['datum']}): "
              f"{letzter['quellen']} Quellen abgefragt"
              + ("  ✓ deckt sich mit der Konfiguration" if stimmt else
                 "  ! weicht von der Konfiguration ab - seither geaendert?"))

    if args.verlauf:
        print("\n  Verlauf (aus stats.sources_total der Laeufe):\n")
        print(f"    {'Datum':12} {'Quellen':>8} {'Betreiber':>10} "
              f"{'Themen':>7} {'gesammelt':>10} {'neu':>6}")
        vorher = None
        for e in lauf:
            delta = ("" if vorher is None or e["quellen"] is None
                     else f"  {e['quellen'] - vorher:+d}")
            print(f"    {e['datum']:12} {str(e['quellen']):>8} "
                  f"{str(e['betreiber']):>10} {str(e['themenfelder']):>7} "
                  f"{str(e['gesammelt']):>10} {str(e['neu']):>6}{delta}")
            vorher = e["quellen"]
    print()
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except BrokenPipeError:
        # `... | head` schliesst die Pipe - kein Fehler, sondern der Normalfall
        # beim Nachschauen.
        raise SystemExit(0)
