"""Belegbilder des Klick-Tageslaufs in GitHub-Releases legen (Job ``belege`` von
``klick.yml``).

AUFRUF
------
    PYTHONPATH=src python scripts/belege_veroeffentlichen.py --quelle klick-artefakte
        [--root .] [--job-frist-sekunden 2100] [--job-start EPOCHE] [--heute JJJJ-MM-TT]

``--quelle`` enthält je Anbieter die Ergebnisdatei und die WebP-Bilder (``belegbild``),
in beliebig tiefen Unterordnern. Je (Gerät, Anbieter) wählt ``beleg_schluessel`` den
Preis mit den niedrigsten Gesamtkosten; sein Bild heißt
``<geraet_id>__<anbieter_id>__<JJJJ-MM-TT>__preis__<kennung>.webp``
(``beleg_regeln.folge_dateiname``; Gerät aus dem Katalog, Anbieter als ASCII-Schlüssel,
Kennung aus der ``beleg_id``). Nur ohne brauchbare ``beleg_id`` bleibt es beim Namen
ohne Kennung (``beleg_regeln.dateiname``): ein Einzelbild ohne Folge.
``beleg_ablage.veroeffentliche`` lädt es ins Release ``belege-JJJJ-MM-TT``, eine große
Änderung zusätzlich in ``belege-gross-JJJJ-MM``. Die Folgebilder derselben Position
(``<beleg_id>_<schritt>.webp`` im Artefakt, ``belegbild.folgename``) gehen denselben
Weg, in dieselben Releases und mit denselben Grenzen hoch, mit derselben Kennung im
Namen: Einzelbild und Schritte einer Position bilden eine Folge, nie die einer
anderen. Dieser Job löscht nichts: Bilder einer früheren Position desselben Paares und
Tages bleiben liegen, bis der Gerätelauf das Manifest auf die neuen Bilder gestellt hat
und sie danach löscht (``beleg_veraltet``, ``scripts/belege_manifest.py``); das
eingecheckte Manifest zeigt so nie auf gelöschte Dateien. Es gibt keine Indexdatei und
keinen Commit: die Seite liest die Anhänge der Releases
(``scripts/belege_manifest.py``). Das Token liegt nur in ``GH_TOKEN``.

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

from telco_radar.analyze.beleg_schluessel import Messung, ist_besser, ordne_zu
from telco_radar.beleg_ablage import (
    ZEIT_JE_AUFRUF_S,
    Bild,
    Gh,
    Releases,
    veroeffentliche,
)
from telco_radar.beleg_bildfolge import PREIS
from telco_radar.beleg_regeln import (
    anbieter_schluessel,
    dateiname,
    folge_dateiname,
    ist_grosse_aenderung,
    zerlege_dateiname,
)
from telco_radar.collect.geraete.belegbild import folgename, zwischenname
from telco_radar.collect.geraete.klickbildfolge import GEWAEHLT
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
    """Bilder zu den gewählten Preisen mit endgültigem Namen in ``ziel`` (und Log).

    Ein Anbieter läuft in mehreren Matrix-Jobs (telekom, telekom-2 …), die dasselbe
    Gerät messen: derselbe Dateiname kommt mehrfach vor. Je Name zählt der niedrigste
    Preis über alle Ergebnisse, sonst scheitert ``gh --clobber`` (HTTP 404).
    """
    dateien = {p.name: p for p in sorted(quelle.rglob("*.webp"))}
    gewaehlt: dict[str, tuple[Messung, Path]] = {}
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
            alt = gewaehlt.get(name)
            if alt is None or ist_besser(messung, alt[0]):
                gewaehlt[name] = (messung, roh)
        zeilen.append(
            f"{daten.get('anbieter')}: {len(zuordnung.messungen)} Preise, "
            f"{ohne_datei} ohne Bild, {unbrauchbar} ohne Dateiname, "
            f"{zuordnung.mehrdeutig} weitere Tarife, "
            f"{sum(zuordnung.uebersprungen.values())} übersprungen"
        )
    bilder: list[Bild] = []
    folgebilder = 0
    for name, (messung, roh) in sorted(gewaehlt.items()):
        datei = ziel / einzelbild_name(messung, name, zeilen)
        shutil.copyfile(roh, datei)
        gross = ist_grosse_aenderung(messung.vorher_24, messung.gesamt_24)
        bilder.append(Bild(datei, gross))
        folge = sammle_folge(messung, name, dateien, ziel, gross, zeilen)
        bilder += folge
        folgebilder += len(folge)
    zeilen.append(
        f"{len(bilder) - folgebilder} Bilder und {folgebilder} Folgebilder nach "
        "Zusammenführen der Ergebnisse"
    )
    return bilder, zeilen


def einzelbild_name(messung: Messung, name: str, zeilen: list[str]) -> str:
    """Der veröffentlichte Name des Einzelbilds: der Preisschritt mit der Kennung der
    Position (``…__preis__<kennung>.webp``), damit es zu seiner Folge gehört und zu
    keiner anderen. Ohne brauchbare ``beleg_id`` bleibt es beim Namen ohne Kennung (ein
    Einzelbild ohne Folge, nichts geht verloren)."""
    zerlegt = zerlege_dateiname(name)
    if zerlegt is None:
        return name
    try:
        return folge_dateiname(
            zerlegt.geraet_id,
            zerlegt.anbieter_id,
            zerlegt.datum,
            PREIS,
            messung.beleg_id,
        )
    except ValueError as fehler:
        zeilen.append(f"{name}: ohne Kennung veröffentlicht: {fehler}")
        return name


def sammle_folge(
    messung: Messung,
    einzelname: str,
    dateien: dict[str, Path],
    ziel: Path,
    gross: bool,
    zeilen: list[str],
) -> list[Bild]:
    """Die Folgebilder der gewählten Position unter ihrem endgültigen Namen.

    Gerät und Anbieter stehen im Namen des Einzelbilds. Ein Schritt ohne Datei im
    Artefakt fehlt einfach (die Seite nennt ihn); es gibt keinen Ersatz aus einer
    anderen Position."""
    zerlegt = zerlege_dateiname(einzelname)
    folge: list[Bild] = []
    if zerlegt is None:
        return folge
    for schritt in GEWAEHLT:
        roh = dateien.get(folgename(messung.beleg_id, schritt))
        if roh is None:
            continue
        try:
            name = folge_dateiname(
                zerlegt.geraet_id,
                zerlegt.anbieter_id,
                zerlegt.datum,
                schritt,
                messung.beleg_id,
            )
        except ValueError as fehler:
            zeilen.append(f"{einzelname}: kein Dateiname für {schritt}: {fehler}")
            continue
        datei = ziel / name
        shutil.copyfile(roh, datei)
        folge.append(Bild(datei, gross))
    return folge


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
        releases = gh or Gh()
        bilanz = veroeffentliche(bilder, heute, releases, frist_ende=ende)
    for zeile in bilanz.zeilen()[:1] + bilanz.hinweise():
        print(zeile)
    for zeile in bilanz.fehler:
        print(f"Belege: {zeile}", file=sys.stderr)
    return FEHLER_TEIL if bilanz.fehler or bilanz.ausgelassen else 0


if __name__ == "__main__":
    sys.exit(main())
