"""Was Stufe 0 an den Tests zählt: Uhr, eigenes Chromium, Netzfreigaben, Griffe in die
Hermetik, vor pytest versteckte Tests, Pflichtoptionen und veränderte Schnappschüsse.

Gezählt wird je Datei und Code gegen ``pruef/tests-basis.txt``; nur schrumpfend.
"""

from __future__ import annotations

import ast
import fnmatch
import hashlib
import json
import shlex
import tomllib
from collections import Counter
from pathlib import Path

import waechter_speicher
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
VERSTECKT = "test-versteckt"
SETZEN = frozenset({"setattr", "delattr"})
NAMENSRAEUME = frozenset({"globals", "vars", "locals"})
VERSTECK_NAMEN = frozenset({"__test__", "allow_module_level"})
# Vorgabe von pytest für norecursedirs und python_files.
NICHT_GESAMMELT = ("*.egg", ".*", "_darcs", "build", "CVS", "dist", "node_modules")
NICHT_GESAMMELT += ("venv", "{arch}")
TESTDATEIEN = ("test_*.py", "*_test.py")
TESTNAME = "testname"
# Die Kanarie der Leiter sammelt nur ``-o python_files``, sie bleibt verborgen.
VERSTECKT_ERLAUBT = frozenset({"tests/kanarie_leiter.py"})


def tests_zaehlung(wurzel: Path) -> Counter[Schluessel]:
    zaehlung: Counter[Schluessel] = Counter()
    for datei in sorted((wurzel / "tests").rglob("*.py")):
        pfad = datei.relative_to(wurzel).as_posix()
        if pfad == CONFTEST or "__pycache__" in datei.parts:
            continue
        text = datei.read_text(encoding="utf-8", errors="replace")
        codes = waechter_speicher.hole(
            "tests", pfad, text, lambda t=text: _codes_aus(t)
        )
        if pfad in HERMETIK_ERLAUBT:
            codes = [c for c in codes if c != "hermetik-eingriff"]
        zaehlung.update((pfad, code) for code in codes if code != TESTNAME)
        if pfad not in VERSTECKT_ERLAUBT and _ungesammelt(pfad, codes):
            zaehlung[(pfad, VERSTECKT)] += 1
    zaehlung["pyproject.toml", "pytest-pflicht"] += _fehlende_optionen(wurzel)
    for ordner in sorted((wurzel / BESTAND).glob("*/")):
        relativ = ordner.relative_to(wurzel).as_posix()
        zaehlung[(relativ, "schnappschuss-veraendert")] += _veraendert(ordner)
    return +zaehlung


def _codes_aus(text: str) -> list[str]:
    try:
        return _codes(ast.parse(text))
    except SyntaxError:
        return ["syntaxfehler"]


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
    return codes + _versteck_codes(baum)


def _versteck_codes(baum: ast.AST) -> list[str]:
    """``__test__``, ``allow_module_level``, überschriebene Testmodule und Testnamen
    für ``_ungesammelt``."""
    module = {
        alias.asname or alias.name
        for knoten in ast.walk(baum)
        if isinstance(knoten, ast.Import | ast.ImportFrom)
        for alias in knoten.names
        if alias.name.rsplit(".", 1)[-1].startswith("test")
    }
    module |= {
        knoten.name
        for knoten in ast.walk(baum)
        if isinstance(knoten, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef)
        and knoten.name.lower().startswith("test")
    }
    codes = [VERSTECKT] * sum(map(lambda k: _ueberschreibt(k, module), ast.walk(baum)))
    for knoten in ast.walk(baum):
        if (
            isinstance(knoten, ast.Call)
            and getattr(knoten.func, "id", None) in NAMENSRAEUME
        ):
            codes.append(VERSTECKT)
        name = getattr(knoten, "id", None) or getattr(knoten, "attr", None)
        if isinstance(knoten, ast.Constant) and isinstance(knoten.value, str):
            name = knoten.value
        if isinstance(knoten, ast.keyword):
            name = knoten.arg
        if name in VERSTECK_NAMEN:
            codes.append(VERSTECKT)
        if isinstance(knoten, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            codes += [TESTNAME] * knoten.name.lower().startswith("test")
    return codes


def _ueberschreibt(knoten: ast.AST, module: set[str]) -> bool:
    """Eine Zuweisung, Löschung oder ``setattr`` an einem Testmodul, einer Testfunktion
    oder einem Modul aus ``sys.modules``."""
    ziele: list[ast.expr] = []
    if isinstance(knoten, ast.Assign | ast.Delete):
        ziele = list(knoten.targets)
    elif isinstance(knoten, ast.AugAssign | ast.AnnAssign):
        ziele = [knoten.target]
    elif isinstance(knoten, ast.Call) and knoten.args:
        name = getattr(knoten.func, "id", None) or getattr(knoten.func, "attr", "")
        ziele = [ast.Attribute(knoten.args[0])] if name in SETZEN else []
    return any(
        (isinstance(z, ast.Name) and z.id in module)
        or (
            isinstance(z, ast.Attribute)
            and (getattr(z.value, "id", None) in module or _sys_modules(z.value))
        )
        for z in ziele
    )


def _sys_modules(ausdruck: ast.expr) -> bool:
    """Ein Ausdruck, der in ``sys.modules`` greift."""
    return any(
        isinstance(k, ast.Attribute) and k.attr == "modules" for k in ast.walk(ausdruck)
    )


def _ungesammelt(pfad: str, codes: list[str]) -> bool:
    """Eine Datei mit Tests, die pytest nach seinen Vorgaben nie sammelt."""
    teile = Path(pfad).parts
    ordner_versteckt = any(
        fnmatch.fnmatch(teil, muster)
        for teil in teile[1:-1]
        for muster in NICHT_GESAMMELT
    )
    testdatei = any(fnmatch.fnmatch(teile[-1], muster) for muster in TESTDATEIEN)
    return TESTNAME in codes and (ordner_versteckt or not testdatei)


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
