"""Was Stufe 0 je Datei zählt: Größe, Kommentare, Syntaxbaum, Farben, Konfiguration.

Gezählt wird je Datei und Code; die Basen und den Vergleich hält ``waechter.py``.
"""

from __future__ import annotations

import ast
import io
import os
import re
import shlex
import tokenize
import tomllib
from collections import Counter
from collections.abc import Iterable, Iterator
from pathlib import Path

import waechter_kommentare
import waechter_speicher

RIESEN_GRENZE = 400
CODE_ORDNER = ("src/**/*", "scripts/**/*", "tools/**/*", "service/**/*")
_RUFF_MYPY = {"pyproject.toml", "ruff.toml", ".ruff.toml", "mypy.ini", ".mypy.ini"}
_PYTEST = {"pytest.ini", ".pytest.ini", "pytest.toml", ".pytest.toml", "tox.ini"}
_PYTHON = {"conftest.py", "sitecustomize.py", "usercustomize.py", "setup.cfg"}
_PLUGIN = "leiter_roh"
KONFIG_NAMEN = frozenset(
    {*_RUFF_MYPY, *_PYTEST, *_PYTHON, ".importlinter", f"{_PLUGIN}.py", _PLUGIN}
)
KONFIG_ERLAUBT = frozenset(
    {"pyproject.toml", ".importlinter", f"scripts/leiter_plugin/{_PLUGIN}.py"}
)
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
_WERKZEUG_AUS = re.compile(
    r"mypy:\s*ignore-errors|fmt:\s*(?:off|skip)|isort:\s*(?:off|skip)"
)
_RUFF_AUS = re.compile(r"^#\s*ruff:\s*disable\b(?:\[([^\]]*)\])?", re.I | re.M)
_MYPY_AUS = re.compile(r"^#\s*mypy:\s*(?!ignore-errors)(.*)", re.I | re.M)
_ABSCHALTER = (_NOQA, _TYPE_IGNORE, _WERKZEUG_AUS, _RUFF_AUS, _MYPY_AUS)
KOMMENTAR_ORDNER = (*CODE_ORDNER, "tests/**/*")
_KEIN_TYPCHECK = frozenset({"no_type_check", "no_type_check_decorator"})
_UHREN = frozenset(
    {
        "time.time",
        "time.time_ns",
        "datetime.datetime.now",
        "datetime.datetime.utcnow",
        "datetime.datetime.today",
        "datetime.date.today",
    }
)
_UHR_OHNE_ZEIT = frozenset(
    {"time.localtime", "time.gmtime", "time.ctime", "time.asctime"}
)
_EINGRIFF_MODULE = ("_pytest", "pluggy", "leiter_roh")
_EINGRIFF_TEXTE = frozenset({"leiter_roh", "TELCO_LEITER_ROH"})
EINGRIFF_ERLAUBT = (
    "scripts/leiter_plugin/",
    "scripts/leiter_pytest.py",
    "scripts/waechter_regeln.py",
)
ANKER_NAME = "ANKER"
_PLUGINS = "_".join(("pytest", "plugins"))

Schluessel = tuple[str, str]


def riesendateien(wurzel: Path) -> Counter[Schluessel]:
    zeilen = {p: len(t.splitlines()) for p, t in _dateien(wurzel, CODE_ORDNER, {".py"})}
    return Counter({(p, "zeilen"): n for p, n in zeilen.items() if n > RIESEN_GRENZE})


def waechter_zaehlung(wurzel: Path) -> Counter[Schluessel]:
    zaehlung: Counter[Schluessel] = Counter()
    alle = list(_dateien(wurzel, (*CODE_ORDNER, "tests/**/*"), {".py"}))
    codes = waechter_speicher.je_datei("regeln", alle, _codes_je_datei, PARALLEL_AB)
    zaehlung.update((p, c) for (p, _), je in zip(alle, codes, strict=True) for c in je)
    for pfad, text in _dateien(wurzel, ("src/**/*",), FARB_ENDUNGEN):
        if pfad != FARBEN_ERLAUBT:
            ohne_root = _ROOT.sub("", text, count=1) if pfad == STYLE else text
            zaehlung[(pfad, "hexfarbe")] += len(_HEX.findall(ohne_root))
    zaehlung.update((pfad, "fremde-konfig") for pfad in fremde_konfig(wurzel))
    zaehlung["pyproject.toml", "pytest-plugin-option"] += _plugin_optionen(wurzel)
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
        for name in sorted(KONFIG_NAMEN.intersection([*namen, *unterordner])):
            pfad = name if relativ == "." else f"{relativ}/{name}"
            unter_tests = name == "conftest.py" and pfad.startswith(CONFTEST_ORDNER)
            if pfad not in KONFIG_ERLAUBT and not unter_tests:
                yield pfad


