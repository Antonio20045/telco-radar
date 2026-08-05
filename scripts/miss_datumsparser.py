#!/usr/bin/env python3
"""Misst, was die Erweiterung des Datums-Parsers wirklich bringt.

Warum es diese Messung gibt
---------------------------
AUFTRAG_1000_QUELLEN_WELLE3.md Abschnitt 4.2 verlangt sie ausdruecklich:
"Miss vorher und nachher: wie viele der abgelehnten Kandidaten bestehen nach
der Erweiterung?" In Welle 2 lieferten 82 Kandidaten Meldungen und fielen NUR
am Datumsformat durch (Kriterium 3, >= 80 % datiert). Das sind Parser-Luecken,
keine schlechten Quellen - eine undatierte Meldung sortiert im Lauf ans Ende
und wird faktisch nie bewertet.

Wie gemessen wird
-----------------
Jede Quelle wird EINMAL abgerufen und dann ZWEIMAL geparst: einmal mit dem
heutigen Parser, einmal mit den Tabellen und Mustern von vor Welle 3. Beide
Male auf demselben HTML - so misst der Vergleich den Parser und nicht die
Tagesform des Servers. Ein Nacheinander ("erst pruefen, dann erweitern, dann
nochmal pruefen") haette beides vermischt.

Aufruf
------
    python scripts/miss_datumsparser.py kandidaten.yaml
    python scripts/miss_datumsparser.py kandidaten.yaml --json messung.json
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from telco_radar.collect import newsroom  # noqa: E402
from telco_radar.collect.http import configure_throttle, fetch  # noqa: E402
from telco_radar.config import Source  # noqa: E402

# Kriterium 3 des Abnahme-Checks. Hier gespiegelt statt importiert, damit die
# Messung auch dann laeuft, wenn am Check gerade gearbeitet wird.
MIN_DATED_SHARE = 0.80

# --------------------------------------------------------------------------- #
# Der Stand VOR Welle 3, woertlich aus der damaligen Fassung von
# collect/newsroom.py. Das ist die Vergleichsgroesse - sie steht hier und nicht
# in der Versionsgeschichte, damit die Messung jederzeit wiederholbar ist.
# --------------------------------------------------------------------------- #
ALT_MONTHS = {m: i + 1 for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun",
     "jul", "aug", "sep", "oct", "nov", "dec"])}
ALT_MONTHS.update({
    "ene": 1, "abr": 4, "ago": 8, "set": 9, "dic": 12,
    "fev": 2, "mai": 5, "out": 10, "dez": 12,
    "mär": 3, "okt": 10,
    "mei": 5, "agu": 8, "des": 12,
    "oca": 1, "şub": 2, "sub": 2, "nis": 4, "haz": 6, "tem": 7,
    "ağu": 8, "eyl": 9, "eki": 10, "kas": 11, "ara": 12,
    "fév": 2, "avr": 4, "aoû": 8, "aou": 8, "déc": 12,
})
ALT_TEXT_DATE = re.compile(
    r"\b(0?[1-9]|[12]\d|3[01])(?:st|nd|rd|th)?[./\s]+(?:de\s+)?"
    r"(0?[1-9]|1[0-2]|[^\W\d_]{3,12})[./\s,]+(?:de\s+)?(20\d{2})\b", re.I)
ALT_TEXT_DATE_MDY = re.compile(
    r"\b(Jan\w*|Feb\w*|Mar\w*|Apr\w*|May|Jun\w*|Jul\w*|Aug\w*|"
    r"Sep\w*|Oct\w*|Nov\w*|Dec\w*)\s+(0?[1-9]|[12]\d|3[01])"
    r"(?:st|nd|rd|th)?[./\s,]+(20\d{2})\b", re.I)
# Ein Muster, das nie trifft - so verhalten sich die drei NEUEN Muster
# (Jahr-zuerst, CJK, vietnamesisch) im Alt-Zustand.
NIE = re.compile(r"(?!x)x")


@contextmanager
def alter_parser():
    """Den Parser voruebergehend auf den Stand vor Welle 3 zuruecksetzen."""
    gesichert = {name: getattr(newsroom, name) for name in (
        "_MONATSSTAEMME", "_STAMM_MAX", "_TEXT_DATE", "_TEXT_DATE_MDY",
        "_TEXT_DATE_YMD_WORT", "_TEXT_DATE_CJK", "_TEXT_DATE_VI")}
    newsroom._MONATSSTAEMME = dict(ALT_MONTHS)
    newsroom._STAMM_MAX = max(len(s) for s in ALT_MONTHS)
    newsroom._TEXT_DATE = ALT_TEXT_DATE
    newsroom._TEXT_DATE_MDY = ALT_TEXT_DATE_MDY
    newsroom._TEXT_DATE_YMD_WORT = NIE
    newsroom._TEXT_DATE_CJK = NIE
    newsroom._TEXT_DATE_VI = NIE
    try:
        yield
    finally:
        for name, wert in gesichert.items():
            setattr(newsroom, name, wert)


def _quelle(kandidat: dict) -> Source:
    return Source(
        type=kandidat.get("type", "newsroom"),
        url=kandidat["url"],
        name=kandidat.get("operator") or kandidat.get("name") or "",
        kind=kandidat.get("type", "newsroom"),
        item_selector=kandidat.get("item_selector"),
        allow_short_titles=bool(kandidat.get("allow_short_titles")),
    )


def _hole(kandidat: dict) -> str:
    try:
        return fetch(kandidat["url"], {"timeout_seconds": 20}).text or ""
    except Exception:  # noqa: BLE001
        return ""


def _datiert(html: str, kandidat: dict) -> tuple[int, int]:
    """(Meldungen, davon datiert) mit dem gerade eingestellten Parser."""
    try:
        items = newsroom.parse_newsroom_html(
            html, _quelle(kandidat), "europe", None, "operator")
    except Exception:  # noqa: BLE001
        return 0, 0
    return len(items), sum(1 for i in items if i.published)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("datei", type=Path, help="Kandidaten-YAML aus finde_quellen.py")
    p.add_argument("--json", type=Path)
    p.add_argument("--workers", type=int, default=12)
    args = p.parse_args(argv)

    configure_throttle(4, 0.2)
    roh = yaml.safe_load(args.datei.read_text(encoding="utf-8")) or {}
    kandidaten = [k for k in (roh.get("kandidaten") or roh)
                  if k.get("type") == "newsroom"]
    if not kandidaten:
        print("Keine newsroom-Kandidaten in der Datei - "
              "die Messung betrifft nur geparste Seiten.")
        return 0
    print(f"{len(kandidaten)} newsroom-Kandidaten werden einmal abgerufen "
          f"und zweimal geparst")

    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
        seiten = list(pool.map(_hole, kandidaten))

    # Erst ALLE alt, dann alle neu: der Kontextwechsel veraendert Modulzustand,
    # der bei nebenlaeufigem Parsen nicht sauber waere.
    with alter_parser():
        alt = [_datiert(html, k) for html, k in zip(seiten, kandidaten)]
    neu = [_datiert(html, k) for html, k in zip(seiten, kandidaten)]

    zeilen = []
    for k, (n_a, d_a), (n_n, d_n) in zip(kandidaten, alt, neu):
        anteil_a = d_a / n_a if n_a else 0.0
        anteil_n = d_n / n_n if n_n else 0.0
        zeilen.append({
            "url": k["url"],
            "bezeichnung": k.get("operator") or k.get("name") or "",
            "n_items": n_n,
            "datiert_alt": d_a, "datiert_neu": d_n,
            "anteil_alt": round(anteil_a, 3), "anteil_neu": round(anteil_n, 3),
            "k3_alt": n_a > 0 and anteil_a >= MIN_DATED_SHARE,
            "k3_neu": n_n > 0 and anteil_n >= MIN_DATED_SHARE,
        })

    gewonnen = [z for z in zeilen if z["k3_neu"] and not z["k3_alt"]]
    verloren = [z for z in zeilen if z["k3_alt"] and not z["k3_neu"]]
    besser = [z for z in zeilen if z["datiert_neu"] > z["datiert_alt"]]

    print()
    print(f"{'K3 alt':>7} {'K3 neu':>7} {'DAT alt':>8} {'DAT neu':>8}  URL")
    print("-" * 120)
    for z in sorted(zeilen, key=lambda x: (x["k3_neu"] - x["k3_alt"]),
                    reverse=True):
        if z["datiert_neu"] == z["datiert_alt"]:
            continue
        print(f"{'ja' if z['k3_alt'] else 'nein':>7} "
              f"{'ja' if z['k3_neu'] else 'nein':>7} "
              f"{z['datiert_alt']:>8} {z['datiert_neu']:>8}  {z['url']}")
    print("-" * 120)
    print(f"Kandidaten geprueft:                     {len(zeilen)}")
    print(f"Kriterium 3 vorher bestanden:            "
          f"{sum(1 for z in zeilen if z['k3_alt'])}")
    print(f"Kriterium 3 nachher bestanden:           "
          f"{sum(1 for z in zeilen if z['k3_neu'])}")
    print(f"davon NEU bestanden (der Gewinn):        {len(gewonnen)}")
    print(f"durch die Erweiterung verloren:          {len(verloren)}")
    print(f"Quellen mit mehr datierten Meldungen:    {len(besser)}")
    print(f"datierte Meldungen gesamt vorher/nachher: "
          f"{sum(z['datiert_alt'] for z in zeilen)} / "
          f"{sum(z['datiert_neu'] for z in zeilen)}")

    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(zeilen, ensure_ascii=False, indent=1),
                             encoding="utf-8")
        print(f"Ergebnis geschrieben: {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
