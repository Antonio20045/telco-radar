"""Release-Anhänge lesen, Abgelaufenes löschen, Manifest für die Seite schreiben
(``geraete.yml``).

AUFRUF
------
    PYTHONPATH=src python scripts/belege_manifest.py [--root .] [--heute JJJJ-MM-TT]
        [--nur-lesen] [--melde-ausfall GRUND]

Die Anhänge der Releases ``belege-JJJJ-MM-TT`` und ``belege-gross-JJJJ-MM`` sind die
einzige Quelle der Wahrheit (``beleg_ablage``). Das Skript löscht, was nach
``beleg_regeln`` abgelaufen ist (Tages-Releases nach 7 Tagen, große Änderungen nach 90),
und schreibt aus dem Rest ``data/state/belege_manifest.json`` (``beleg_manifest``). Von
Hand hochgeladene Bilder mit richtigem Namen stehen nach dem nächsten Lauf auf der
Seite. ``--nur-lesen`` löscht nichts. ``--melde-ausfall GRUND`` rührt kein GitHub an
und vermerkt nur im bestehenden Manifest, dass es nicht erneuert wurde (Handarbeit
und Notweg); die Seite nennt den Grund als Ausfall.

Frist und Exit-Code: Der Schritt in ``geraete.yml`` hat 5 min und darf den Commit
des Messtags nie sperren, und die Workflow-Datei bleibt, wie sie ist. Deshalb hält
das Skript selbst ``GESAMT_FRIST_S`` ein: Das Timeout jedes ``gh``-Aufrufs ist die
Restzeit (``beleg_ablage.runner_mit_frist``), ein Alarm (``wachhund``) beendet auch
alles andere. Jeder Fehler, auch ein Zeitüberschreiten, steht auf stderr und als
``ausfall`` im Manifest (die Seite nennt ihn; die letzten Bilder bleiben stehen,
CLAUDE.md Clean Code 5), und der Exit-Code ist 0. Nur ein falscher Aufruf (argparse)
endet mit 2. Löschen, das scheitert, schreibt das Manifest trotzdem: die nicht
gelöschten Bilder sind abgelaufen und fallen darin schon heraus. Das Token liegt nur
in ``GH_TOKEN``. Der Workflow committet die Manifestdatei, dieses Skript nicht.
"""

from __future__ import annotations

import argparse
import signal
import subprocess
import sys
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import UTC, date, datetime
from pathlib import Path

from telco_radar.beleg_ablage import (
    Bilanz,
    Gh,
    GhFehler,
    Releases,
    raeume_auf,
    runner_mit_frist,
)
from telco_radar.beleg_folgen import lies_folgen
from telco_radar.beleg_manifest import (
    MANIFEST_DATEI,
    baue_manifest,
    markiere_ausfall,
    schreibe,
)
from telco_radar.klick_vertrag import ORDNER as KLICK_ORDNER
from telco_radar.klick_vertrag import lies_ergebnisse

SCHRITT_FRIST_S = 300
"""``timeout-minutes`` des Schritts „Belege-Manifest“ in ``geraete.yml`` (5 min)."""
GESAMT_FRIST_S = 200
"""Harte Frist des ganzen Skripts, deutlich unter ``SCHRITT_FRIST_S`` (ein Wächter
prüft es): dann ist der Schritt fertig, bevor GitHub ihn abbricht und der Commit des
Messtags verlorengeht."""
SCHREIB_RESERVE_S = 20
"""Davon gehen die ``gh``-Aufrufe nicht auf: Platz für Manifest und Ausfallvermerk."""
OK = 0
FEHLER_FRIST_ODER_LAUF = (
    GhFehler,
    OSError,
    ValueError,
    KeyError,
    TypeError,
    subprocess.SubprocessError,
)
"""Alles, was ein Lauf über ``gh`` und Dateien erwartbar wirft: wird Ausfall im
Manifest, nie ein Abbruch des Schritts. Programmierfehler gehören nicht dazu."""


class Gesamtfrist(Exception):
    """``GESAMT_FRIST_S`` ist abgelaufen, bevor das Skript fertig war."""