def _plugin_optionen(wurzel: Path) -> int:
    """Zählt ``-p`` in ``addopts`` von pytest: ein Weg, Plugins einzuschleusen."""
    datei = wurzel / "pyproject.toml"
    try:
        werkzeuge = tomllib.loads(datei.read_text("utf-8")).get("tool", {})
    except (OSError, tomllib.TOMLDecodeError):
        return 0
    pytest = werkzeuge.get("pytest", {})
    anzahl = 0
    for optionen in (
        pytest.get("ini_options", {}).get("addopts", ""),
        pytest.get("addopts", ""),
    ):
        try:
            teile = (
                shlex.split(optionen) if isinstance(optionen, str) else list(optionen)
            )
        except ValueError:
            anzahl += 1
            continue
        anzahl += sum(str(t).startswith(("-p", "--plugin")) for t in teile)
    return anzahl


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
        aliase = importnamen(baum)
        anzahl += sum(
            ist_uhr(k, aliase) and id(k) not in innen
            for k in ast.walk(baum)
            if isinstance(k, ast.Call)
        )
    return anzahl


def _kommentar_codes(text: str) -> Iterator[str]:
    if not any(m.search(text) for m in _ABSCHALTER):
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
        for treffer in _RUFF_AUS.finditer(kommentar):
            codes = re.findall(r"[A-Z]+[0-9]+", treffer.group(1) or "") or ["alle"]
            yield from (f"ruff-aus:{c}" for c in codes)
        treffer = _MYPY_AUS.search(kommentar)
        if treffer and not _WERKZEUG_AUS.search(kommentar):
            yield from _mypy_aus(treffer.group(1))


def _mypy_aus(einstellung: str) -> Iterator[str]:
    """Zählt eine Inline-Einstellung von mypy je abgeschaltetem Code oder Schalter."""
    for teil in re.split(r",\s*(?=[a-z-]+\s*(?:=|,|$))", einstellung.strip()):
        name, _, wert = teil.partition("=")
        if name.strip() == "disable-error-code":
            codes = re.findall(r"[a-z][\w-]*", wert) or ["alle"]
            yield from (f"mypy-aus:{c}" for c in codes)
        elif name.strip():
            yield f"mypy-aus:{name.strip()}"


def kommentar_dateien(wurzel: Path) -> list[str]:
    """Die Python-Dateien, deren Kommentare das Löschwerkzeug und Stufe 0 behandeln."""
    return [p for p, _ in _dateien(wurzel, KOMMENTAR_ORDNER, {".py"})]


def _codes_je_datei(datei: tuple[str, str]) -> list[str]:
    pfad, text = datei
    codes = list(_kommentar_codes(text))
    codes += ["kommentar"] * len(waechter_kommentare.freie_kommentare(text))
    try:
        codes += _ast_codes(pfad, ast.parse(text))
    except SyntaxError:
        codes.append("syntaxfehler")
    return codes


def ist_uhr(aufruf: ast.Call, aliase: dict[str, str] | None = None) -> bool:
    name, basis = _name(aufruf.func), _name(getattr(aufruf.func, "value", None))
    if bool(basis) and (name in ("now", "utcnow", "today") or name == basis == "time"):
        return True
    voll = _voller_name(aufruf.func, aliase or {})
    return voll in _UHREN or (
        (voll in _UHR_OHNE_ZEIT and not aufruf.args)
        or (voll == "time.strftime" and len(aufruf.args) == 1)
    )


def uhr_verweise(baum: ast.AST, aliase: dict[str, str]) -> int:
    """Zählt Uhren, die ohne Aufruf weitergereicht werden: ``jetzt = time.time``."""
    aufgerufen = {id(k.func) for k in ast.walk(baum) if isinstance(k, ast.Call)}
    return sum(
        isinstance(k, ast.Name | ast.Attribute)
        and id(k) not in aufgerufen
        and _voller_name(k, aliase) in _UHREN
        for k in ast.walk(baum)
    )


def _eingriffe(pfad: str, baum: ast.AST) -> int:
    """Zählt Importe von pytest-Interna, Zuweisungen an ``__code__``, Nennungen des
    Leiterplugins und, in ``conftest.py``, Zugriffe auf ``sys.modules``."""
    if pfad.startswith(EINGRIFF_ERLAUBT):
        return 0
    anzahl = 0
    for k in ast.walk(baum):
        module = (
            [a.name for a in getattr(k, "names", [])]
            if isinstance(k, ast.Import)
            else []
        )
        if isinstance(k, ast.ImportFrom):
            module = [k.module or ""]
        anzahl += sum(m.split(".")[0] in _EINGRIFF_MODULE for m in module)
        if isinstance(k, ast.Attribute):
            anzahl += k.attr == "__code__" and not isinstance(k.ctx, ast.Load)
            anzahl += k.attr == "modules" and pfad.endswith("conftest.py")
        if isinstance(k, ast.Constant) and isinstance(k.value, str):
            anzahl += k.value in _EINGRIFF_TEXTE or k.value.startswith("_pytest")
    return anzahl


