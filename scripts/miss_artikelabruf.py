#!/usr/bin/env python3
"""Messaufgabe 3: Traegt eine Extraktionsbibliothek ueber die echten Seiten?

Nimmt echte Artikeladressen (aus den Feeds der konfigurierten Quellen oder
aus einer Datei), ruft die ARTIKELSEITE ab - den Weg also, den heute kein
Collector geht - und laesst `trafilatura` den Fliesstext herausziehen.

Ausgegeben wird je Artikel: HTTP-Status, Zeichenzahl des Extrakts, erkannte
Sprache und die ersten 160 Zeichen. Genau daran entscheidet sich Premortem 2
(Navigation statt Artikel) und Premortem 1 (Extrakt kuerzer als der Teaser).

    python3 scripts/miss_artikelabruf.py --fremd 12
    python3 scripts/miss_artikelabruf.py --urls datei.txt
"""
from __future__ import annotations

import argparse
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import feedparser  # noqa: E402
import py3langid  # noqa: E402
import trafilatura  # noqa: E402
from bs4 import BeautifulSoup  # noqa: E402

from telco_radar.config import load_config  # noqa: E402
from telco_radar.collect.http import fetch  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
BEKANNT = {"de", "en"}


def _text(roh: str) -> str:
    if not roh:
        return ""
    if "<" in roh:
        roh = BeautifulSoup(roh, "html.parser").get_text(" ", strip=True)
    return " ".join(roh.split())


def sprache(text: str) -> str:
    text = " ".join((text or "").split())
    if len(text) < 40:
        return "?"
    return py3langid.classify(text)[0]


def sammle_kandidaten(cfg, http_cfg, nur_fremd: bool, deckel: int):
    """Artikeladressen aus den Feeds - mit dem Teaser als Vergleichsmassstab."""
    quellen = []
    gesehen = set()
    kandidaten = list(cfg.news_sources) + list(cfg.tech_sources)
    for op in cfg.operators:
        kandidaten.extend(op.sources)
    for src in kandidaten:
        if src.type == "rss" and src.url not in gesehen:
            gesehen.add(src.url)
            quellen.append(src)

    def eine(src):
        try:
            resp = fetch(src.url, http_cfg, src.timeout_seconds, src.headers)
            if resp.status_code >= 400:
                return []
            feed = feedparser.parse(resp.content)
        except Exception:  # noqa: BLE001
            return []
        raus = []
        for entry in feed.entries[:3]:
            titel = _text(entry.get("title") or "")
            link = (entry.get("link") or "").strip()
            if not titel or not link:
                continue
            teaser = _text(entry.get("summary") or entry.get("description") or "")
            s = sprache(f"{titel}. {teaser}")
            if nur_fremd and (s in BEKANNT or s == "?"):
                continue
            raus.append({"quelle": src.name, "titel": titel, "url": link,
                         "teaser": len(teaser), "sprache": s})
        return raus

    treffer = []
    with ThreadPoolExecutor(max_workers=10) as pool:
        for teil in pool.map(eine, quellen):
            treffer.extend(teil)
            if len(treffer) >= deckel * 3:
                break
    # Je Quelle hoechstens einen - sonst misst die Stichprobe ein Layout.
    je_quelle: dict[str, dict] = {}
    for t in treffer:
        je_quelle.setdefault(t["quelle"], t)
    return list(je_quelle.values())[:deckel]


