"""Klick-Erkundung je Anbieter (Datenkonzept Geräteradar, Schritt 5a).

Holt je Anbieter aus ``config/klick_erkundung.yaml`` das Material für die Klick-Karte:
gerenderte Seite, Bedienelemente, Preis-Kandidaten, Mitschnitt, Klick-Proben und
Screenshot, nach ``<ausgabe>/<anbieter>/<JJJJ-MM-TT>/`` mit ``index.json``. Die Logik
steht in ``telco_radar.collect.geraete.klickerkundung``; dieses Skript liest nur die
Eingaben, startet Chromium ohne Tarnung und gibt je Anbieter eine Zeile aus.

AUFRUF
------
    PYTHONPATH=src python scripts/klick_erkunden.py [--anbieter alle|o2,telekom]
        [--ausgabe erkundung] [--frist-sekunden 3600] [--root .] [--chromium PFAD]
    PYTHONPATH=src python scripts/klick_erkunden.py --plan --anbieter alle

``--frist-sekunden`` ist die Gesamtfrist ab Start; jeder Anbieter bekommt höchstens
``ZEIT_JE_ANBIETER_S`` daraus. ``--plan`` prüft die Auswahl gegen die Konfiguration und
gibt die Schlüssel als JSON-Liste aus (für die Matrix des Workflows), ohne Netz. Ein
gestörter Anbieter ist ein Ergebnis, kein Fehler: der Exit-Code ist 0; 2 heißt, die
Auswahl oder die Konfiguration ist falsch. ``--chromium`` nennt eine vorhandene
Chromium-Datei für lokale Läufe ohne passenden Playwright-Browser; Actions lässt es weg.
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

from telco_radar.collect.geraete.klickerkundung import ZEIT_JE_ANBIETER_S, erkunde
from telco_radar.collect.geraete.klickziele import (
    ALLE,
    ErkundungszielFehler,
    lade_ziele,
    waehle,
)

FEHLER_AUSWAHL = 2


def _uhr() -> datetime:
    return datetime.now(UTC)


def main(argumente: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", default=".", type=Path)
    parser.add_argument("--anbieter", default=ALLE)
    parser.add_argument("--ausgabe", default="erkundung", type=Path)
    parser.add_argument("--frist-sekunden", type=float, default=ZEIT_JE_ANBIETER_S)
    parser.add_argument("--plan", action="store_true")
    parser.add_argument("--chromium", type=Path)
    args = parser.parse_args(argumente)
    try:
        ziele = waehle(lade_ziele(args.root), args.anbieter)
    except ErkundungszielFehler as fehler:
        print(f"Klick-Erkundung: {fehler}", file=sys.stderr)
        return FEHLER_AUSWAHL
    if args.plan:
        print(json.dumps([z.schluessel for z in ziele]))
        return 0
    logging.basicConfig(
        level=logging.INFO, format="%(levelname)s %(name)s: %(message)s"
    )
    ende = time.monotonic() + args.frist_sekunden
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(executable_path=args.chromium)
        try:
            indizes = erkunde(browser, ziele, _uhr, args.ausgabe, ende)
        finally:
            browser.close()
    for index in indizes:
        grund = f" ({index['grund']})" if index["grund"] else ""
        print(
            f"{index['anbieter']}: {index['status']}{grund},"
            f" {index['groesse_bytes']} Bytes, {index['dauer_sekunden']} s"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
