#!/usr/bin/env python3
"""Messaufgabe 2: Wie viel Text liefern die Quellen heute schon mit?

Ruft die konfigurierten Feeds WIRKLICH ab (kein Modellaufruf, kein
Pipeline-Lauf, kein Schreiben nach data/state) und misst je Eintrag drei
Dinge:

  1. Laenge von summary/description - also das, was heute nach `[:600]`
     uebrig bleibt, und wie viel die Kappung wirklich abschneidet.
  2. Vorhandensein und Laenge von `content:encoded` - das Feld, das
     collect/rss.py heute NICHT liest und in dem WordPress & Co. den
     Volltext ablegen.
  3. Die Sprache, gemessen auf Titel PLUS echtem Teaser.

Damit beantwortet es die eine Frage, an der der ganze Zuschnitt haengt:
reicht es, die Kappung aufzuheben und ein Feld mehr zu lesen - oder braucht
es den teuren Abruf der Artikelseite?

    python3 scripts/miss_volltext_quellen.py              # 25 Quellen
    python3 scripts/miss_volltext_quellen.py --alle       # alle rss-Quellen
    python3 scripts/miss_volltext_quellen.py --nur-fremd  # nur nicht-en/de
"""
from __future__ import annotations

import argparse
import re
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import feedparser  # noqa: E402
import py3langid  # noqa: E402
from bs4 import BeautifulSoup  # noqa: E402

from telco_radar.config import load_config  # noqa: E402
from telco_radar.collect.http import fetch  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
BEKANNT = {"de", "en"}
# Ab hier gilt ein Teaser als "mehr als ein Anreisser". Die Kappung steht bei
# 600; alles darunter ist ohnehin kein Volltext.
VOLLTEXT_AB = 1200


def _text(roh: str) -> str:
    if not roh:
        return ""
    if "<" in roh:
        roh = BeautifulSoup(roh, "html.parser").get_text(" ", strip=True)
    return " ".join(roh.split())


def _content_encoded(entry) -> str:
    """Der Volltext, wenn der Feed ihn mitschickt.

    feedparser legt <content:encoded> unter entry.content ab - als Liste von
    Woerterbuechern mit `value` und `type`. Das laengste gewinnt: manche
    Feeds fuehren dort zusaetzlich eine Kurzfassung.
    """
    bester = ""
    for c in (entry.get("content") or []):
        wert = _text(c.get("value") or "")
        if len(wert) > len(bester):
            bester = wert
    return bester


def sprache(text: str) -> tuple[str, float]:
    text = " ".join((text or "").split())
    if len(text) < 40:
        return "?", 0.0
    s, w = py3langid.classify(text)
    return s, float(w)


def rss_quellen(cfg):
    """Alle Quellen, die durch den RSS-Parser laufen - je Kanal einmal."""
    raus = []
    gesehen = set()
    kandidaten = list(cfg.news_sources) + list(cfg.tech_sources)
    for op in cfg.operators:
        kandidaten.extend(op.sources)
    for src in kandidaten:
        if src.type != "rss" or src.url in gesehen:
            continue
        gesehen.add(src.url)
        raus.append(src)
    return raus


