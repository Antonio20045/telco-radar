"""Stufe 0 der Prüfleiter: zählt, was nur schrumpfen darf, und sperrt Lockerungen.

Gezählt wird je Datei und Code gegen drei Basen unter ``pruef/``. Keine Basis- oder
Ausnahmeliste darf seit dem Anker in einem Commit oder im Arbeitsstand lockerer
werden. Der Anker steht genau einmal in dieser Datei und wird aus ihr gelesen; der
Stand, der ihn verschiebt, ist rot, und ``anker_verschiebungen`` nennt jede
Verschiebung seit Beginn.
"""

from __future__ import annotations

import configparser
import json
import re
import shlex
import subprocess
import tomllib
from collections import Counter
from collections.abc import Callable
from functools import partial
from pathlib import Path

from waechter_regeln import (
    Schluessel,
    anker_aus_text,
    riesendateien,
    waechter_zaehlung,
)
from waechter_tests import TESTS_BASIS, tests_zaehlung

WURZEL = Path(__file__).resolve().parents[1]
RIESEN_BASIS = "pruef/riesendateien.txt"
PRIVAT_BASIS = "pruef/privat-basis.txt"
WAECHTER_BASIS = "pruef/waechter-basis.txt"
ANKER = "77d68537c80134513dd784d005136a561a6b467b"
WAECHTER = "scripts/waechter.py"
ABGESCHAFFT = ("pruef/tests-mit-bestand.txt", "pruef/rot-bekannt.txt")


def zaehlbasis_aus_text(text: str, als_json: bool) -> Counter[Schluessel]:
    if als_json:
        roh = json.loads(text or "{}")
        return Counter({(p, c): n for p, d in roh.items() for c, n in d.items()})
    return Counter({(p, c): int(n) for p, c, n in map(str.split, text.splitlines())})


def lies_zaehlbasis(pfad: Path) -> Counter[Schluessel]:
    return zaehlbasis_aus_text(pfad.read_text(encoding="utf-8"), pfad.suffix == ".json")


def schreibe_zaehlbasis(pfad: Path, basis: Counter[Schluessel]) -> None:
    if pfad.suffix == ".json":
        roh: dict[str, dict[str, int]] = {}
        for (p, c), n in sorted(basis.items()):
            roh.setdefault(p, {})[c] = n
        text = json.dumps(roh, indent=1, sort_keys=True, ensure_ascii=False) + "\n"
    else:
        text = "".join(f"{p} {c} {n}\n" for (p, c), n in sorted(basis.items()) if n)
    pfad.write_text(text, encoding="utf-8")


def ueber_basis(
    zaehlung: Counter[Schluessel], basis: Counter[Schluessel]
) -> list[Schluessel]:
    return sorted(k for k, n in zaehlung.items() if n > basis[k])


def gesenkt(
    zaehlung: Counter[Schluessel], basis: Counter[Schluessel]
) -> Counter[Schluessel]:
    return Counter({k: min(n, zaehlung[k]) for k, n in basis.items() if zaehlung[k]})


def pruefe(
    wurzel: Path, privat: Counter[Schluessel], schreiben: bool = True
) -> tuple[list[str], list[Path]]:
    """Gibt rote Zeilen und gesenkte Basen zurück; gesenkt wird nur bei Grün."""
    rot = lockerungen(wurzel) + [
        f"{name} ist abgeschafft; rote Tests werden repariert, nicht gelistet"
        for name in ABGESCHAFFT
        if (wurzel / name).exists()
    ]
    paare = [
        (RIESEN_BASIS, riesendateien(wurzel)),
        (PRIVAT_BASIS, privat),
        (WAECHTER_BASIS, waechter_zaehlung(wurzel)),
        (TESTS_BASIS, tests_zaehlung(wurzel)),
    ]
    neu = []
    for name, zaehlung in paare:
        basis = lies_zaehlbasis(wurzel / name)
        rot += [
            f"{p} [{c}] erwartet höchstens {basis[(p, c)]}, gefunden"
            f" {zaehlung[(p, c)]} ({name})"
            for p, c in ueber_basis(zaehlung, basis)
        ]
        if gesenkt(zaehlung, basis) != basis:
            neu.append((wurzel / name, gesenkt(zaehlung, basis)))
    if rot or not schreiben:
        return rot, []
    for basis_pfad, basis in neu:
        schreibe_zaehlbasis(basis_pfad, basis)
    return [], [basis_pfad for basis_pfad, _ in neu]


