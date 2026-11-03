"""Belegbilder des Klick-Tageslaufs in GitHub-Releases legen (Job ``belege`` von
``klick.yml``).

AUFRUF
------
    PYTHONPATH=src python scripts/belege_veroeffentlichen.py --quelle klick-artefakte
        [--root .] [--job-frist-sekunden 2100] [--job-start EPOCHE] [--heute JJJJ-MM-TT]

``--quelle`` enthält je Anbieter die Ergebnisdatei und die WebP-Bilder (``belegbild``),
in beliebig tiefen Unterordnern. Je (Gerät, Anbieter) wählt ``beleg_schluessel`` den
Preis mit den niedrigsten Gesamtkosten; das Bild heißt dann
``<geraet_id>__<anbieter_id>__<JJJJ-MM-TT>.webp`` (``beleg_regeln.dateiname``, Gerät aus
dem Katalog, Anbieter als ASCII-Schlüssel). ``beleg_ablage.veroeffentliche`` lädt es ins
Release ``belege-JJJJ-MM-TT``, eine große Änderung zusätzlich in
``belege-gross-JJJJ-MM``. Es gibt keine Indexdatei und keinen Commit: die Seite liest
die Anhänge der Releases (``scripts/belege_manifest.py``). Das Token liegt nur in
``GH_TOKEN``.

Exit-Code 0: alles getan oder nichts zu tun (auch ohne Artefakt); 1: ein Teil ist
gescheitert; 2: Eingabe oder Konfiguration falsch.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
import time
from datetime import UTC, date, datetime
from pathlib import Path

from telco_radar.analyze.beleg_schluessel import ordne_zu
from telco_radar.beleg_ablage import (
    ZEIT_JE_AUFRUF_S,
    Bild,
    Gh,
    Releases,
    veroeffentliche,
)
from telco_radar.beleg_regeln import (
    anbieter_schluessel,
    dateiname,
    ist_grosse_aenderung,
)
from telco_radar.collect.geraete.belegbild import zwischenname
from telco_radar.collect.geraete.klickrohsatz import ausbeute
from telco_radar.geraete_config import lade_katalog
from telco_radar.klick_vertrag import lies_ergebnisse
from telco_radar.report.geraete_tco_karten import geraet_aus_sku, modell_schluessel

FEHLER_TEIL = 1
FEHLER_EINGABE = 2
TCO_DATEI = Path("data") / "state" / "geraete_tco.json"
JOB_MINUTEN = 40
"""``timeout-minutes`` des Jobs ``belege`` in ``klick.yml`` (ein Test prüft es)."""
PUFFER_S = 300
"""Reserve nach dem letzten Aufruf: Skriptende, Aufräumen des Läufers."""
JOB_ENDE_S = JOB_MINUTEN * 60 - PUFFER_S
"""Bis hierhin soll alles fertig sein (Standard von ``--job-frist-sekunden``)."""
JOB_FRIST_S = JOB_ENDE_S - ZEIT_JE_AUFRUF_S
"""Bis hierhin darf ein neues Paket beginnen. Ein Aufruf, der kurz davor beginnt, darf
``ZEIT_JE_AUFRUF_S`` laufen; danach bleibt ``PUFFER_S`` bis zum Zeitlimit des Jobs."""


def wirksame_frist(uebergeben_s: float) -> float:
    """Bis wann (Sekunden seit Jobstart) ein neues Paket beginnen darf.

    ``--job-frist-sekunden`` ist das Ende, bis zu dem alles fertig sein soll: ein
    Aufruf, der kurz davor beginnt, darf noch ``ZEIT_JE_AUFRUF_S`` laufen, also zählt
    die Frist abzüglich dieser Zeit. Nie mehr als ``JOB_FRIST_S``: auch bei einem
    zu großen Argument bleibt der Puffer vor dem Job-Timeout (die Workflow-Datei muss
    dafür nicht stimmen). Nie unter 0."""
    return max(0.0, min(uebergeben_s - ZEIT_JE_AUFRUF_S, JOB_FRIST_S))


def sammle_bilder(
    ergebnisse: list[dict],
    quelle: Path,
    ziel: Path,
    bestand: list[dict],
    katalog,
    heute: date,
) -> tuple[list[Bild], list[str]]:
    """Bilder zu den gewählten Preisen mit endgültigem Namen in ``ziel`` (und Log)."""
    dateien = {p.name: p for p in sorted(quelle.rglob("*.webp"))}
    bilder: list[Bild] = []
    zeilen: list[str] = []
    for daten in ergebnisse:
        rohsaetze = ausbeute(daten, katalog).rohsaetze
        zuordnung = ordne_zu(
            rohsaetze, bestand, lambda sku: geraet_aus_sku(sku, katalog)
        )
        ohne_datei = unbrauchbar = 0
        for messung in zuordnung.messungen:
            roh = dateien.get(zwischenname(messung.beleg_id))
            if roh is None:
                ohne_datei += 1
                continue
            try:
                name = dateiname(
                    modell_schluessel(messung.device_id, messung.speicher_gb),
                    anbieter_schluessel(messung.anbieter),
                    heute,
                )
            except ValueError as fehler:
                unbrauchbar += 1
                zeilen.append(f"{daten.get('anbieter')}: kein Dateiname: {fehler}")
                continue
            datei = ziel / name
            shutil.copyfile(roh, datei)
            bilder.append(
                Bild(datei, ist_grosse_aenderung(messung.vorher_24, messung.gesamt_24))
            )
        zeilen.append(
            f"{daten.get('anbieter')}: {len(zuordnung.messungen)} Preise, "
            f"{ohne_datei} ohne Bild, {unbrauchbar} ohne Dateiname, "
            f"{zuordnung.mehrdeutig} weitere Tarife, "
            f"{sum(zuordnung.uebersprungen.values())} übersprungen"
        )
    return bilder, zeilen


def main(argumente: list[str] | None = None, gh: Releases | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", default=".", type=Path)
    parser.add_argument("--quelle", required=True, type=Path)
    parser.add_argument("--job-frist-sekunden", type=float, default=JOB_ENDE_S)
    parser.add_argument("--job-start", type=float)
    parser.add_argument("--heute", type=date.fromisoformat)
    args = parser.parse_args(argumente)
    beginn = time.time()
    heute = args.heute or datetime.now(UTC).date()
    verstrichen = max(
        0.0, beginn - (args.job_start if args.job_start is not None else beginn)
    )
    ende = time.monotonic() + max(
        0.0, wirksame_frist(args.job_frist_sekunden) - verstrichen
    )
    try:
        bestand = json.loads((args.root / TCO_DATEI).read_text(encoding="utf-8"))[
            "buendel"
        ]
        katalog = lade_katalog(args.root)
    except (OSError, ValueError, KeyError) as fehler:
        print(f"Belege: Eingabe unlesbar: {fehler}", file=sys.stderr)
        return FEHLER_EINGABE
    if not args.quelle.is_dir():
        print(f"Belege: kein Ordner {args.quelle}, nichts hochzuladen")
        return 0
    ergebnisse, unlesbar = lies_ergebnisse(args.quelle)
    with tempfile.TemporaryDirectory() as ordner:
        bilder, zeilen = sammle_bilder(
            ergebnisse, args.quelle, Path(ordner), bestand, katalog, heute
        )
        for zeile in [*zeilen, *(f"unlesbar: {z}" for z in unlesbar)]:
            print(f"Belege {zeile}")
        bilanz = veroeffentliche(bilder, heute, gh or Gh(), frist_ende=ende)
    for zeile in bilanz.zeilen()[:1]:
        print(zeile)
    for zeile in bilanz.fehler:
        print(f"Belege: {zeile}", file=sys.stderr)
    return FEHLER_TEIL if bilanz.fehler or bilanz.ausgelassen else 0


if __name__ == "__main__":
    sys.exit(main())
