"""Ergebnisse der Klick-Erkundung für den öffentlichen Zweig ``klick-erkundung``.

Der Job ``ablegen`` in ``.github/workflows/klick-erkundung.yml`` ruft zwei Schritte:

``einsortieren NEU ZIEL``
    Nimmt aus den heruntergeladenen Artefakten (``NEU/<artefakt>/<anbieter>/<tag>/``)
    nur Ordner mit gültigem ``index.json`` (Anbieter und Tag wie der Ordner, ein
    Status), dessen Status nicht ``verschoben`` ist; ein Teilergebnis ohne Index
    ersetzt nie einen vollständigen Stand. Kopiert werden nur abgeleitete
    Strukturdaten (``ERLAUBT``: Index, Bedienelemente, Preise, Klicks, Mitschnitt,
    Kartenprobe);
    Screenshot und Seite bleiben im Artefakt (Datenkonzept Abschnitt 12). Nennt die
    abgelegten Anbieter; ohne ein einziges gültiges ``index.json`` Exit 1.

``pruefe ZIEL``
    Sucht in jeder Datei unter ``ZIEL``, gepackte entpackt, nach Namen außerhalb von
    ``ERLAUBT`` und nach Lecks (``LECKMUSTER``: JSON Web Token, Sitzungskennung,
    Warenkorb-Kennung, auch in einem Antwortkörper als JSON-Text, Set-Cookie, Bearer,
    Brevo-Schlüssel). Jeder Treffer ist eine ``::error::``-Zeile und Exit 1, also kein
    Commit. Die Ablage schwärzt schon beim Schreiben; dies ist die zweite Linie.
"""

from __future__ import annotations

import argparse
import gzip
import json
import re
import shutil
import sys
import zlib
from pathlib import Path

ERLAUBT = re.compile(
    r"^(?:index|(?:bedienelemente|preise|klicks|mitschnitt|karte)-\d{1,3})\.json$"
)
INDEX = "index.json"
ANBIETER = re.compile(r"^[a-z0-9]{1,40}$")
TAG = re.compile(r"^\d{4}-\d{2}-\d{2}$")
OHNE_DATEN = frozenset({"verschoben"})
ENTFERNT = r"(?!ENTFERNT\b|\[Cookie entfernt\])"
LECKMUSTER = {
    "JSON Web Token": re.compile(rb"eyJ[\w-]{4,}\.eyJ[\w-]{4,}\.[\w-]*"),
    "Sitzungskennung": re.compile(
        rb"(?i)\b(?:jsessionid|phpsessid|asp\.net_sessionid|session_?id|sid)"
        + rb'"?\s*[=:]\s*"?'
        + ENTFERNT.encode()
        + rb"[\w%.-]{6,}"
    ),
    "Warenkorb-Kennung": re.compile(
        rb"(?i)(?:(?:cart|basket)[_-]?id|warenkorb(?:[_-]?id)?)"
        + rb'(?:\\?")?\s*[=:]\s*(?:\\?")?'
        + ENTFERNT.encode()
        + rb"[\w%.-]{6,}"
    ),
    "Set-Cookie": re.compile(rb"(?i)set-cookie"),
    "Bearer": re.compile(rb"(?i)\bbearer\s+" + ENTFERNT.encode() + rb"[\w.~+/=-]{8,}"),
    "Brevo-Schlüssel": re.compile(rb"x(?:key|smtp)sib-[A-Za-z0-9]"),
}
GZIP_ENDUNG = ".gz"


def einsortieren(neu: Path, ziel: Path) -> list[str]:
    """Legt jeden gültigen Tagesordner aus ``neu`` nach ``ziel``; gibt die Anbieter."""
    abgelegt: list[str] = []
    ziel.mkdir(parents=True, exist_ok=True)
    for tag in sorted(neu.glob("*/*/*")):
        if not tag.is_dir():
            continue
        grund = _ungueltig(tag)
        if grund is not None:
            print(f"::warning::{tag.relative_to(neu)} nicht abgelegt: {grund}")
            continue
        status = json.loads((tag / INDEX).read_text(encoding="utf-8"))["status"]
        if status in OHNE_DATEN:
            print(f"{tag.parent.name}: {status}, nichts abgelegt")
            continue
        ort = ziel / tag.parent.name / tag.name
        if ort.exists():
            shutil.rmtree(ort)
        ort.mkdir(parents=True)
        for datei in sorted(tag.iterdir()):
            if datei.is_file() and ERLAUBT.match(datei.name):
                shutil.copyfile(datei, ort / datei.name)
            else:
                print(f"{tag.parent.name}: {datei.name} bleibt im Artefakt")
        abgelegt.append(tag.parent.name)
    return abgelegt


def gueltige_indizes(neu: Path) -> int:
    """Zahl der Tagesordner mit gültigem ``index.json``, auch verschobene."""
    return sum(1 for t in neu.glob("*/*/*") if t.is_dir() and _ungueltig(t) is None)


def pruefe(ziel: Path) -> list[str]:
    """Jeder unerlaubte Dateiname und jedes Leck unter ``ziel`` als Zeile."""
    funde = []
    for datei in sorted(p for p in ziel.rglob("*") if p.is_file()):
        ort = datei.relative_to(ziel).as_posix()
        if not ERLAUBT.match(datei.name):
            funde.append(f"{ort}: Datei gehört nicht auf den öffentlichen Zweig")
        inhalt = datei.read_bytes()
        if datei.name.endswith(GZIP_ENDUNG):
            inhalt = _entpackt(inhalt)
        for name, muster in LECKMUSTER.items():
            if muster.search(inhalt):
                funde.append(f"{ort}: {name} gefunden")
    return funde


def _ungueltig(tag: Path) -> str | None:
    anbieter = tag.parent.name
    if not ANBIETER.match(anbieter) or not TAG.match(tag.name):
        return "Ordnername ist kein Anbieter/Tag"
    try:
        index = json.loads((tag / INDEX).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return f"{INDEX} fehlt"
    except (OSError, ValueError) as fehler:
        return f"{INDEX} unlesbar ({type(fehler).__name__})"
    if not isinstance(index, dict):
        return f"{INDEX} ist kein Objekt"
    if index.get("anbieter") != anbieter or index.get("datum") != tag.name:
        return f"{INDEX} nennt {index.get('anbieter')}/{index.get('datum')}"
    if not isinstance(index.get("status"), str) or not index["status"]:
        return f"{INDEX} ohne Status"
    return None


def _entpackt(inhalt: bytes) -> bytes:
    try:
        return gzip.decompress(inhalt)
    except (OSError, EOFError, zlib.error):
        return inhalt


def main(argumente: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    teile = parser.add_subparsers(dest="befehl", required=True)
    sortieren = teile.add_parser("einsortieren")
    sortieren.add_argument("neu", type=Path)
    sortieren.add_argument("ziel", type=Path)
    pruefen = teile.add_parser("pruefe")
    pruefen.add_argument("ziel", type=Path)
    args = parser.parse_args(argumente)
    if args.befehl == "einsortieren":
        if gueltige_indizes(args.neu) == 0:
            print("::error::Kein Anbieter hat ein gültiges index.json hochgeladen.")
            return 1
        abgelegt = einsortieren(args.neu, args.ziel)
        print(f"Abgelegt: {', '.join(abgelegt) if abgelegt else 'kein Anbieter'}")
        return 0
    funde = pruefe(args.ziel)
    for fund in funde:
        print(f"::error::{fund}")
    return 1 if funde else 0


if __name__ == "__main__":
    sys.exit(main())