def lockerungen(wurzel: Path) -> list[str]:
    """Meldet jede Liste, die seit dem Anker lockerer wurde, je Commit und Stand."""
    anker, rot = anker_pruefung(wurzel)
    if anker is None:
        return rot
    try:
        bereich = [f"{anker}..HEAD", "--", *LISTEN]
        commits = _git(wurzel, "rev-list", "--reverse", *bereich).split()
        inhalte = _inhalte(wurzel, [(c, p) for c in [anker, *commits] for p in LISTEN])
    except subprocess.CalledProcessError:
        return [f"Inhalte ab {anker[:7]} nicht lesbar"]
    alt = {p: inhalte[(anker, p)] for p in LISTEN}
    meldungen = rot
    for commit in [*commits, None]:
        for pfad, vergleich in LISTEN.items():
            neu = inhalte[(commit, pfad)] if commit else _datei(wurzel / pfad)
            vorher = alt[pfad]
            if vorher is not None:
                ort = commit[:7] if commit else "Arbeitsstand"
                meldungen += [
                    f"{pfad} lockerer ({ort}): {zeile}"
                    for zeile in vergleich(vorher, neu or "")
                ]
            alt[pfad] = neu if vorher is None else neu or ""
    return meldungen


def anker_pruefung(wurzel: Path) -> tuple[str | None, list[str]]:
    """Liest den Anker aus der Datei, nie aus dem Modul, und meldet jede Verschiebung.

    Rot ist ein Anker, der nicht genau einmal gebunden ist, der nicht Vorfahre von
    HEAD ist, und eine Verschiebung im Arbeitsstand oder in HEAD selbst: Lockern darf
    nur Antonio, indem er diesen roten Stand bewusst selbst committet.
    """
    text = _datei(wurzel / WAECHTER) or ""
    anker, grund = anker_aus_text(text, streng=True)
    if anker is None:
        return None, [f"Anker in {WAECHTER} {grund}"]
    try:
        _git(wurzel, "cat-file", "-e", f"{anker}^{{commit}}")
    except subprocess.CalledProcessError:
        return None, [f"Verlauf ab {anker[:7]} fehlt; erst `git fetch --unshallow`"]
    vorfahre = ["git", "merge-base", "--is-ancestor", anker, "HEAD"]
    if subprocess.run(vorfahre, cwd=wurzel, capture_output=True).returncode:
        return None, [f"Anker {anker[:7]} ist kein Vorfahre von HEAD"]
    try:
        verlauf = _anker_verlauf(wurzel)
        kopf = _git(wurzel, "rev-parse", "HEAD").strip()
    except subprocess.CalledProcessError:
        return None, [f"Verlauf von {WAECHTER} nicht lesbar"]
    rot, alt = [], None
    for fassung in verlauf:
        ort, neu = fassung[0], fassung[-1]
        if ort in (kopf, "Arbeitsstand") and None not in (alt, neu) and alt != neu:
            wo = "Arbeitsstand" if ort == "Arbeitsstand" else f"HEAD {kopf[:7]}"
            rot.append(
                f"Anker verschoben im {wo}: {str(alt)[:7]} -> {str(neu)[:7]};"
                " lockern darf nur Antonio von Hand, indem er diesen roten Stand"
                " selbst committet"
            )
        # Verglichen wird mit dem letzten lesbaren Wert: eine unlesbare Zwischenfassung
        # versteckt keine Verschiebung.
        alt = neu if neu is not None else alt
    return anker, rot


