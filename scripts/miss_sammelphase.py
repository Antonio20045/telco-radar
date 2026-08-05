#!/usr/bin/env python3
"""Sammelphase messen: Wanduhr, Sekunden je Quelle, Fehlerbild.

Zweck (AUFTRAG_SKALIERUNG_1000.md Abschnitt 3.1 / Abzuliefern 1): die
Parallelitaet der Sammelphase ist der einzige Hebel, der 1000 Quellen unter
das Job-Timeout bringt - aber nur, wenn sie den Quellen nicht 429/403
einbringt. Beides ist ohne Messung nicht zu unterscheiden: ein gedrosselter
Host sieht im Protokoll aus wie eine langsame Quelle.

Das Skript ruft ALLE konfigurierten Quellen ueber genau den Pfad der Pipeline
ab (collect_all) und schreibt Wanduhr, Arbeitszeit, Sekunden je Quelle und die
Statusverteilung. Mit --vergleich laeuft es mehrere Einstellungen nacheinander
und stellt sie gegenueber.

    python scripts/miss_sammelphase.py                      # aktuelle settings.yaml
    python scripts/miss_sammelphase.py --workers 48 --host-parallel 2
    python scripts/miss_sammelphase.py --vergleich 8:1000:0 48:2:0.5
    python scripts/miss_sammelphase.py --json outputs/messung.json
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from telco_radar.collect import collect_all  # noqa: E402
from telco_radar.config import load_config  # noqa: E402


def _messung(cfg, workers: int, host_parallel: int, host_interval: float) -> dict:
    cfg.settings["collect_host_max_parallel"] = host_parallel
    cfg.settings["collect_host_min_interval_seconds"] = host_interval
    t0 = time.monotonic()
    items, results = collect_all(cfg, max_workers=workers)
    wanduhr = time.monotonic() - t0

    arbeit = sum(r.get("seconds", 0.0) for r in results)
    status: dict[str, int] = {}
    for r in results:
        status[r["status"]] = status.get(r["status"], 0) + 1
    langsam = sorted(results, key=lambda r: -r.get("seconds", 0.0))[:10]
    gedrosselt = [r for r in results if "429" in str(r.get("error", ""))
                  or "403" in str(r.get("error", ""))]

    return {
        "workers": workers,
        "host_parallel": host_parallel,
        "host_interval": host_interval,
        "quellen": len(results),
        "wanduhr_s": round(wanduhr, 1),
        "arbeit_s": round(arbeit, 1),
        "arbeit_je_quelle_s": round(arbeit / len(results), 2) if results else 0,
        "wanduhr_je_quelle_s": round(wanduhr / len(results), 3) if results else 0,
        "meldungen": len(items),
        "status": status,
        "gedrosselt": len(gedrosselt),
        "gedrosselte_quellen": [r["url"] for r in gedrosselt][:20],
        "langsamste": [{"name": r["name"], "url": r["url"],
                        "sekunden": r.get("seconds"), "status": r["status"]}
                       for r in langsam],
        # Hochrechnung auf 1000 Quellen bei gleicher Arbeitszeit je Quelle und
        # gleicher effektiver Parallelitaet.
        "hochrechnung_1000_min": round(
            (arbeit / len(results) * 1000) / max(1.0, arbeit / wanduhr) / 60, 1)
        if results and wanduhr else None,
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--root", type=Path, default=Path("."))
    p.add_argument("--workers", type=int, default=None)
    p.add_argument("--host-parallel", type=int, default=None)
    p.add_argument("--host-interval", type=float, default=None)
    p.add_argument("--vergleich", nargs="*", default=None,
                   metavar="WORKERS:HOSTPARALLEL:INTERVALL")
    p.add_argument("--json", type=Path)
    p.add_argument("-v", "--verbose", action="store_true")
    args = p.parse_args(argv)

    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING,
                        format="%(levelname)-7s %(message)s", stream=sys.stdout)
    cfg = load_config(args.root.resolve())

    laeufe = []
    if args.vergleich:
        for spec in args.vergleich:
            teile = (spec.split(":") + ["", ""])[:3]
            laeufe.append((int(teile[0]),
                           int(teile[1] or 2),
                           float(teile[2] or 0.0)))
    else:
        laeufe.append((
            args.workers or int(cfg.settings.get("collect_max_workers", 8)),
            args.host_parallel if args.host_parallel is not None
            else int(cfg.settings.get("collect_host_max_parallel", 2)),
            args.host_interval if args.host_interval is not None
            else float(cfg.settings.get("collect_host_min_interval_seconds", 0.0)),
        ))

    ergebnisse = []
    for workers, hp, hi in laeufe:
        print(f"\n>>> {workers} Worker, max. {hp} je Host, {hi}s Abstand ...",
              flush=True)
        erg = _messung(cfg, workers, hp, hi)
        ergebnisse.append(erg)
        print(f"    {erg['quellen']} Quellen | Wanduhr {erg['wanduhr_s']}s | "
              f"Arbeit {erg['arbeit_s']}s ({erg['arbeit_je_quelle_s']}s/Quelle) | "
              f"{erg['meldungen']} Meldungen | {erg['status']} | "
              f"gedrosselt: {erg['gedrosselt']} | "
              f"1000 Quellen ≈ {erg['hochrechnung_1000_min']} min", flush=True)

    if len(ergebnisse) > 1:
        print("\n| Worker | je Host | Abstand | Wanduhr | Arbeit/Quelle | ok/leer/Fehler | 429/403 | 1000 ≈ |")
        print("|---:|---:|---:|---:|---:|---|---:|---:|")
        for e in ergebnisse:
            s = e["status"]
            print(f"| {e['workers']} | {e['host_parallel']} | {e['host_interval']}s "
                  f"| {e['wanduhr_s']}s | {e['arbeit_je_quelle_s']}s "
                  f"| {s.get('ok',0)}/{s.get('empty',0)}/{s.get('fail',0)} "
                  f"| {e['gedrosselt']} | {e['hochrechnung_1000_min']} min |")

    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(ergebnisse, ensure_ascii=False, indent=1),
                             encoding="utf-8")
        print(f"\nJSON geschrieben: {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
