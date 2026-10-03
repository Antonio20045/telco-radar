"""Sperrt Geheimnisse und Adressen in getrackten Dateien des öffentlichen Repos.

Stufe 0 der Prüfleiter und die Bot-Workflows vor ihrem Commit rufen dieselbe
Funktion ``lecks``. Es gibt keine Ausnahmeliste: ein Treffer ist rot.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

import waechter_speicher

BREVO_SCHLUESSEL = re.compile(rb"x(?:key|smtp)sib-[A-Za-z0-9]")
ADRESSE = re.compile(rb"[A-Za-z0-9_.+-]+@[A-Za-z][A-Za-z0-9-]*\.[A-Za-z]{2,}")
ADRESSEN_ORDNER = "data/"
ADRESSEN_ENDUNG = ".jsonl"
WORKFLOWS = ".github/workflows"
SCAN_AUFRUF = "scripts/waechter_leck.py"
_GIT = r"\bgit(?:\s+(?:-[cC]\s+\S+|--?[\w-]+(?:=\S+)?))*\s+"
GIT_COMMIT = re.compile(_GIT + r"commit\b")
GIT_VORMERKEN = re.compile(_GIT + r"(?:add|stage)\b")
SCAN_ZEILE = re.compile(
    r"^\s*(?:-\s+)?(?:run:\s+)?(?:\S*python3?\s+)?scripts/waechter_leck\.py\s*$"
)
UNTERMODUL = b"160000"
SYMLINK = b"120000"


def lecks(wurzel: Path) -> list[str]:
    """Meldet je getrackter Datei einen Brevo-Schlüssel und je getrackter
    ``.jsonl`` unter ``data/`` eine E-Mail-Adresse, gelesen aus Index und
    Arbeitsstand, dazu jeden Workflow-Commit ohne vorherigen Scan."""
    try:
        eintraege = _index(wurzel)
        abweichend = _abweichend(wurzel)
        nur_index = [e for e in eintraege if e[0] in abweichend or e[2] == SYMLINK]
        gelesen = _blobs(wurzel, [e[1] for e in nur_index])
        blobs = dict(zip(nur_index, gelesen, strict=True))
    except (OSError, ValueError, subprocess.CalledProcessError):
        return ["Leckprüfung: getrackte Dateien nicht lesbar (git ls-files)"]
    meldungen = []
    for eintrag in sorted(eintraege):
        name, sha, _ = eintrag
        if eintrag in blobs:
            funde = _funde(wurzel, name, [blobs[eintrag]])
        else:
            funde = waechter_speicher.hole(
                "leck", name, sha, lambda n=name: _funde(wurzel, n, [])
            )
        if "schluessel" in funde:
            meldungen.append(f"{name}: Brevo-Schlüssel im Repo (gehört in ein Secret)")
        if "adresse" in funde:
            meldungen.append(f"{name}: E-Mail-Adresse in Bot-Daten")
    return meldungen + ungepruefte_commits(wurzel)


def _funde(wurzel: Path, name: str, inhalte: list[bytes]) -> list[str]:
    pfad = wurzel / name
    if not pfad.is_symlink() and pfad.is_file():
        inhalte = [*inhalte, pfad.read_bytes()]
    funde = []
    if any(BREVO_SCHLUESSEL.search(i) for i in inhalte):
        funde.append("schluessel")
    if _adressdatei(name) and any(ADRESSE.search(i) for i in inhalte):
        funde.append("adresse")
    return funde


def ungepruefte_commits(wurzel: Path) -> list[str]:
    """Meldet jedes ``git commit`` in einem Workflow, vor dem seit Dateibeginn
    oder dem letzten ``git add`` keine Zeile steht, die nur den Leckscan ruft."""
    meldungen = []
    for datei in sorted((wurzel / WORKFLOWS).glob("*.y*ml")):
        geprueft = False
        zeilen = datei.read_text(encoding="utf-8").splitlines()
        for nummer, zeile in enumerate(zeilen, 1):
            if GIT_VORMERKEN.search(zeile):
                geprueft = False
            if SCAN_ZEILE.match(zeile):
                geprueft = True
            if GIT_COMMIT.search(zeile) and not geprueft:
                ort = f"{WORKFLOWS}/{datei.name}:{nummer}"
                meldungen.append(f"{ort}: git commit ohne vorherigen {SCAN_AUFRUF}")
    return meldungen


def _index(wurzel: Path) -> list[tuple[str, str, bytes]]:
    roh = _git(wurzel, "ls-files", "-s", "-z")
    eintraege = []
    for zeile in filter(None, roh.split(b"\0")):
        kopf, _, name = zeile.partition(b"\t")
        modus, sha, _ = kopf.split(b" ")
        if modus != UNTERMODUL:
            eintraege.append((os.fsdecode(name), sha.decode(), modus))
    return eintraege


def _abweichend(wurzel: Path) -> set[str]:
    roh = _git(wurzel, "diff-files", "--name-only", "-z")
    return {os.fsdecode(n) for n in roh.split(b"\0") if n}


def _git(wurzel: Path, *argumente: str) -> bytes:
    befehl = ["git", *argumente]
    return subprocess.run(befehl, cwd=wurzel, capture_output=True, check=True).stdout


def _blobs(wurzel: Path, shas: list[str]) -> list[bytes]:
    befehl = ["git", "cat-file", "--batch"]
    anfrage = "".join(f"{sha}\n" for sha in shas).encode()
    roh = subprocess.run(
        befehl, cwd=wurzel, input=anfrage, capture_output=True, check=True
    ).stdout
    blobs = []
    stelle = 0
    for _ in shas:
        ende = roh.index(b"\n", stelle)
        kopf = roh[stelle:ende]
        if kopf.endswith(b" missing"):
            raise subprocess.CalledProcessError(1, befehl)
        groesse = int(kopf.rsplit(b" ", 1)[1])
        blobs.append(roh[ende + 1 : ende + 1 + groesse])
        stelle = ende + 2 + groesse
    return blobs


def _adressdatei(name: str) -> bool:
    return name.startswith(ADRESSEN_ORDNER) and name.endswith(ADRESSEN_ENDUNG)


def main() -> int:
    meldungen = lecks(Path.cwd())
    for zeile in meldungen:
        print(f"::error::{zeile}")
    return 1 if meldungen else 0


if __name__ == "__main__":
    sys.exit(main())
