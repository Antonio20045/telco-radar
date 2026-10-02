"""Stufe 0 der Prüfleiter: zählt, was nur schrumpfen darf, und sperrt Lockerungen.

Gezählt wird je Datei und Code gegen drei Basen unter ``pruef/``. Keine Basis- oder
Ausnahmeliste darf seit ``ANKER`` in einem Commit oder im Arbeitsstand lockerer
werden, außer in einem Commit mit einer Zeile ``Lockerung: <Grund>``.
"""

from __future__ import annotations

import ast
import configparser
import io
import json
import re
import subprocess
import tokenize
import tomllib
from collections import Counter
from collections.abc import Callable, Iterable, Iterator
from functools import partial
from pathlib import Path

WURZEL = Path(__file__).resolve().parents[1]
RIESEN_BASIS = "pruef/riesendateien.txt"
PRIVAT_BASIS = "pruef/privat-basis.txt"
WAECHTER_BASIS = "pruef/waechter-basis.txt"
ANKER = "77d68537c80134513dd784d005136a561a6b467b"
RIESEN_GRENZE = 400
CODE_ORDNER = ("src/**/*", "scripts/**/*", "tools/**/*", "service/**/*")
FREMDE_KONFIG = ("*ruff.toml", "*mypy.ini", "pytest.ini", "tox.ini")
REPORT = "src/telco_radar/report/"
UHR_ERLAUBT = frozenset(
    f"src/telco_radar/{p}.py" for p in ("pipeline", "geraete_pipeline", "collect/http")
)
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


def riesendateien(wurzel: Path) -> Counter[Schluessel]:
    zeilen = {p: len(t.splitlines()) for p, t in _dateien(wurzel, CODE_ORDNER, {".py"})}
    return Counter({(p, "zeilen"): n for p, n in zeilen.items() if n > RIESEN_GRENZE})


def waechter_zaehlung(wurzel: Path) -> Counter[Schluessel]:
    zaehlung: Counter[Schluessel] = Counter()
    for pfad, text in _dateien(
        wurzel, (*CODE_ORDNER, "tests/**/*", "conftest.py"), {".py"}
    ):
        zaehlung.update((pfad, code) for code in _kommentar_codes(text))
        try:
            zaehlung.update((pfad, code) for code in _ast_codes(pfad, ast.parse(text)))
        except SyntaxError:
            zaehlung[(pfad, "syntaxfehler")] += 1
    for pfad, text in _dateien(wurzel, ("src/**/*",), FARB_ENDUNGEN):
        if pfad != FARBEN_ERLAUBT:
            ohne_root = _ROOT.sub("", text, count=1) if pfad == STYLE else text
            zaehlung[(pfad, "hexfarbe")] += len(_HEX.findall(ohne_root))
    for pfad, _ in _dateien(wurzel, FREMDE_KONFIG, {".toml", ".ini"}):
        zaehlung[(pfad, "fremde-konfig")] += 1
    for pfad, text in _dateien(wurzel, (".github/workflows/*",), {".yml", ".yaml"}):
        for zeile in text.splitlines():
            zaehlung[(pfad, "oder-true")] += len(re.findall(r"\|\|\s*true\b", zeile))
            if re.search(r"continue-on-error:\s*(?!false\b)\S", zeile):
                zaehlung[(pfad, "continue-on-error")] += 1
            if re.match(r"\s*python-version:", zeile):
                zaehlung[(pfad, "python-version")] += 1
    return +zaehlung


def pruefe(
    wurzel: Path, privat: Counter[Schluessel], schreiben: bool = True
) -> tuple[list[str], list[Path]]:
    """Gibt rote Zeilen und gesenkte Basen zurück; gesenkt wird nur bei Grün."""
    rot = lockerungen(wurzel)
    paare = [
        (RIESEN_BASIS, riesendateien(wurzel)),
        (PRIVAT_BASIS, privat),
        (WAECHTER_BASIS, waechter_zaehlung(wurzel)),
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
    """Meldet jede Liste, die seit ``ANKER`` lockerer wurde, je Commit und Stand."""
    try:
        bereich = [f"{ANKER}..HEAD", "--", *LISTEN]
        commits = _git(wurzel, "rev-list", "--reverse", *bereich).split()
        erlaubt = _git(wurzel, "rev-list", "--grep=^Lockerung:", *bereich).split()
    except subprocess.CalledProcessError:
        return [f"Verlauf ab {ANKER[:7]} fehlt; erst `git fetch --unshallow`"]
    alt = {p: _inhalt(wurzel, ANKER, p) for p in LISTEN}
    meldungen = []
    for commit in [*commits, None]:
        for pfad, vergleich in LISTEN.items():
            neu = _inhalt(wurzel, commit, pfad)
            vorher = alt[pfad]
            if vorher is not None and commit not in erlaubt:
                ort = commit[:7] if commit else "Arbeitsstand"
                meldungen += [
                    f"{pfad} lockerer ({ort}): {zeile}"
                    for zeile in vergleich(vorher, neu or "")
                ]
            alt[pfad] = neu if vorher is None else neu or ""
    return meldungen


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
    namen = ("ruff", "mypy")
    return [f"{k} geändert" for k in namen if vorher.get(k) != nachher.get(k)]


def _neu_in(alt: str, neu: str) -> list[str]:
    zeilen = {z.strip() for z in neu.splitlines()} - set(
        map(str.strip, alt.splitlines())
    )
    return sorted(z for z in zeilen if z)


LISTEN: dict[str, Callable[[str, str], list[str]]] = {
    "pruef/ruff-basis.json": partial(_zaehl_lockerer, als_json=True),
    "pruef/mypy-basis.txt": _zaehl_lockerer,
    PRIVAT_BASIS: _zaehl_lockerer,
    RIESEN_BASIS: _zaehl_lockerer,
    WAECHTER_BASIS: _zaehl_lockerer,
    "pruef/rot-bekannt.txt": _menge_lockerer,
    "pruef/tests-anzahl.txt": partial(_grenze_lockerer, richtung=1),
    "pruef/tests-uebersprungen.txt": partial(_grenze_lockerer, richtung=-1),
    ".importlinter": _vertraege_lockerer,
    "pyproject.toml": _werkzeuge_lockerer,
}


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


def _ast_codes(pfad: str, baum: ast.AST) -> Iterator[str]:
    in_src = pfad.startswith("src/")
    for knoten in ast.walk(baum):
        if isinstance(knoten, ast.Call):
            name, basis = _name(knoten.func), _name(getattr(knoten.func, "value", None))
            uhr = name in ("now", "utcnow", "today") or name == basis == "time"
            if in_src and pfad not in UHR_ERLAUBT and basis and uhr:
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


def _inhalt(wurzel: Path, commit: str | None, pfad: str) -> str | None:
    if commit is None:
        datei = wurzel / pfad
        return datei.read_text(encoding="utf-8") if datei.exists() else None
    lauf = subprocess.run(
        ["git", "show", f"{commit}:{pfad}"], cwd=wurzel, capture_output=True, text=True
    )
    return lauf.stdout if lauf.returncode == 0 else None


def _git(wurzel: Path, *argumente: str) -> str:
    return subprocess.run(
        ["git", *argumente], cwd=wurzel, capture_output=True, text=True, check=True
    ).stdout
