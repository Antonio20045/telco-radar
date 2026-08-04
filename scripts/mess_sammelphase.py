#!/usr/bin/env python3
"""Sammelphase messen: Wanduhr, Sekunden je Quelle, langsamste Hosts.

Ruft alle konfigurierten Quellen einmal ab - ohne Delta-Schicht, ohne
Modell, ohne Schreibzugriff auf data/. Gedacht fuer den Vergleich
vorher/nachher beim Drehen an `collect_max_workers`,
`collect_host_parallel` und `collect_host_delay_seconds`.

    python scripts/mess_sammelphase.py --worker 8  --host-abstand 0
    python scripts/mess_sammelphase.py --worker 48 --host-abstand 1.0
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from telco_radar.collect import collect_all, _host  # noqa: E402
from telco_radar.config import load_config  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--root", type=Path, default=Path("."))
    p.add_argument("--worker", type=int, default=None)
    p.add_argument("--host-parallel", type=int, default=None)
    p.add_argument("--host-abstand", type=float, default=None)
    p.add_argument("--json", type=Path, default=None)
    args = p.parse_args(argv)

    cfg = load_config(args.root.resolve())
    if args.host_parallel is not None:
        cfg.settings["collect_host_parallel"] = args.host_parallel
    if args.host_abstand is not None:
        cfg.settings["collect_host_delay_seconds"] = args.host_abstand
    worker = args.worker or int(cfg.settings.get("collect_max_workers", 8))

    t0 = time.monotonic()
    items, results = collect_all(cfg, max_workers=worker)
    dauer = time.monotonic() - t0

    n = len(results)
    ok = sum(1 for r in results if r["status"] == "ok")
    leer = sum(1 for r in results if r["status"] == "empty")
    fail = sum(1 for r in results if r["status"] == "fail")
    arbeit = sum(r.get("seconds", 0.0) for r in results)
    hosts: dict[str, float] = defaultdict(float)
    for r in results:
        hosts[_host(r["url"])] += r.get("seconds", 0.0)

    print()
    print(f"Quellen              : {n} ({ok} ok / {leer} leer / {fail} Fehler)")
    print(f"Meldungen            : {len(items)}")
    print(f"Worker               : {worker}, je Host "
          f"{cfg.settings.get('collect_host_parallel', 1)} parallel, "
          f"{cfg.settings.get('collect_host_delay_seconds', 0.0)}s Abstand")
    print(f"Wanduhr              : {dauer:.1f}s")
    print(f"Arbeitszeit (Summe)  : {arbeit:.1f}s "
          f"= {arbeit / max(1, n):.1f}s je Quelle")
    print(f"Wanduhr je Quelle    : {dauer / max(1, n):.2f}s")
    print(f"Effektive Nebenlaeufigkeit: {arbeit / max(0.001, dauer):.1f}x")
    print()
    print("Langsamste Hosts (Summe der Abrufzeiten):")
    for host, sek in sorted(hosts.items(), key=lambda kv: -kv[1])[:12]:
        print(f"  {sek:7.1f}s  {host}")
    print()
    print("Langsamste Einzelquellen:")
    for r in sorted(results, key=lambda r: -r.get("seconds", 0))[:12]:
        print(f"  {r.get('seconds', 0):7.1f}s  {r['status']:5s} "
              f"{r['name'][:24]:24s} {r['url'][:60]}")

    if args.json:
        args.json.write_text(json.dumps({
            "worker": worker,
            "host_parallel": cfg.settings.get("collect_host_parallel", 1),
            "host_delay": cfg.settings.get("collect_host_delay_seconds", 0.0),
            "sekunden": round(dauer, 1),
            "quellen": n, "ok": ok, "leer": leer, "fehler": fail,
            "meldungen": len(items),
            "arbeitszeit": round(arbeit, 1),
            "quellen_detail": sorted(
                ({"name": r["name"], "url": r["url"], "status": r["status"],
                  "count": r.get("count", 0), "seconds": r.get("seconds", 0)}
                 for r in results), key=lambda r: -r["seconds"]),
        }, ensure_ascii=False, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
