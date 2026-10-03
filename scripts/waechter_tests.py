"""Was Stufe 0 an den Tests zählt: Uhr, eigenes Chromium, Netzfreigaben, Griffe in die
Hermetik, Pflichtoptionen von pytest und veränderte Schnappschüsse.

Gezählt wird je Datei und Code gegen ``pruef/tests-basis.txt``; nur schrumpfend.
"""

from __future__ import annotations

import ast
import hashlib
import json
import shlex
import tomllib
from collections import Counter
from pathlib import Path

from waechter_regeln import Schluessel, importnamen, ist_uhr, uhr_verweise

TESTS_BASIS = "pruef/tests-basis.txt"
CONFTEST = "tests/conftest.py"
BESTAND = "tests/fixtures/bestand"
HERKUNFT = "_herkunft.json"
PFLICHT_OPTIONEN = ("--strict-markers", "--disable-socket", "--allow-hosts=127.0.0.1")
NETZ_FREIGABEN = frozenset(
    {
        "enable_socket",
        "socket_enabled",
        "force_enable_socket",
        "allow_hosts",
        "--force-enable-socket",
        "--allow-unix-socket",
    }
)
HERMETIK_NAMEN = frozenset(
    {"_aktiv", "_altlasten", "_verstoesse", "_gemeldet", "_hermetik", "conftest"}
)
# Die Tests der Hermetik und der Leiter legen selbst eine conftest.py an.
HERMETIK_ERLAUBT = frozenset({"tests/test_hermetik.py", "tests/test_pruefleiter.py"})
PLAYWRIGHT_START = frozenset({"sync_playwright", "async_playwright"})


def tests_zaehlung(wurzel: Path) -> Counter[Schluessel]:
    zaehlung: Counter[Schluessel] = Counter()
    for datei in sorted((wurzel / "tests").rglob("*.py")):
        pfad = datei.relative_to(wurzel).as_posix()
        if pfad == CONFTEST or "__pycache__" in datei.parts:
            continue
        try:
            baum = ast.parse(datei.read_text(encoding="utf-8", errors="replace"))
        except SyntaxError:
            zaehlung[(pfad, "syntaxfehler")] += 1
            continue
        codes = _codes(baum)
        if pfad in HERMETIK_ERLAUBT:
            codes = [c for c in codes if c != "hermetik-eingriff"]
        zaehlung.update((pfad, code) for code in codes)
    zaehlung["pyproject.toml", "pytest-pflicht"] += _fehlende_optionen(wurzel)
    for ordner in sorted((wurzel / BESTAND).glob("*/")):
        relativ = ordner.relative_to(wurzel).as_posix()
        zaehlung[(relativ, "schnappschuss-veraendert")] += _veraendert(ordner)
    return +zaehlung


def _codes(baum: ast.AST) -> list[str]:
    aliase = importnamen(baum)
    codes = ["uhr"] * uhr_verweise(baum, aliase)
    for knoten in ast.walk(baum):
        if isinstance(knoten, ast.Call):
            if ist_uhr(knoten, aliase):
                codes.append("uhr")
            if _startet_playwright(knoten, aliase):
                codes.append("chromium-eigenes")
        name = getattr(knoten, "id", None) or getattr(knoten, "attr", None)
        if isinstance(knoten, ast.Constant) and isinstance(knoten.value, str):
            name = knoten.value
        if isinstance(knoten, ast.arg):
            name = knoten.arg
        if isinstance(knoten, ast.alias):
            name = knoten.name.split(".")[0]
        if isinstance(knoten, ast.ImportFrom):
            name = (knoten.module or "").split(".")[0]
        if name in NETZ_FREIGABEN:
            codes.append("netz-freigabe")
        if name in HERMETIK_NAMEN:
            codes.append("hermetik-eingriff")
    return codes


def _startet_playwright(aufruf: ast.Call, aliase: dict[str, str]) -> bool:
    """Ein Start von Playwright, auch unter anderem Namen importiert."""
    funktion = aufruf.func
    name = getattr(funktion, "id", None) or getattr(funktion, "attr", None) or ""
    return aliase.get(name, name).rsplit(".", 1)[-1] in PLAYWRIGHT_START


def _fehlende_optionen(wurzel: Path) -> int:
    try:
        text = (wurzel / "pyproject.toml").read_text(encoding="utf-8")
        optionen = tomllib.loads(text)["tool"]["pytest"]["ini_options"]["addopts"]
        teile = shlex.split(optionen) if isinstance(optionen, str) else optionen
    except (OSError, KeyError, TypeError, ValueError, tomllib.TOMLDecodeError):
        return len(PFLICHT_OPTIONEN)
    return sum(option not in teile for option in PFLICHT_OPTIONEN)


def _veraendert(ordner: Path) -> int:
    """Zählt jede Datei des Schnappschusses, die fehlt, dazukam oder anders ist."""
    try:
        eintraege = json.loads((ordner / HERKUNFT).read_text(encoding="utf-8"))
        soll = {name: e["sha256"] for name, e in eintraege["dateien"].items()}
    except (OSError, KeyError, TypeError, ValueError):
        return 1
    ist = {
        d.relative_to(ordner).as_posix(): hashlib.sha256(d.read_bytes()).hexdigest()
        for d in ordner.rglob("*")
        if d.is_file() and d.name != HERKUNFT
    }
    return len(set(soll.items()) ^ set(ist.items()))
