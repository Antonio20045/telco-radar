"""Klick-Tageslauf eines Anbieters (Datenkonzept Geräteradar §8 „Betrieb“).

Liest die Produktseiten des Anbieters aus ``config/klick_tageslauf.yaml``, klickt sie
mit ``config/klickkarten/<schluessel>.yaml`` in Rotation durch und schreibt
``<ausgabe>/<schluessel>.json`` (``klickergebnis``). Die Logik steht in
``telco_radar.collect.geraete.klicktageslauf``; dieses Skript liest nur die Eingaben,
startet Chromium ohne Tarnung und stellt die Uhr.

AUFRUF
------
    PYTHONPATH=src python scripts/klick_tageslauf.py --anbieter o2 --ausgabe klick
        [--stand data/state/klick_stand.json] [--job-frist-sekunden 3600]
        [--job-start EPOCHE] [--root .] [--chromium PFAD]
    PYTHONPATH=src python scripts/klick_tageslauf.py --plan

``--job-start`` ist der Start des Jobs in Sekunden seit 1970 (``date +%s`` im ersten
Schritt); mit ``--job-frist-sekunden`` ergibt er die Restzeit (CLAUDE.md Regel 8).
``--plan`` gibt die Schlüssel aller Anbieter mit Karte als JSON-Liste aus (Matrix),
ohne Netz. Ein gestörter Anbieter ist ein Ergebnis, kein Fehler: Exit-Code 0; 2 heißt,
die Auswahl oder die Konfiguration ist falsch.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

from playwright.sync_api import sync_playwright

from telco_radar.collect import http
from telco_radar.collect.geraete.klickergebnis import (
    FORMAT,
    LAUF_NICHT_GELESEN,
    lies_stand,
    schreibe,
)
from telco_radar.collect.geraete.klickerkundung import robots_holer
from telco_radar.collect.geraete.klickkartenprobe import KARTEN, Kartenlage, lade_karte
from telco_radar.collect.geraete.klicktageslauf import (
    JOB_FRIST_S,
    budget_ende,
    crawler_im_browser,
    fahre,
)
from telco_radar.collect.geraete.klickziele import (
    TAGESDATEI,
    Erkundungsziel,
    ErkundungszielFehler,
    lade_ziele,
    waehle,
)

FEHLER_AUSWAHL = 2
STAND = Path("data") / "state" / "klick_stand.json"


def _uhr() -> datetime:
    return datetime.now(UTC)


def main(argumente: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", default=".", type=Path)
    parser.add_argument("--anbieter")
    parser.add_argument("--ausgabe", default="klick", type=Path)
    parser.add_argument("--stand", type=Path)
    parser.add_argument("--job-frist-sekunden", type=float, default=JOB_FRIST_S)
    parser.add_argument("--job-start", type=float)
    parser.add_argument("--plan", action="store_true")
    parser.add_argument("--chromium", type=Path)
    args = parser.parse_args(argumente)
    beginn = time.time()
    try:
        ziele = lade_ziele(args.root, TAGESDATEI, hoechste=None)
        if args.plan:
            mit_karte = [z.schluessel for z in ziele if _hat_karte(args.root, z)]
            print(json.dumps(mit_karte))
            return 0
        gewaehlt = waehle(ziele, args.anbieter or "")
        if not args.anbieter or len(gewaehlt) != 1:
            raise ErkundungszielFehler("--anbieter nennt genau einen Schlüssel")
        (ziel,) = gewaehlt
    except ErkundungszielFehler as fehler:
        print(f"Klick-Tageslauf: {fehler}", file=sys.stderr)
        return FEHLER_AUSWAHL
    logging.basicConfig(
        level=logging.INFO, format="%(levelname)s %(name)s: %(message)s"
    )
    heute = _uhr().date().isoformat()
    lage = lade_karte(args.root / KARTEN, ziel.schluessel)
    ziel_datei = args.ausgabe / f"{ziel.schluessel}.json"
    if lage.karte is None:
        schreibe(ziel_datei, _ohne_karte(ziel.schluessel, ziel.name, heute, lage))
        print(f"{ziel.schluessel}: {LAUF_NICHT_GELESEN} ({lage.grund})")
        return 0
    stand = lies_stand(args.stand or args.root / STAND)
    verstrichen = beginn - (args.job_start if args.job_start is not None else beginn)
    ende = budget_ende(args.job_frist_sekunden, verstrichen, time.monotonic())
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(executable_path=args.chromium)
        try:
            holer = robots_holer(ziel.kennung or http.BOT_UA)
            crawle = crawler_im_browser(browser, ziel, lage.karte, _uhr, holer)
            daten = fahre(
                ziel,
                lage.karte,
                lage.datei,
                crawle,
                heute,
                ende,
                gelesen=stand["seiten"].get(ziel.name, {}),
            )
        finally:
            browser.close()
    schreibe(ziel_datei, daten)
    grund = f" ({daten['grund']})" if daten["grund"] else ""
    print(
        f"{ziel.schluessel}: {daten['laufstatus']}{grund}, {daten['dauer_sekunden']} s"
    )
    return 0


def _hat_karte(root: Path, ziel: Erkundungsziel) -> bool:
    return (root / KARTEN / f"{ziel.schluessel}.yaml").is_file()


def _ohne_karte(schluessel: str, name: str, heute: str, lage: Kartenlage) -> dict:
    return {
        "format": FORMAT,
        "anbieter": schluessel,
        "name": name,
        "datum": heute,
        "karte": lage.datei,
        "laufstatus": LAUF_NICHT_GELESEN,
        "grund": f"Karte {lage.status}: {lage.grund}",
        "seiten": [],
    }


if __name__ == "__main__":
    sys.exit(main())