def miss_quelle(src, http_cfg) -> dict | None:
    try:
        resp = fetch(src.url, http_cfg, src.timeout_seconds, src.headers)
        if resp.status_code >= 400:
            return {"name": src.name, "url": src.url,
                    "fehler": f"HTTP {resp.status_code}"}
        feed = feedparser.parse(resp.content)
        if feed.bozo and not feed.entries:
            return {"name": src.name, "url": src.url,
                    "fehler": f"unparseable: {feed.bozo_exception}"}
    except Exception as exc:  # noqa: BLE001 - Diagnose, kein Produktionspfad
        return {"name": src.name, "url": src.url,
                "fehler": f"{type(exc).__name__}: {str(exc)[:60]}"}

    eintraege = []
    for entry in feed.entries[:10]:
        titel = _text(entry.get("title") or "")
        if not titel:
            continue
        teaser = _text(entry.get("summary") or entry.get("description") or "")
        voll = _content_encoded(entry)
        s, wert = sprache(f"{titel}. {teaser or voll}")
        eintraege.append({
            "titel": titel, "teaser": len(teaser), "content": len(voll),
            "sprache": s, "score": wert,
            "url": (entry.get("link") or "").strip(),
        })
    return {"name": src.name, "url": src.url, "eintraege": eintraege,
            "fehler": None}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--alle", action="store_true", help="alle rss-Quellen")
    ap.add_argument("--nur-fremd", action="store_true",
                    help="nur Quellen mit ueberwiegend fremdsprachigen Titeln")
    ap.add_argument("--anzahl", type=int, default=25)
    ap.add_argument("--worker", type=int, default=8)
    args = ap.parse_args()

    cfg = load_config(ROOT)
    quellen = rss_quellen(cfg)
    if not args.alle:
        quellen = quellen[:args.anzahl]
    http_cfg = dict(cfg.settings.get("http", {}) or {})
    http_cfg.setdefault("timeout_seconds", 20)

    print(f"Messe {len(quellen)} RSS-Quellen ...\n")
    with ThreadPoolExecutor(max_workers=args.worker) as pool:
        ergebnisse = [e for e in pool.map(
            lambda s: miss_quelle(s, http_cfg), quellen) if e]

    fehler = [e for e in ergebnisse if e.get("fehler")]
    gut = [e for e in ergebnisse if not e.get("fehler")]

    alle = [x for e in gut for x in e["eintraege"]]
    if args.nur_fremd:
        alle = [x for x in alle if x["sprache"] not in BEKANNT]

    print("=" * 78)
    print("A) JE QUELLE - Teaserlaenge und content:encoded")
    print("=" * 78)
    print(f"{'Quelle':<30}{'n':>4}{'Teaser~':>9}{'>600':>6}"
          f"{'content':>9}{'c>1200':>8}{'Spr':>5}")
    for e in sorted(gut, key=lambda x: x["name"]):
        eintraege = e["eintraege"]
        if not eintraege:
            continue
        n = len(eintraege)
        schnitt = sum(x["teaser"] for x in eintraege) // n
        ueber = sum(1 for x in eintraege if x["teaser"] > 600)
        mit_c = sum(1 for x in eintraege if x["content"] > 0)
        c_voll = sum(1 for x in eintraege if x["content"] >= VOLLTEXT_AB)
        spr = Counter(x["sprache"] for x in eintraege).most_common(1)[0][0]
        print(f"{e['name'][:29]:<30}{n:>4}{schnitt:>9}{ueber:>6}"
              f"{mit_c:>9}{c_voll:>8}{spr:>5}")

    if fehler:
        print(f"\nNicht abrufbar ({len(fehler)}):")
        for e in fehler[:15]:
            print(f"   {e['name'][:34]:<35}{e['fehler']}")

    print("\n" + "=" * 78)
    print("B) DIE ZAHL, AN DER DER ZUSCHNITT HAENGT")
    print("=" * 78)
    n = len(alle)
    if not n:
        print("Keine Eintraege gemessen.")
        return 1
    gekappt = sum(1 for x in alle if x["teaser"] > 600)
    hat_c = sum(1 for x in alle if x["content"] > 0)
    c_voll = sum(1 for x in alle if x["content"] >= VOLLTEXT_AB)
    teaser_voll = sum(1 for x in alle if x["teaser"] >= VOLLTEXT_AB)
    # Was ein Weg WIRKLICH einbringt: Volltext aus Feed, egal welches Feld.
    aus_feed = sum(1 for x in alle
                   if max(x["teaser"], x["content"]) >= VOLLTEXT_AB)

    def zeile(text, wert):
        print(f"  {text:<52}{wert:>5}  ({wert / n * 100:>5.1f}%)")

    print(f"  Gemessene Eintraege: {n}\n")
    zeile("Teaser laenger als die Kappung (>600)", gekappt)
    zeile("Teaser ist selbst schon Volltext (>=1200)", teaser_voll)
    zeile("hat ueberhaupt ein content:encoded", hat_c)
    zeile("content:encoded ist Volltext (>=1200)", c_voll)
    print("  " + "-" * 60)
    zeile("VOLLTEXT AUS DEM FEED (bestes Feld >=1200)", aus_feed)
    zeile("--> braucht den Abruf der Artikelseite", n - aus_feed)

    print("\n" + "=" * 78)
    print("C) SPRACHEN (auf Titel PLUS echtem Teaser)")
    print("=" * 78)
    sprachen = Counter(x["sprache"] for x in alle)
    fremd = sum(v for k, v in sprachen.items() if k not in BEKANNT and k != "?")
    for s, k in sprachen.most_common(12):
        marke = " *" if s not in BEKANNT and s != "?" else "  "
        print(f"{marke} {s:<5}{k:>6}   ({k / n * 100:.1f}%)")
    print(f"\n  fremdsprachig gesamt: {fremd} von {n} "
          f"({fremd / n * 100:.1f}%)")

    fr = [x for x in alle if x["sprache"] not in BEKANNT and x["sprache"] != "?"]
    if fr:
        fr_feed = sum(1 for x in fr
                      if max(x["teaser"], x["content"]) >= VOLLTEXT_AB)
        print(f"  davon mit Volltext im Feed: {fr_feed} "
              f"({fr_feed / len(fr) * 100:.1f}%)")
        print("\n  Beispiele fremdsprachiger Eintraege:")
        for x in fr[:12]:
            print(f"   {x['sprache']} t={x['teaser']:>5} c={x['content']:>6}"
                  f"  {x['titel'][:52]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