def hole_und_extrahiere(kand, http_cfg) -> dict:
    ergebnis = dict(kand, status=0, zeichen=0, extrakt="", extrakt_sprache="?")
    try:
        resp = fetch(kand["url"], http_cfg, 25, None)
        ergebnis["status"] = resp.status_code
        if resp.status_code >= 400:
            return ergebnis
        text = trafilatura.extract(
            resp.text, include_comments=False, include_tables=False,
            favor_precision=True) or ""
        text = " ".join(text.split())
        ergebnis["zeichen"] = len(text)
        ergebnis["extrakt"] = text[:160]
        ergebnis["extrakt_sprache"] = sprache(text)
    except Exception as exc:  # noqa: BLE001
        ergebnis["status"] = -1
        ergebnis["extrakt"] = f"{type(exc).__name__}: {str(exc)[:70]}"
    return ergebnis


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fremd", type=int, default=0,
                    help="N fremdsprachige Artikel aus den Feeds ziehen")
    ap.add_argument("--anzahl", type=int, default=12)
    ap.add_argument("--urls", type=Path, help="Datei mit je einer URL pro Zeile")
    args = ap.parse_args()

    cfg = load_config(ROOT)
    http_cfg = dict(cfg.settings.get("http", {}) or {})
    http_cfg.setdefault("timeout_seconds", 25)

    if args.urls:
        kandidaten = [{"quelle": "-", "titel": "-", "url": u.strip(),
                       "teaser": 0, "sprache": "?"}
                      for u in args.urls.read_text().splitlines() if u.strip()]
    else:
        deckel = args.fremd or args.anzahl
        print(f"Suche {deckel} Artikel"
              f"{' (nur fremdsprachig)' if args.fremd else ''} in den Feeds ...")
        kandidaten = sammle_kandidaten(cfg, http_cfg, bool(args.fremd), deckel)

    if not kandidaten:
        print("Keine Kandidaten gefunden.")
        return 1

    print(f"Rufe {len(kandidaten)} Artikelseiten ab ...\n")
    with ThreadPoolExecutor(max_workers=6) as pool:
        ergebnisse = list(pool.map(
            lambda k: hole_und_extrahiere(k, http_cfg), kandidaten))

    print("=" * 78)
    print("MESSAUFGABE 3 - Artikelabruf und Extraktion (trafilatura)")
    print("=" * 78)
    print(f"{'Quelle':<24}{'Spr':>4}{'HTTP':>6}{'Teaser':>8}{'Extrakt':>9}"
          f"{'Faktor':>8}")
    for e in ergebnisse:
        faktor = (f"{e['zeichen'] / e['teaser']:.1f}x"
                  if e["teaser"] else "-")
        print(f"{e['quelle'][:23]:<24}{e['sprache']:>4}{e['status']:>6}"
              f"{e['teaser']:>8}{e['zeichen']:>9}{faktor:>8}")

    n = len(ergebnisse)
    ok = [e for e in ergebnisse if e["status"] == 200 and e["zeichen"] >= 1200]
    duenn = [e for e in ergebnisse if e["status"] == 200 and e["zeichen"] < 1200]
    tot = [e for e in ergebnisse if e["status"] != 200]
    besser = [e for e in ergebnisse
              if e["teaser"] and e["zeichen"] >= 2 * e["teaser"]]

    print("\n" + "-" * 78)
    print(f"  brauchbarer Fliesstext (>=1200 Zeichen)   {len(ok):>3} von {n}"
          f"  ({len(ok) / n * 100:.0f}%)")
    print(f"  duenn (<1200, also kaum mehr als Teaser)  {len(duenn):>3} von {n}")
    print(f"  nicht abrufbar (403/404/Fehler)           {len(tot):>3} von {n}")
    print(f"  mindestens doppelt so lang wie der Teaser {len(besser):>3} von {n}"
          "   <- Premortem 1")

    abweichend = [e for e in ergebnisse
                  if e["sprache"] != "?" and e["extrakt_sprache"] != "?"
                  and e["sprache"] != e["extrakt_sprache"]]
    print(f"  Sprache Teaser != Sprache Volltext        {len(abweichend):>3} von {n}"
          "   <- Premortem 4")
    for e in abweichend[:6]:
        print(f"      {e['sprache']} -> {e['extrakt_sprache']}  "
              f"[{e['quelle'][:20]}] {e['titel'][:44]}")

    if tot:
        print("\n  Nicht abrufbar im Einzelnen:")
        for e in tot:
            print(f"   HTTP {e['status']:>4}  [{e['quelle'][:20]:<20}] "
                  f"{e['url'][:56]}")

    print("\n" + "=" * 78)
    print("PROBE - die ersten 160 Zeichen je Extrakt (Navigation oder Artikel?)")
    print("=" * 78)
    for e in ergebnisse:
        print(f"\n[{e['quelle'][:24]}] {e['sprache']} | {e['zeichen']} Zeichen")
        print(f"  {e['titel'][:72]}")
        print(f"  > {e['extrakt'][:160]}")

    print("\n  Sprachen der Extrakte:",
          dict(Counter(e["extrakt_sprache"] for e in ergebnisse)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
