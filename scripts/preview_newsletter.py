#!/usr/bin/env python3
"""Drei Beispielausgaben nach `outputs/mail-preview/` - zum Ansehen.

Eine Mail ist erst fertig, wenn sie jemand ANGESEHEN hat. Diese Codebasis
hat die Lehre teuer bezahlt: die Positionskarte des Geraeteradars ging mit
Etiketten live, die bis zu 235 px neben ihrem Punkt standen - Tests
geschrieben, Daten geprueft, Quellen diagnostiziert, und niemand hatte das
Ergebnis mit den Augen kontrolliert.

Drei Faelle, weil sie verschiedene Dinge zeigen:

  1. **voller Filter** - eine enge Auswahl. Zeigt, ob die Mail bei drei
     Meldungen noch nach etwas aussieht oder nach einem Rest.
  2. **minimaler Filter** - alles. Zeigt den Deckel von acht Eintraegen und
     die Reihenfolge.
  3. **reiner Stichwort-Treffer** - eine Auswahl, die NUR ueber ein
     Stichwort etwas hereinholt. Der Fall, in dem die Markierung "Ihr
     Stichwort: ..." das Einzige ist, was die Mail erklaert.

Aufruf:
    PYTHONPATH=src python scripts/preview_newsletter.py
    PYTHONPATH=src python scripts/preview_newsletter.py --datum 2026-08-08
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

WURZEL = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(WURZEL / "src"))

from telco_radar.newsletter import render                      # noqa: E402
from telco_radar.newsletter.config import lade_katalog         # noqa: E402
from telco_radar.newsletter.filters import (                   # noqa: E402
    Filtersatz, Stichwort, waehle)
from telco_radar.newsletter.quelle import aus_bericht, aus_promo  # noqa: E402

BASIS = "https://telco-radar.onrender.com"

FAELLE = [
    ("voller-filter", "Enge Auswahl: Europa, Tarife, Telekom und O2",
     Filtersatz(bereiche=("marktrecherche",), regionen=("europa",),
                kategorien=("tarife",), wettbewerber=("telekom", "o2"))),
    ("minimal", "Keine Auswahl - alles, gedeckelt auf acht",
     Filtersatz()),
    ("nur-stichwort", "Ozeanien (trifft fast nie) plus zwei Stichwoerter",
     Filtersatz(regionen=("ozeanien",),
                stichwoerter=(Stichwort("Starlink"),
                              Stichwort("Netzausbau"),
                              Stichwort("Fixed Wireless Access", "phrase")))),
]


def _monat_de(iso: str) -> str:
    from telco_radar.report.html import _fmt_date_de
    return _fmt_date_de(iso)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--datum", help="Ausgabe (Vorgabe: die juengste)")
    p.add_argument("--ziel", default="outputs/mail-preview")
    args = p.parse_args()

    reports = WURZEL / "data" / "reports"
    kandidaten = sorted(f for f in reports.glob("*.json")
                        if len(f.stem) == 10 and f.stem[4] == "-")
    if not kandidaten:
        print("Keine Berichte unter data/reports/ - nichts zu zeigen.")
        return 1
    datei = (reports / f"{args.datum}.json") if args.datum else kandidaten[-1]
    if not datei.exists():
        print(f"Kein Bericht {datei.name}")
        return 1
    bericht = json.loads(datei.read_text(encoding="utf-8"))
    datum = bericht.get("date") or datei.stem

    eintraege = aus_bericht(bericht,
                            bericht_url=f"{BASIS}/reports/{datum}.html")
    promo_db = WURZEL / "data" / "state" / "promo_db.json"
    if promo_db.exists():
        daten = json.loads(promo_db.read_text(encoding="utf-8"))
        eintraege += aus_promo(daten.get("entries") or [])

    katalog = lade_katalog(WURZEL)
    ziel = WURZEL / args.ziel
    ziel.mkdir(parents=True, exist_ok=True)

    print(f"Ausgabe {datum} - {len(eintraege)} Einträge zur Auswahl\n")
    for name, beschreibung, satz in FAELLE:
        treffer = waehle(eintraege, satz, katalog)
        nachricht = render.baue(
            treffer, datum_de=_monat_de(datum),
            bericht_url=f"{BASIS}/index.html",
            abmelde_url=f"{BASIS}/newsletter-abgemeldet.html?t=beispiel",
            seit_datum="1. August 2026", basis_url=BASIS,
            mit_filter=not satz.ist_leer)
        (ziel / f"{name}.html").write_text(nachricht.html, encoding="utf-8")
        (ziel / f"{name}.txt").write_text(nachricht.text, encoding="utf-8")
        ueber_stichwort = sum(1 for t in treffer if t.ueber_stichwort)
        print(f"  {name:<16} {len(treffer)} Einträge"
              f"{f' (davon {ueber_stichwort} über Stichwort)' if ueber_stichwort else ''}"
              f"  – {beschreibung}")
        print(f"  {'':<16} Betreff: {nachricht.betreff}")
    print(f"\nGeschrieben nach {ziel.relative_to(WURZEL)}/")
    print("Ansehen: die .html im Browser, die .txt im Editor. Die echte "
          "Abnahme braucht Outlook, Gmail-Web und ein Telefon (N9).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