def anker_verschiebungen(wurzel: Path) -> list[str]:
    """Nennt jede Fassung, die den Anker verschob, mit Datum, Autor und Werten."""
    try:
        verlauf = _anker_verlauf(wurzel)
    except subprocess.CalledProcessError:
        return [f"Verlauf von {WAECHTER} nicht lesbar"]
    meldungen, vorher = [], None
    for commit, datum, autor, titel, wert in verlauf:
        ort = commit[:7] if commit != "Arbeitsstand" else commit
        wer = f" ({datum}, {autor})" if datum else ""
        if wert is None:
            meldungen.append(f"Anker in {ort} nicht lesbar")
        elif vorher is not None and wert != vorher:
            meldungen.append(
                f"Anker verschoben in {ort}{wer} {titel}".rstrip()
                + f": {vorher[:7]} -> {wert[:7]}"
            )
        vorher = wert if wert is not None else vorher
    return meldungen


def _anker_verlauf(wurzel: Path) -> list[tuple[str, str, str, str, str | None]]:
    """Gibt je Fassung von ``scripts/waechter.py`` Commit, Datum, Autor, Titel, Wert."""
    log = _git(
        wurzel, "log", "--reverse", "--format=%H%x00%as%x00%an%x00%s", "--", WAECHTER
    )
    fassungen = [z.split("\0", 3) for z in log.splitlines()]
    inhalte = _inhalte(wurzel, [(c, WAECHTER) for c, *_ in fassungen])
    verlauf = [
        (c, d, a, t, anker_aus_text(inhalte[(c, WAECHTER)] or "")[0])
        for c, d, a, t in fassungen
    ]
    stand = _datei(wurzel / WAECHTER)
    if stand is not None:
        verlauf.append(("Arbeitsstand", "", "", "", anker_aus_text(stand)[0]))
    return verlauf


def _zaehl_lockerer(alt: str, neu: str, als_json: bool = False) -> list[str]:
    vorher = zaehlbasis_aus_text(alt, als_json)
    nachher = zaehlbasis_aus_text(neu, als_json)
    return [
        f"{p} {c} von {vorher[(p, c)]} auf {nachher[(p, c)]}"
        for p, c in ueber_basis(nachher, vorher)
    ]


def _grenze_lockerer(alt: str, neu: str, richtung: int) -> list[str]:
    if not alt.strip() or (neu.strip() and (int(neu) - int(alt)) * richtung >= 0):
        return []
    return [f"{alt.strip()} -> {neu.strip() or 'fehlt'}"]


def _menge_lockerer(alt: str, neu: str) -> list[str]:
    return [f"neu: {z}" for z in _neu_in(alt, neu)]


def _vertraege_lockerer(alt: str, neu: str) -> list[str]:
    vorher, nachher = configparser.ConfigParser(), configparser.ConfigParser()
    vorher.read_string(alt)
    nachher.read_string(neu)
    meldungen = []
    for name in [n for n in vorher.sections() if n.startswith("importlinter:contract")]:
        if not nachher.has_section(name):
            meldungen.append(f"{name} fehlt")
            continue
        a, n = dict(vorher[name]), dict(nachher[name])
        ausnahmen = _neu_in(a.get("ignore_imports", ""), n.get("ignore_imports", ""))
        meldungen += [f"{name}: neue Ausnahme {k}" for k in ausnahmen]
        if {**a, "ignore_imports": ""} != {**n, "ignore_imports": ""}:
            meldungen.append(f"{name}: Vertrag geändert")
    return meldungen


def _werkzeuge_lockerer(alt: str, neu: str) -> list[str]:
    vorher, nachher = (tomllib.loads(t).get("tool", {}) for t in (alt, neu))
    namen = ("ruff", "mypy", "importlinter")
    meldungen = [f"{k} geändert" for k in namen if vorher.get(k) != nachher.get(k)]
    alt_pytest, neu_pytest = vorher.get("pytest", {}), nachher.get("pytest", {})
    for a, n in ((alt_pytest, neu_pytest), _ini(alt_pytest, neu_pytest)):
        meldungen += _pytest_lockerer(a, n)
    return meldungen


def _ini(alt: dict, neu: dict) -> tuple[dict, dict]:
    return alt.get("ini_options", {}), neu.get("ini_options", {})