def importnamen(baum: ast.AST) -> dict[str, str]:
    """Bildet jeden importierten Namen der Datei auf seinen vollen Namen ab."""
    aliase = {}
    for knoten in ast.walk(baum):
        if isinstance(knoten, ast.Import):
            for a in knoten.names:
                aliase[a.asname or a.name.split(".")[0]] = (
                    a.name if a.asname else a.name.split(".")[0]
                )
        elif isinstance(knoten, ast.ImportFrom) and knoten.module:
            for a in knoten.names:
                aliase[a.asname or a.name] = f"{knoten.module}.{a.name}"
    return aliase


def _voller_name(knoten: ast.expr, aliase: dict[str, str]) -> str | None:
    if isinstance(knoten, ast.Name):
        return aliase.get(knoten.id, knoten.id)
    if isinstance(knoten, ast.Attribute):
        basis = _voller_name(knoten.value, aliase)
        return f"{basis}.{knoten.attr}" if basis else None
    if isinstance(knoten, ast.Call) and _name(knoten.func) in (
        "__import__",
        "import_module",
    ):
        modul = knoten.args[0] if knoten.args else None
        return modul.value if isinstance(modul, ast.Constant) else None
    return None


def _ast_codes(pfad: str, baum: ast.AST) -> Iterator[str]:
    in_src = pfad.startswith("src/")
    aliase = importnamen(baum)
    yield from ["leiter-eingriff"] * _eingriffe(pfad, baum)
    if in_src and pfad not in UHR_ERLAUBT:
        yield from ["uhr"] * uhr_verweise(baum, aliase)
    for knoten in ast.walk(baum):
        if _letzter_name(knoten, aliase) in _KEIN_TYPCHECK:
            yield "kein-typcheck"
        if isinstance(knoten, ast.Call):
            name = _name(knoten.func)
            if in_src and pfad not in UHR_ERLAUBT and ist_uhr(knoten, aliase):
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
        elif _PLUGINS in (_name(knoten), getattr(knoten, "value", None)):
            yield "pytest-plugins"


def _letzter_name(knoten: ast.AST, aliase: dict[str, str]) -> str | None:
    if isinstance(knoten, ast.Name):
        return aliase.get(knoten.id, knoten.id).rsplit(".", 1)[-1]
    return knoten.attr if isinstance(knoten, ast.Attribute) else None


def anker_aus_text(text: str, streng: bool = False) -> tuple[str | None, str]:
    """Liest den Anker aus dem Text von ``scripts/waechter.py``.

    Streng gilt er nur, wenn der Name genau einmal gebunden ist, als Zeichenkette auf
    oberster Ebene, und nirgends sonst als Name, Attribut, Import oder Text vorkommt;
    sonst kommt ``None`` mit dem Grund zurück.
    """
    try:
        baum = ast.parse(text)
    except SyntaxError:
        return None, "nicht lesbar"
    oben = [
        k
        for k in baum.body
        if isinstance(k, ast.Assign | ast.AnnAssign)
        and [_name(z) for z in getattr(k, "targets", [getattr(k, "target", None)])]
        == [ANKER_NAME]
    ]
    wert = getattr(oben[0], "value", None) if oben else None
    if not isinstance(wert, ast.Constant) or not isinstance(wert.value, str):
        return None, "nicht lesbar"
    if streng and sum(map(_nennt_anker, ast.walk(baum))) != 1:
        return None, "nicht eindeutig: der Name darf nur einmal gebunden werden"
    return wert.value, ""


def _nennt_anker(knoten: ast.AST) -> bool:
    """Wahr für jede Bindung des Ankernamens und jede Zeichenkette, die ihn nennt."""
    if isinstance(knoten, ast.Name | ast.Attribute):
        return _name(knoten) == ANKER_NAME and not isinstance(knoten.ctx, ast.Load)
    if isinstance(knoten, ast.Global | ast.Nonlocal):
        return ANKER_NAME in knoten.names
    if isinstance(knoten, ast.alias):
        return ANKER_NAME in (knoten.asname, knoten.name.rsplit(".", 1)[-1])
    if isinstance(knoten, ast.Constant):
        return isinstance(knoten.value, str) and ANKER_NAME in knoten.value.split()
    namen = ("name", "arg")
    return any(getattr(knoten, n, None) == ANKER_NAME for n in namen)


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
