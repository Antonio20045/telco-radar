"""Was Stufe 0 je Datei zählt: Größe, Kommentare, Syntaxbaum, Farben, Konfiguration.

Gezählt wird je Datei und Code; die Basen und den Vergleich hält ``waechter.py``.
"""

from __future__ import annotations

import ast
import io
import os
import re
import tokenize
from collections import Counter
from collections.abc import Iterable, Iterator
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

RIESEN_GRENZE = 400
CODE_ORDNER = ("src/**/*", "scripts/**/*", "tools/**/*", "service/**/*")
_RUFF_MYPY = {"pyproject.toml", "ruff.toml", ".ruff.toml", "mypy.ini", ".mypy.ini"}
_PYTEST = {"pytest.ini", ".pytest.ini", "pytest.toml", ".pytest.toml", "tox.ini"}
_PYTHON = {"conftest.py", "sitecustomize.py", "usercustomize.py", "setup.cfg"}
KONFIG_NAMEN = frozenset({*_RUFF_MYPY, *_PYTEST, *_PYTHON, ".importlinter"})
KONFIG_ERLAUBT = frozenset({"pyproject.toml", ".importlinter"})
CONFTEST_ORDNER = "tests/"
NICHT_DURCHSUCHT = frozenset({".git", "node_modules", "__pycache__"})
NICHT_DURCHSUCHTE_PFADE = frozenset({".venv", "venv", ".claude/worktrees"})
REPORT = "src/telco_radar/report/"
EINSTIEG = {
    "src/telco_radar/pipeline.py": "run",
    "src/telco_radar/geraete_pipeline.py": "run_geraete_stage",
}
UHR_ERLAUBT = frozenset(EINSTIEG)
PARALLEL_AB = 64
PARALLEL_STUECK = 16
FARBEN_ERLAUBT = "src/telco_radar/report/anbieter_farben.py"
STYLE = "src/telco_radar/report/templates/style.css"
FARB_ENDUNGEN = frozenset({".py", ".j2", ".css", ".js", ".html"})
VERBOTENE_HOOKS = re.compile(
    r"pytest_(runtest_(makereport|logreport|protocol|call|logfinish)"
    r"|report_teststatus|pyfunc_call|sessionfinish|terminal_summary)"
)
_DATEIZUGRIFF = re.compile(r"open|(read|write)_(text|bytes)")
_HEX = re.compile(r"(?<![&\w])#(?:[0-9a-fA-F]{8}|[0-9a-fA-F]{6}|[0-9a-fA-F]{3,4})\b")
_ROOT = re.compile(r":root\s*\{[^}]*\}")
_NOQA = re.compile(r"noqa(?::\s*([A-Z]+[0-9]+(?:[\s,]+[A-Z]+[0-9]+)*))?", re.I)
_TYPE_IGNORE = re.compile(r"type:\s*ignore(?:\[([^\]]*)\])?")
_WERKZEUG_AUS = re.compile(r"mypy:\s*ignore-errors|fmt:\s*(?:off|skip)")

Schluessel = tuple[str, str]


def riesendateien(wurzel: Path) -> Counter[Schluessel]:
    zeilen = {p: len(t.splitlines()) for p, t in _dateien(wurzel, CODE_ORDNER, {".py"})}
    return Counter({(p, "zeilen"): n for p, n in zeilen.items() if n > RIESEN_GRENZE})


def waechter_zaehlung(wurzel: Path) -> Counter[Schluessel]:
    zaehlung: Counter[Schluessel] = Counter()
    dateien = list(_dateien(wurzel, (*CODE_ORDNER, "tests/**/*"), {".py"}))
    if len(dateien) < PARALLEL_AB:
        codes = map(_codes_je_datei, dateien)
        zaehlung.update(k for je_datei in codes for k in je_datei)
    else:
        with ProcessPoolExecutor() as pool:
            codes = pool.map(_codes_je_datei, dateien, chunksize=PARALLEL_STUECK)
            zaehlung.update(k for je_datei in codes for k in je_datei)
    for pfad, text in _dateien(wurzel, ("src/**/*",), FARB_ENDUNGEN):
        if pfad != FARBEN_ERLAUBT:
            ohne_root = _ROOT.sub("", text, count=1) if pfad == STYLE else text
            zaehlung[(pfad, "hexfarbe")] += len(_HEX.findall(ohne_root))
    zaehlung.update((pfad, "fremde-konfig") for pfad in fremde_konfig(wurzel))
    for pfad, text in _dateien(wurzel, (".github/workflows/*",), {".yml", ".yaml"}):
        for zeile in text.splitlines():
            zaehlung[(pfad, "oder-true")] += len(re.findall(r"\|\|\s*true\b", zeile))
            if re.search(r"continue-on-error:\s*(?!false\b)\S", zeile):
                zaehlung[(pfad, "continue-on-error")] += 1
            if re.match(r"\s*python-version:", zeile):
                zaehlung[(pfad, "python-version")] += 1
    return +zaehlung


