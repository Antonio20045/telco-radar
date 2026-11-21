"""Legt die Teildateien der Gegenprobe-Matrix ab (Job ``ablegen``, ``gegenprobe.yml``).

AUFRUF
------
    PYTHONPATH=src python scripts/gegenprobe_ablegen.py --root . --quelle TEILE
        [--erwartet '["o2", "telekom"]']

Jeder Anbieter-Job schreibt ``<job>.jsonl`` (seine Zeilen) und ``<job>.lauf.json``
(Besuche, Sekunden, Ausfall) und lädt beide als Artefakt hoch; ``download-artifact``
legt je Artefakt einen Unterordner unter ``TEILE`` an. Dieses Skript sucht beide
Dateiarten rekursiv, gruppiert nach Messtag und gibt sie
``gegenprobe_bilanz.lege_ab``: Tagesdatei ergänzen, Läufe fortschreiben, Bilanz neu
rechnen. Nur dieser Job schreibt nach ``data/state/gegenprobe``; die Matrix-Jobs
überschreiben einander so nie. Wie ``klick_ablegen.py`` für den Klick-Lauf.
``--erwartet`` nennt die Jobs des Plans: fehlt die Teildatei eines Jobs (Abbruch,
Zeitlimit), steht für jeden seiner Anbieter ein Lauf ohne Messung mit Grund in der
Bilanz (Besuche None, nie 0).

Exit-Code 0: abgelegt; 1: eine Teildatei unlesbar (die lesbaren sind abgelegt);
2: Bestand unlesbar.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

from telco_radar import gegenprobe as gp
from telco_radar import gegenprobe_fenster as gf
from telco_radar.gegenprobe_bilanz import angezeigte, lege_ab

TCO_DATEI = Path("data") / "state" / "geraete_tco.json"
FEHLER_TEIL = 1
FEHLER_EINGABE = 2
LAUF_ENDUNG = ".lauf.json"
GRUND_TEIL_FEHLT = "Teildatei des Jobs fehlt (Abbruch oder Zeitlimit), nicht gemessen"


def fehlende(quelle: Path, erwartet: list[str], datum: str) -> list[dict]:
    """Je Anbieter eines erwarteten Jobs ohne Teildatei ein Lauf ohne Messung."""
    da = {p.name.removesuffix(LAUF_ENDUNG) for p in quelle.rglob(f"*{LAUF_ENDUNG}")}
    return [
        dict.fromkeys(("besuche", "sekunden", "buendel"))
        | {"datum": datum, "anbieter": s, "ausfall": GRUND_TEIL_FEHLT}
        for job in erwartet
        if job not in da
        for s in sorted(gf.schluessel_der_jobs([job]) or ())
    ]


def teile(quelle: Path) -> tuple[dict[str, list], dict[str, list], list[str]]:
    """(Zeilen je Tag, Läufe je Tag, unlesbare Dateien) aller Teildateien."""
    zeilen: dict[str, list] = defaultdict(list)
    laeufe: dict[str, list] = defaultdict(list)
    fehler: list[str] = []
    for pfad in sorted(quelle.rglob("*.jsonl")):
        try:
            for e in gp.lies_tag(pfad):
                zeilen[e.datum].append(e)
        except gp.GegenprobeFehler as problem:
            fehler.append(str(problem))
    for pfad in sorted(quelle.rglob(f"*{LAUF_ENDUNG}")):
        try:
            for lauf in json.loads(pfad.read_text(encoding="utf-8")):
                laeufe[str(lauf["datum"])].append(lauf)
        except (ValueError, TypeError, KeyError) as problem:
            fehler.append(f"{pfad.name}: {problem}")
    return zeilen, laeufe, fehler


def main(argumente: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", default=".", type=Path)
    parser.add_argument("--quelle", required=True, type=Path)
    parser.add_argument("--erwartet", default="[]", help="Jobs des Plans (JSON)")
    args = parser.parse_args(argumente)
    try:
        bestand = json.loads((args.root / TCO_DATEI).read_text(encoding="utf-8"))
        buendel = bestand["buendel"]
        erwartet = json.loads(args.erwartet or "[]")
    except (OSError, ValueError, KeyError) as fehler:
        print(f"Gegenprobe ablegen: Bestand unlesbar: {fehler}", file=sys.stderr)
        return FEHLER_EINGABE
    zeilen, laeufe, fehler = teile(args.quelle)
    stand = str(bestand.get("updated") or "")
    for lauf in fehlende(args.quelle, erwartet, stand):
        laeufe[stand].append(lauf)
    for datum in sorted(set(zeilen) | set(laeufe)):
        bilanz = lege_ab(
            args.root, datum, zeilen[datum], laeufe[datum], angezeigte(buendel, datum)
        )
        summe = bilanz["summe"]
        print(
            f"Gegenprobe {datum}: {len(zeilen[datum])} Zeilen, "
            f"{summe['im_fenster']} von {summe['angezeigt']} im Fenster, "
            f"{summe['ueberfaellig']} überfällig, Ausfälle {summe['ausfall']}"
        )
    for f in fehler:
        print(f"Gegenprobe ablegen: unlesbar: {f}", file=sys.stderr)
    return FEHLER_TEIL if fehler else 0


if __name__ == "__main__":
    sys.exit(main())
