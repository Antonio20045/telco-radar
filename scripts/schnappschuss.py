"""Zieht einen Ausschnitt des Bestands aus einem Bot-Commit nach tests/fixtures/.

Ein Schnappschuss wird nie geändert, nur durch einen neuen Ordner mit neuem Datum
ersetzt. ``_herkunft.json`` nennt Commit, Zeit, Quelle, Zeilenfilter und sha256 je
Datei; Stufe 0 hält die Dateien dagegen.

    python scripts/schnappschuss.py <commit> [--datei PFAD] [--zeilen PFAD=REGEX]
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

WURZEL = Path(__file__).resolve().parents[1]
HERKUNFT = "_herkunft.json"
BOT = "telco-radar-bot"
DATEN = "data/"
# Was render_site aus dem Bestand liest, ohne Bilder; die Historie nur für vier Geräte.
STANDARD_DATEIEN = (
    "data/state/diff_bilder.json",
    "data/state/differentiation.jsonl",
    "data/state/differentiation_db.json",
    "data/state/geraete_db.json",
    "data/state/geraete_katalog_auto.json",
    "data/state/geraete_preise.jsonl",
    "data/state/geraete_tco.json",
    "data/state/highlight_topics.json",
    "data/state/lieferzeit.json",
    "data/state/promo_db.json",
    "data/state/tarife.jsonl",
    "data/state/uebersetzungen.jsonl",
)
STANDARD_ZEILEN = (
    r"data/state/geraete_tco_historie.jsonl="
    r'"id": "[^"]*(apple-iphone-17-256gb|apple-iphone-18-pro-256gb'
    r"|samsung-galaxy-s26-ultra-256gb|google-pixel-11-256gb)-",
)


class SchnappschussFehler(Exception):
    """Der Schnappschuss lässt sich so nicht ziehen."""


def ziehe(
    commit: str, dateien: list[str], zeilen: dict[str, str], wurzel: Path = WURZEL
) -> Path:
    """Schreibt den Schnappschuss und gibt seinen Ordner zurück."""
    voll, autor, sekunden = _git(
        wurzel, "log", "-1", "--format=%H%n%an%n%ct", commit
    ).split()
    zeit = dt.datetime.fromtimestamp(int(sekunden), dt.UTC).isoformat()
    if autor != BOT:
        raise SchnappschussFehler(f"{voll[:7]} ist kein Bot-Commit ({autor})")
    ordner = wurzel / "tests" / "fixtures" / "bestand" / zeit[:10]
    if ordner.exists():
        raise SchnappschussFehler(
            f"{ordner.name} gibt es schon; nie ändern, nur ersetzen"
        )
    eintraege = {}
    inhalte = {}
    for quelle in [*dateien, *_bericht(wurzel, voll), *zeilen]:
        if not quelle.startswith(DATEN):
            raise SchnappschussFehler(f"{quelle} liegt nicht unter {DATEN}")
        roh = _git_bytes(wurzel, "show", f"{voll}:{quelle}")
        muster = zeilen.get(quelle)
        if muster is not None:
            treffer = re.compile(muster)
            roh = b"".join(
                z for z in roh.splitlines(keepends=True) if treffer.search(z.decode())
            )
        ziel = quelle.removeprefix(DATEN)
        inhalte[ziel] = roh
        eintraege[ziel] = {
            "quelle": quelle,
            "filter": muster,
            "sha256": hashlib.sha256(roh).hexdigest(),
        }
    for ziel, roh in inhalte.items():
        (ordner / ziel).parent.mkdir(parents=True, exist_ok=True)
        (ordner / ziel).write_bytes(roh)
    herkunft = {"commit": voll, "autor": autor, "zeit": zeit, "dateien": eintraege}
    text = json.dumps(herkunft, indent=1, sort_keys=True, ensure_ascii=False)
    (ordner / HERKUNFT).write_text(text + "\n", encoding="utf-8")
    return ordner


def _bericht(wurzel: Path, commit: str) -> list[str]:
    """Der neueste Bericht des Commits mit seinen Promo- und Differenzierungsteilen."""
    namen = _git(wurzel, "ls-tree", "-r", "--name-only", commit, "data/reports").split()
    tage = sorted(
        n[13:23] for n in namen if re.fullmatch(r"data/reports/[\d-]{10}\.json", n)
    )
    if not tage:
        return []
    teile = ("", "promo/", "differenzierung/")
    gesucht = [
        f"data/reports/{t}{tage[-1]}{e}" for t in teile for e in (".json", ".md")
    ]
    return [n for n in gesucht if n in namen]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("commit")
    parser.add_argument("--datei", action="append")
    parser.add_argument("--zeilen", action="append", help="PFAD=REGEX")
    argumente = parser.parse_args(argv)
    dateien = argumente.datei or list(STANDARD_DATEIEN)
    paare = argumente.zeilen or list(STANDARD_ZEILEN)
    zeilen = dict(paar.split("=", 1) for paar in paare)
    try:
        ordner = ziehe(argumente.commit, dateien, zeilen)
    except (SchnappschussFehler, subprocess.CalledProcessError) as fehler:
        print(f"Schnappschuss nicht gezogen: {fehler}", file=sys.stderr)
        return 1
    print(ordner.relative_to(WURZEL))
    return 0


def _git(wurzel: Path, *argumente: str) -> str:
    return _git_bytes(wurzel, *argumente).decode()


def _git_bytes(wurzel: Path, *argumente: str) -> bytes:
    return subprocess.run(
        ["git", *argumente], cwd=wurzel, capture_output=True, check=True
    ).stdout


if __name__ == "__main__":
    sys.exit(main())