@contextmanager
def wachhund(sekunden: float) -> Iterator[None]:
    """Wirft nach ``sekunden`` ``Gesamtfrist`` im Hauptfaden (wo ``gh`` auch hängt).

    Ohne ``SIGALRM`` (Windows) bleibt nur das Timeout der einzelnen Aufrufe."""
    if not hasattr(signal, "SIGALRM"):
        yield
        return

    def alarm(signum: int, frame: object) -> None:
        raise Gesamtfrist(f"Gesamtfrist von {sekunden:.0f} s überschritten")

    alt = signal.signal(signal.SIGALRM, alarm)
    signal.setitimer(signal.ITIMER_REAL, sekunden)
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, alt)


def erneuere(root: Path, heute: date, nur_lesen: bool, gh: Releases) -> str | None:
    """Liest, räumt auf, schreibt das Manifest; gibt den Ausfallgrund zurück oder
    ``None``."""
    try:
        anhaenge = gh.anhaenge()
    except GhFehler as fehler:
        return f"Releases nicht lesbar: {fehler}"
    bilanz = Bilanz()
    if not nur_lesen:
        bilanz, anhaenge = raeume_auf(anhaenge, heute, gh)
    ergebnisse, unlesbar = lies_ergebnisse(root / KLICK_ORDNER)
    for zeile in unlesbar:
        print(
            f"Belege: Klick-Ergebnis für die Beschriftung unlesbar: {zeile}",
            file=sys.stderr,
        )
    manifest = baue_manifest(anhaenge, heute, lies_folgen(ergebnisse))
    schreibe(root / MANIFEST_DATEI, manifest)
    gross = sum(1 for b in manifest["belege"] if b["gross"])
    print(
        f"Belege: {len(manifest['belege'])} Bilder im Manifest, davon {gross} große "
        f"Änderungen, {sum(1 for b in manifest['belege'] if b.get('bildfolge'))} mit "
        f"Bildfolge, {manifest.get('folge_verworfen', 0)} Folgen verworfen, "
        f"{manifest['fremd']} fremde Dateien; "
        f"{len(bilanz.releases_geloescht)} "
        f"Releases und {bilanz.assets_geloescht} Dateien gelöscht"
    )
    for zeile in bilanz.fehler:
        print(f"Belege: {zeile}", file=sys.stderr)
    if bilanz.fehler:
        return f"Löschen gescheitert ({len(bilanz.fehler)}): {bilanz.fehler[0]}"
    return None


def vermerke_ausfall(root: Path, grund: str, heute: date) -> None:
    """Grund auf stderr und im Manifest; scheitert auch das, steht es im Log."""
    print(f"::error::Belege-Manifest nicht erneuert: {grund}", file=sys.stderr)
    try:
        markiere_ausfall(root / MANIFEST_DATEI, grund, heute)
    except OSError as fehler:
        print(f"Belege: Ausfallvermerk nicht geschrieben: {fehler}", file=sys.stderr)


def main(
    argumente: list[str] | None = None,
    gh: Releases | None = None,
    lauf: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", default=".", type=Path)
    parser.add_argument("--heute", type=date.fromisoformat)
    parser.add_argument("--nur-lesen", action="store_true")
    parser.add_argument("--melde-ausfall", metavar="GRUND")
    args = parser.parse_args(argumente)
    heute = args.heute or datetime.now(UTC).date()
    if args.melde_ausfall:
        vermerke_ausfall(args.root, args.melde_ausfall, heute)
        return OK
    ende = time.monotonic() + GESAMT_FRIST_S - SCHREIB_RESERVE_S
    gh = gh or Gh(runner_mit_frist(ende, lauf=lauf))
    try:
        with wachhund(GESAMT_FRIST_S):
            grund = erneuere(args.root, heute, args.nur_lesen, gh)
    except (Gesamtfrist, *FEHLER_FRIST_ODER_LAUF) as fehler:
        grund = f"{type(fehler).__name__}: {fehler}"
    if grund:
        vermerke_ausfall(args.root, grund, heute)
    return OK


if __name__ == "__main__":
    sys.exit(main())