def fremde_konfig(wurzel: Path) -> Iterator[str]:
    """Nennt jede Datei, die pytest, ruff, mypy oder Python neben der Wurzel steuert.

    Erlaubt sind nur ``pyproject.toml`` und ``.importlinter`` in der Wurzel und
    ``conftest.py`` unter ``tests/``; nicht durchsucht werden die benannten
    Ordner für virtuelle Umgebungen und Lauf-Worktrees.
    """
    for ordner, unterordner, namen in os.walk(wurzel):
        relativ = Path(ordner).relative_to(wurzel).as_posix()
        if relativ in NICHT_DURCHSUCHTE_PFADE:
            unterordner[:] = []
            continue
        unterordner[:] = sorted(set(unterordner) - NICHT_DURCHSUCHT)
        for name in sorted(KONFIG_NAMEN.intersection(namen)):
            pfad = name if relativ == "." else f"{relativ}/{name}"
            unter_tests = name == "conftest.py" and pfad.startswith(CONFTEST_ORDNER)
            if pfad not in KONFIG_ERLAUBT and not unter_tests:
                yield pfad


def uhr_ausserhalb_einstieg(wurzel: Path) -> int:
    """Zählt Uhraufrufe in den Einstiegsdateien außerhalb ihrer Einstiegsfunktion."""
    anzahl = 0
    for pfad, funktion in EINSTIEG.items():
        datei = wurzel / pfad
        baum = ast.parse(datei.read_text("utf-8") if datei.is_file() else "")
        innen = {
            id(k)
            for f in ast.walk(baum)
            if isinstance(f, ast.FunctionDef | ast.AsyncFunctionDef)
            and f.name == funktion
            for k in ast.walk(f)
        }
        anzahl += sum(
            _ist_uhr(k) and id(k) not in innen
            for k in ast.walk(baum)
            if isinstance(k, ast.Call)
        )
    return anzahl


def _kommentar_codes(text: str) -> Iterator[str]:
    if not any(m.search(text) for m in (_NOQA, _TYPE_IGNORE, _WERKZEUG_AUS)):
        return
    try:
        tokens = list(tokenize.generate_tokens(io.StringIO(text).readline))
    except (tokenize.TokenError, SyntaxError):
        return
    for kommentar in (t.string for t in tokens if t.type == tokenize.COMMENT):
        for treffer in _NOQA.finditer(kommentar):
            codes = re.findall(r"[A-Z]+[0-9]+", treffer.group(1) or "") or ["alle"]
            yield from (f"noqa:{c}" for c in codes)
        for treffer in _TYPE_IGNORE.finditer(kommentar):
            codes = re.findall(r"[\w-]+", treffer.group(1) or "") or ["alle"]
            yield from (f"type-ignore:{c}" for c in codes)
        if _WERKZEUG_AUS.search(kommentar):
            yield "werkzeug-aus"


def _codes_je_datei(datei: tuple[str, str]) -> list[Schluessel]:
    pfad, text = datei
    codes = list(_kommentar_codes(text))
    try:
        codes += _ast_codes(pfad, ast.parse(text))
    except SyntaxError:
        codes.append("syntaxfehler")
    return [(pfad, code) for code in codes]


def _ist_uhr(aufruf: ast.Call) -> bool:
    name, basis = _name(aufruf.func), _name(getattr(aufruf.func, "value", None))
    return bool(basis) and (
        name in ("now", "utcnow", "today") or name == basis == "time"
    )


def _ast_codes(pfad: str, baum: ast.AST) -> Iterator[str]:
    in_src = pfad.startswith("src/")
    for knoten in ast.walk(baum):
        if isinstance(knoten, ast.Call):
            name = _name(knoten.func)
            if in_src and pfad not in UHR_ERLAUBT and _ist_uhr(knoten):
                yield "uhr"
            if pfad.startswith(REPORT) and _DATEIZUGRIFF.fullmatch(name or ""):
                yield "dateizugriff"
        elif isinstance(knoten, ast.ExceptHandler) and in_src:
            if _ist_breit(knoten.type):
                yield "breite-ausnahme"
        elif VERBOTENE_HOOKS.fullmatch(
            str(getattr(knoten, "name", None) or getattr(knoten, "value", ""))
        ):
            yield "pytest-hook"
        elif isinstance(knoten, ast.Name) and knoten.id == "pytest_plugins":
            yield "pytest-plugins"


def _name(knoten: object) -> str | None:
    return getattr(knoten, "id", None) or getattr(knoten, "attr", None)


def _ist_breit(typ: ast.expr | None) -> bool:
    if isinstance(typ, ast.Tuple):
        return any(_ist_breit(element) for element in typ.elts)
    return typ is None or _name(typ) in ("Exception", "BaseException")


def _dateien(
    wurzel: Path, ordner: tuple[str, ...], endungen: Iterable[str]
) -> Iterator[tuple[str, str]]:
    for muster in ordner:
        for datei in sorted(wurzel.glob(muster)):
            if datei.suffix in endungen and "__pycache__" not in datei.parts:
                text = datei.read_text(encoding="utf-8", errors="replace")
                yield datei.relative_to(wurzel).as_posix(), text
