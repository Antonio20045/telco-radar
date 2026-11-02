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
und vermerkt nur im bestehenden Manifest, dass es nicht erneuert wurde (der Workflow
ruft es, wenn dieses Skript hängt oder abbricht); die Seite nennt den Grund als Ausfall.

Kann ``gh`` die Releases nicht lesen, bleiben die Bilder des Manifests stehen, es erhält
den Vermerk ``ausfall``, und der Exit-Code ist 1: die Seite zeigt dann den letzten
Stand, nicht „keine Belege“ (CLAUDE.md Clean Code 5). Löschen, das scheitert, gibt Exit
1, das Manifest wird trotzdem geschrieben: die nicht gelöschten Bilder sind abgelaufen
und fallen darin schon heraus. Das Token liegt nur in ``GH_TOKEN``. Der Workflow
committet die Manifestdatei, dieses Skript nicht.
"""

from __future__ import annotations

import argparse
import sys
from datetime import UTC, date, datetime
from pathlib import Path

from telco_radar.beleg_ablage import Bilanz, Gh, GhFehler, Releases, raeume_auf
from telco_radar.beleg_manifest import (
    MANIFEST_DATEI,
    baue_manifest,
    markiere_ausfall,
    schreibe,
)

FEHLER = 1


def main(argumente: list[str] | None = None, gh: Releases | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", default=".", type=Path)
    parser.add_argument("--heute", type=date.fromisoformat)
    parser.add_argument("--nur-lesen", action="store_true")
    parser.add_argument("--melde-ausfall", metavar="GRUND")
    args = parser.parse_args(argumente)
    heute = args.heute or datetime.now(UTC).date()
    if args.melde_ausfall:
        markiere_ausfall(args.root / MANIFEST_DATEI, args.melde_ausfall, heute)
        print(f"Belege: Ausfall vermerkt: {args.melde_ausfall}", file=sys.stderr)
        return FEHLER
    gh = gh or Gh()
    try:
        anhaenge = gh.anhaenge()
    except GhFehler as fehler:
        print(
            f"Belege: Releases nicht lesbar, Manifest bleibt: {fehler}", file=sys.stderr
        )
        markiere_ausfall(
            args.root / MANIFEST_DATEI, f"Releases nicht lesbar: {fehler}", heute
        )
        return FEHLER
    bilanz = Bilanz()
    if not args.nur_lesen:
        bilanz, anhaenge = raeume_auf(anhaenge, heute, gh)
    manifest = baue_manifest(anhaenge, heute)
    schreibe(args.root / MANIFEST_DATEI, manifest)
    gross = sum(1 for b in manifest["belege"] if b["gross"])
    print(
        f"Belege: {len(manifest['belege'])} Bilder im Manifest, davon {gross} große "
        f"Änderungen, {manifest['fremd']} fremde Dateien; "
        f"{len(bilanz.releases_geloescht)} "
        f"Releases und {bilanz.assets_geloescht} Dateien gelöscht"
    )
    for zeile in bilanz.fehler:
        print(f"Belege: {zeile}", file=sys.stderr)
    return FEHLER if bilanz.fehler else 0


if __name__ == "__main__":
    sys.exit(main())