def _pytest_lockerer(alt: dict, neu: dict) -> list[str]:
    """Meldet jede Einstellung von pytest, die Tests abwählen oder Strenge nehmen kann.

    Durch geht nur, was verschärft: neue Marker und in ``addopts`` neue Optionen aus
    ``PYTEST_STRENGER``; jede andere geänderte Einstellung und jede entfernte strenge
    Option oder Socket-Sperre ist eine Lockerung.
    """
    meldungen = [
        f"pytest {k} geändert"
        for k in sorted({*alt, *neu} - {"addopts", "markers", "ini_options"})
        if alt.get(k) != neu.get(k)
    ]
    vorher, nachher = _optionen(alt.get("addopts")), _optionen(neu.get("addopts"))
    if vorher is None or nachher is None:
        return [*meldungen, "pytest addopts nicht lesbar"]
    dazu = [o for o in nachher if o not in vorher and not PYTEST_STRENGER.fullmatch(o)]
    weg = [
        o
        for o in vorher
        if o not in nachher and o.startswith(("--strict", "--disable-socket"))
    ]
    if dazu:
        meldungen.append(f"pytest addopts neu: {' '.join(dazu)}")
    if weg:
        meldungen.append(f"pytest addopts entfernt: {' '.join(weg)}")
    return meldungen


def _optionen(addopts: object) -> list[str] | None:
    if not addopts:
        return []
    try:
        teile = shlex.split(addopts) if isinstance(addopts, str) else addopts
    except ValueError:
        return None
    return [str(t) for t in teile] if isinstance(teile, list) else None


def _neu_in(alt: str, neu: str) -> list[str]:
    zeilen = {z.strip() for z in neu.splitlines()} - set(
        map(str.strip, alt.splitlines())
    )
    return sorted(z for z in zeilen if z)


# Optionen in addopts, die nur verschärfen: strenge Marker und Konfiguration, die
# Socket-Sperre bis auf die lokale Adresse, Parallelität und die Frist je Test.
PYTEST_STRENGER = re.compile(
    r"--strict-markers|--strict-config|--disable-socket"
    r"|--allow-hosts=(127\.0\.0\.1|localhost)(,(127\.0\.0\.1|localhost))*"
    r"|-n|--numprocesses|auto|logical|\d+|--dist|load|loadscope|loadfile|worksteal"
    r"|--timeout=\d+"
)
LISTEN: dict[str, Callable[[str, str], list[str]]] = {
    "pruef/ruff-basis.json": partial(_zaehl_lockerer, als_json=True),
    "pruef/mypy-basis.txt": _zaehl_lockerer,
    PRIVAT_BASIS: _zaehl_lockerer,
    RIESEN_BASIS: _zaehl_lockerer,
    WAECHTER_BASIS: _zaehl_lockerer,
    TESTS_BASIS: _zaehl_lockerer,
    "pruef/tests-mit-bestand.txt": _menge_lockerer,
    "pruef/rot-bekannt.txt": _menge_lockerer,
    "pruef/tests-anzahl.txt": partial(_grenze_lockerer, richtung=1),
    "pruef/tests-uebersprungen.txt": partial(_grenze_lockerer, richtung=-1),
    ".importlinter": _vertraege_lockerer,
    "pyproject.toml": _werkzeuge_lockerer,
}


def _datei(pfad: Path) -> str | None:
    return pfad.read_text(encoding="utf-8") if pfad.exists() else None


def _inhalte(
    wurzel: Path, paare: list[tuple[str, str]]
) -> dict[tuple[str | None, str], str | None]:
    anfrage = "".join(f"{c}:{p}\n" for c, p in paare).encode()
    befehl = ["git", "cat-file", "--batch"]
    lauf = subprocess.run(befehl, cwd=wurzel, input=anfrage, capture_output=True)
    roh = lauf.stdout
    inhalte: dict[tuple[str | None, str], str | None] = {}
    for paar in paare:
        kopf, _, roh = roh.partition(b"\n")
        if lauf.returncode or not kopf:
            raise subprocess.CalledProcessError(lauf.returncode or 1, befehl)
        if kopf.endswith(b" missing"):
            inhalte[paar] = None
            continue
        groesse = int(kopf.rsplit(b" ", 1)[1])
        inhalte[paar] = roh[:groesse].decode("utf-8")
        roh = roh[groesse + 1 :]
    return inhalte


def _git(wurzel: Path, *argumente: str) -> str:
    return subprocess.run(
        ["git", *argumente], cwd=wurzel, capture_output=True, text=True, check=True
    ).stdout
