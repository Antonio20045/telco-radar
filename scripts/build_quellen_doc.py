#!/usr/bin/env python3
"""Erzeugt TELCO_RADAR_QUELLEN.md aus config/watchlist.yaml + config/news_sources.yaml.

Die Watchlist ist die Wahrheitsquelle (siehe Kopf der YAML). Dieses Skript
liest sie und schreibt die menschenlesbare Quellenliste - anders als das
abgeloeste scripts/build_sources.py schreibt es NICHTS nach config/ zurueck.

    python scripts/build_quellen_doc.py              # nur aus der Watchlist
    python scripts/build_quellen_doc.py --validate   # zusaetzlich live pruefen

Mit --validate wird jede Quelle mit dem echten Collector abgerufen; in der
Spalte "Verifikation" stehen dann Item-Zahl, wie viele davon datiert sind,
das neueste Datum und wie viele Meldungen im Frischefenster liegen. Ohne
--validate bleibt die Spalte leer, damit nie erfundene Zahlen im Dokument
landen.
"""
from __future__ import annotations

import argparse
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from telco_radar.config import load_config  # noqa: E402

KIND_LABEL = {
    "rss": "Feed (RSS/Atom)",
    "json_api": "Feed (JSON-API)",
    "newsroom": "Newsroom (statisch)",
    "newsroom_js": "Newsroom (Headless/Playwright)",
    "official": "Referenz (nicht automatisiert)",
}


def _validate(cfg) -> dict[str, str]:
    """Ruft jede Quelle einmal ab und liefert je Quelle eine Belegzeile."""
    from telco_radar.collect import collect_source

    http_cfg = cfg.settings.get("http", {})
    lookback = int(cfg.settings.get("lookback_days", 8))

    jobs = [(s, o.region_key, o.name) for o in cfg.operators for s in o.sources]
    jobs += [(s, "global", s.name) for s in cfg.news_sources]

    def one(source, region, name):
        if source.kind == "official":
            return name, source.url, "nicht gecrawlt (Referenz)"
        try:
            items = collect_source(source, region, name, "operator", http_cfg)
        except Exception as exc:  # noqa: BLE001
            text = str(exc)
            if "BrowserType.launch" in text or "Executable doesn't exist" in text:
                # Sandbox ohne Headless-Browser: das sagt nichts ueber die
                # Quelle aus, in GitHub Actions laeuft sie normal. Als Fehler
                # ins Dokument zu schreiben waere schlicht falsch.
                return name, source.url, ("hier nicht pruefbar (kein "
                                          "Headless-Browser), laeuft in GitHub Actions")
            return name, source.url, f"FEHLER: {type(exc).__name__}: {text[:60]}"
        dated = [i for i in items if i.published]
        fresh = sum(1 for i in items if i.age_days() is not None
                    and -1 <= i.age_days() <= lookback)
        if not items:
            return name, source.url, "0 Meldungen"
        newest = max(i.published for i in dated).date().isoformat() if dated else "-"
        return (name, source.url,
                f"{len(items)} Meldungen, {len(dated)} datiert, neuestes {newest}, "
                f"{fresh} im {lookback}-Tage-Fenster")

    out: dict[str, str] = {}
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = [pool.submit(one, s, r, n) for s, r, n in jobs]
        for fut in as_completed(futures):
            name, url, note = fut.result()
            out[f"{name}|{url}"] = note
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--validate", action="store_true",
                        help="jede Quelle live abrufen und belegen (dauert ~4 min)")
    parser.add_argument("--out", type=Path, default=ROOT / "TELCO_RADAR_QUELLEN.md")
    args = parser.parse_args()

    cfg = load_config(ROOT)
    checks = _validate(cfg) if args.validate else {}

    kinds: dict[str, int] = {}
    for op in cfg.operators:
        for s in op.sources:
            kinds[s.kind] = kinds.get(s.kind, 0) + 1

    L: list[str] = []
    L.append("# Telco Radar — Quellenliste (offizielle Betreiber-Quellen)\n")
    L.append(f"Erzeugt am {date.today().strftime('%d.%m.%Y')} mit "
             "`scripts/build_quellen_doc.py`"
             + (" --validate" if args.validate else "")
             + " aus `config/watchlist.yaml`.")
    if not args.validate:
        L.append("\n> Ohne `--validate` erzeugt: die Spalte Verifikation ist leer, "
                 "weil nur echte Abrufe dort stehen sollen.")
    L.append("\n**Primaerquelle jedes Betreibers ist seine eigene Domain.** "
             "Ausnahmen sind im YAML kommentiert und unten in der Spalte "
             "Verifikation erkennbar. Telco-Fachpresse ist eine separate zweite "
             "Ebene (`config/news_sources.yaml`).\n")

    L.append("## Ueberblick\n")
    L.append(f"- **{len(cfg.operators)} Betreiber** in {len(cfg.region_names) - 1} Regionen.")
    L.append(f"- Direkt maschinenlesbar (Feed/JSON): **{kinds.get('rss', 0) + kinds.get('json_api', 0)}** "
             f"({kinds.get('rss', 0)}x RSS/Atom, {kinds.get('json_api', 0)}x JSON-API).")
    L.append(f"- Newsroom statisch: **{kinds.get('newsroom', 0)}**.")
    L.append(f"- Newsroom JS-gerendert: **{kinds.get('newsroom_js', 0)}**.")
    L.append(f"- Nicht automatisiert (Referenz + Begruendung): **{kinds.get('official', 0)}**.")
    L.append(f"- Fachpresse: **{len(cfg.news_sources)}** Feeds.\n")

    by_region: dict[str, list] = {}
    for op in cfg.operators:
        by_region.setdefault(op.region_key, []).append(op)
    for region_key, ops in by_region.items():
        L.append(f"## {cfg.region_names.get(region_key, region_key)} ({len(ops)})\n")
        L.append("| Betreiber | Land | Website | Quelle | Anbindung | Verifikation |")
        L.append("|---|---|---|---|---|---|")
        for op in sorted(ops, key=lambda o: o.name):
            for s in op.sources:
                extra = ""
                if s.item_selector:
                    extra = f" (item_selector: `{s.item_selector}`)"
                note = checks.get(f"{op.name}|{s.url}", "")
                if s.kind == "official" and s.plan:
                    note = (note + " — " if note else "") + " ".join(s.plan.split())[:300]
                L.append(f"| {op.name} | {op.country} | {op.website} | {s.url} | "
                         f"{KIND_LABEL.get(s.kind, s.kind)}{extra} | {note} |")
        L.append("")

    L.append("## Fachpresse (zweite Ebene)\n")
    L.append("| Quelle | Feed | Verifikation |")
    L.append("|---|---|---|")
    for s in cfg.news_sources:
        L.append(f"| {s.name} | {s.url} | {checks.get(f'{s.name}|{s.url}', '')} |")
    L.append("")

    args.out.write_text("\n".join(L), encoding="utf-8")
    print(f"Geschrieben: {args.out} ({len(cfg.operators)} Betreiber, "
          f"{len(cfg.news_sources)} Fachpresse-Feeds"
          + (", live geprueft" if args.validate else "") + ")")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
