"""Schnelle Leiter für pre-commit: Stufen 0, 1 und 4 auf den geänderten Dateien.

Stufe 4 wählt die Tests, die ein geändertes Modul direkt importieren, ohne die
Marker ``browser``, ``langsam``, ``golden`` und ``netz``; als langsam zählt auch
jeder Test, der im letzten Volllauf länger als ``LANGSAM_SEKUNDEN`` lief. Von den
gemessenen Tests laufen die schnellsten, bis ``TESTBUDGET_SEKUNDEN`` gefüllt ist,
Tests geänderter Testdateien zuerst; selbst geänderte laufen immer (``nachlauf``).
Vorlagen, ``style.css`` und ``app.js`` ziehen die Tests mit Marker ``seite`` und die,
die ``report.html`` importieren. ``config/``, ``pyproject.toml``,
``requirements*.txt`` und jede ``conftest.py`` betreffen alle Tests; das prüft
Stufe 5 im pre-push. Ab ``PARALLEL_AB_SEKUNDEN`` geschätzter Laufzeit läuft pytest
mit ``-n 4``, nach ``KAPPE_SEKUNDEN`` bricht die Stufe mit einer Warnung ab.
"""

from __future__ import annotations

import ast
import json
import signal
import subprocess
import sys
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from functools import partial
from pathlib import Path, PurePosixPath
from typing import TextIO

import pruefstempel
import waechter_speicher
from geaenderte_tests import geaenderte_tests, nachlauf, ohne
from leiter_befunde import WURZEL, Ergebnis, neue_befunde, rote_zeilen, ruff_befunde
from waechter import lies_zaehlbasis

PARALLEL_AB_SEKUNDEN = 4.0
TESTBUDGET_SEKUNDEN = 8.0
KAPPE_SEKUNDEN = 45
ZEITEN = ".pruefleiter/testzeiten.json"
ABGEBROCHEN = f"abgebrochen nach {KAPPE_SEKUNDEN} s"
BUDGET_SEKUNDEN = 30
UNBEKANNT_SEKUNDEN = 1.0
LANGSAM_SEKUNDEN = 5.0
OHNE_MARKER = "not browser and not langsam and not golden and not netz"
VORLAGEN = "src/telco_radar/report/templates/"
VORLAGEN_MODUL = "telco_radar.report.html"
_ALLE_TESTS = ("config/", "pyproject.toml", "requirements", "conftest.py")
_KOPFLOS = ("scripts", "tools", "tests")
_LADER = ("spec_from_file_location", "import_module")
SEITE = "@marker-seite"
KAPUTT = "@syntaxfehler"


Lauf = Callable[..., "subprocess.CompletedProcess[str]"]


@dataclass
class Auswahl:
    """Testdateien für Stufe 4; ``alle`` heißt, die Änderung betrifft jeden Test."""

    dateien: list[str] = field(default_factory=list)
    alle: list[str] = field(default_factory=list)


def geaenderte_dateien(wurzel: Path, nur_vorgemerkt: bool) -> list[str]:
    """Gibt die vorgemerkten oder alle gegen HEAD geänderten, neuen und gelöschten.

    Vorgemerkt liest den Index des Hooks (``GIT_INDEX_FILE``), sonst den eigenen.
    """
    vorgemerkt = pruefstempel.git(
        wurzel, "diff", "--cached", "--name-only", mit_hook=nur_vorgemerkt
    ).split()
    if nur_vorgemerkt:
        return vorgemerkt
    geaendert = pruefstempel.git(wurzel, "diff", "--name-only").split()
    neu = pruefstempel.git(wurzel, "ls-files", "--others", "--exclude-standard")
    return sorted({*vorgemerkt, *geaendert, *neu.split()})


def modulnamen(pfad: str) -> set[str]:
    """Gibt die Namen, unter denen ein Test die Datei ``pfad`` importieren kann."""
    datei = PurePosixPath(pfad)
    if datei.suffix != ".py":
        return set()
    teile = list(datei.with_suffix("").parts)
    if teile[-1] == "__init__":
        teile.pop()
    if teile[:1] == ["src"]:
        return {".".join(teile[1:])} if len(teile) > 1 else set()
    namen = {".".join(teile)}
    if teile[:1] in ([k] for k in _KOPFLOS) and len(teile) > 1:
        namen |= {".".join(teile[1:]), teile[-1]}
    return namen


def importe(quelltext: str) -> set[str]:
    """Gibt die Module, die eine Testdatei direkt importiert oder per Namen lädt."""
    namen: set[str] = set()
    for knoten in ast.walk(ast.parse(quelltext)):
        if isinstance(knoten, ast.Import):
            namen |= {alias.name for alias in knoten.names}
        elif isinstance(knoten, ast.ImportFrom) and knoten.module:
            namen.add(knoten.module)
            namen |= {f"{knoten.module}.{alias.name}" for alias in knoten.names}
        elif isinstance(knoten, ast.Call) and _lader(knoten.func) and knoten.args:
            erstes = knoten.args[0]
            if isinstance(erstes, ast.Constant) and isinstance(erstes.value, str):
                namen.add(erstes.value)
    return namen


def hat_marker_seite(quelltext: str) -> bool:
    """Wahr, wenn die Datei den Marker ``seite`` an einen Test oder das Modul hängt."""
    return any(
        isinstance(k, ast.Attribute)
        and k.attr == "seite"
        and isinstance(k.value, ast.Attribute)
        and k.value.attr == "mark"
        for k in ast.walk(ast.parse(quelltext))
    )


def testdateien(wurzel: Path) -> list[str]:
    """Gibt alle Testdateien ``tests/**/test_*.py`` und ``*_test.py`` relativ."""
    return sorted(
        str(p.relative_to(wurzel))
        for muster in ("test_*.py", "*_test.py")
        for p in (wurzel / "tests").rglob(muster)
    )


def betroffene(wurzel: Path, geaendert: Iterable[str]) -> Auswahl:
    """Wählt die Testdateien, die eine der geänderten Dateien direkt betrifft."""
    auswahl = Auswahl()
    module: set[str] = set()
    seite = False
    for pfad in geaendert:
        name = PurePosixPath(pfad).name
        if pfad.startswith(_ALLE_TESTS) or name in _ALLE_TESTS:
            auswahl.alle.append(pfad)
        elif pfad.startswith(VORLAGEN):
            module.add(VORLAGEN_MODUL)
            seite = True
        else:
            module |= modulnamen(pfad)
    alle_tests = testdateien(wurzel)
    gewaehlt = {p for p in geaendert if p in alle_tests}
    for test in alle_tests:
        text = (wurzel / test).read_text(encoding="utf-8", errors="replace")
        merkmale = set(
            waechter_speicher.hole("importe", test, text, partial(_merkmale, text))
        )
        if merkmale & module or (seite and SEITE in merkmale) or KAPUTT in merkmale:
            gewaehlt.add(test)
    auswahl.dateien = sorted(gewaehlt)
    return auswahl


def _merkmale(text: str) -> list[str]:
    try:
        seite = [SEITE] if hat_marker_seite(text) else []
        return sorted(importe(text)) + seite
    except SyntaxError:
        return [KAPUTT]


def schaetzung(
    dateien: Iterable[str], zeiten: Mapping[str, float], abgewaehlt: Iterable[str]
) -> float:
    """Summiert die gemessene Laufzeit der Tests, die Stufe 4 laufen lässt.

    Wie in ``abwahl`` kostet der erste laufende Test einer Datei ihren Einstieg
    (``einstiege``), eine Datei ohne Messung ``UNBEKANNT_SEKUNDEN``.
    """
    gewaehlt, ohne = list(dateien), set(abgewaehlt)
    einstieg = einstiege(gewaehlt, zeiten)
    summe = 0.0
    for datei in gewaehlt:
        eigene = {t: s for t, s in zeiten.items() if t.partition("::")[0] == datei}
        behalten = sorted(s for t, s in eigene.items() if t not in ohne)
        if not eigene:
            summe += UNBEKANNT_SEKUNDEN
        elif behalten:
            summe += max(einstieg[datei], behalten[0]) + sum(behalten[1:])
    return summe


def einstiege(dateien: Iterable[str], zeiten: Mapping[str, float]) -> dict[str, float]:
    """Gibt je Datei den teuersten Test bis ``LANGSAM_SEKUNDEN``: so viel kostet ihr
    erster Test, weil er die gemeinsamen Fixtures der Datei aufbaut."""
    gewaehlt = set(dateien)
    einstieg: dict[str, float] = {}
    for nodeid, sekunden in zeiten.items():
        datei = nodeid.partition("::")[0]
        if datei in gewaehlt:
            schnell = sekunden if sekunden <= LANGSAM_SEKUNDEN else 0.0
            einstieg[datei] = max(einstieg.get(datei, 0.0), schnell)
    return einstieg


def langsame(dateien: Iterable[str], zeiten: Mapping[str, float]) -> list[str]:
    """Gibt die Tests der Dateien, die zuletzt länger als ``LANGSAM_SEKUNDEN`` liefen.

    Wie der Marker ``langsam`` laufen sie erst in Stufe 5 im pre-push.
    """
    gewaehlt = set(dateien)
    return sorted(
        t
        for t, s in zeiten.items()
        if s > LANGSAM_SEKUNDEN and t.partition("::")[0] in gewaehlt
    )


def abwahl(
    dateien: Iterable[str], zeiten: Mapping[str, float], vorrang: Iterable[str] = ()
) -> list[str]:
    """Gibt die gemessenen Tests der Dateien, die Stufe 4 nicht laufen lässt.

    Das sind die langsamen und alle, die nach den schnellsten nicht mehr in
    ``TESTBUDGET_SEKUNDEN`` passen; Tests der Dateien in ``vorrang`` kommen zuerst.
    Der erste Test einer Datei kostet ihren Einstieg (``einstiege``). Ungemessene
    Tests laufen immer, weil sie sich nicht abwählen lassen; eine ungemessene Datei
    belegt vorab ``UNBEKANNT_SEKUNDEN``. Was hier fehlt, prüft Stufe 5 im pre-push.
    """
    gewaehlt, zuerst = set(dateien), set(vorrang)
    lang = set(langsame(gewaehlt, zeiten))
    einstieg = einstiege(gewaehlt, zeiten)
    kandidaten = sorted(
        (t.partition("::")[0] not in zuerst, s, t)
        for t, s in zeiten.items()
        if t.partition("::")[0] in gewaehlt and t not in lang
    )
    summe = UNBEKANNT_SEKUNDEN * len(gewaehlt - set(einstieg))
    betreten, ueber = set[str](), list[str]()
    for _, sekunden, nodeid in kandidaten:
        datei = nodeid.partition("::")[0]
        kosten = sekunden if datei in betreten else max(einstieg[datei], sekunden)
        if summe + kosten > TESTBUDGET_SEKUNDEN:
            ueber.append(nodeid)
        else:
            summe += kosten
            betreten.add(datei)
    return sorted(lang | set(ueber))


def lies_testzeiten(datei: Path) -> dict[str, float]:
    """Liest die Laufzeit je Test aus dem letzten Volllauf; fehlt sie, leer."""
    try:
        tests = json.loads(datei.read_text("utf-8")).get("tests", {})
        return {str(k): float(v) for k, v in tests.items()}
    except (OSError, ValueError, AttributeError):
        return {}


def schreibe_testzeiten(roh: Path, ziel: Path) -> None:
    """Fasst die Startzeiten aus dem Leiterplugin zu Sekunden je Test zusammen.

    Ein Test dauert bis zum Start des nächsten im selben Prozess; der letzte Test
    jedes Prozesses zählt ``UNBEKANNT_SEKUNDEN``. Ohne Aufzeichnung bleibt die
    letzte Messung stehen.
    """
    je_test: dict[str, float] = {}
    for datei in sorted(roh.glob("*.zeit")):
        zeilen = datei.read_text("utf-8", errors="replace").splitlines()
        starts = [z.split(" ", 1) for z in zeilen if _ist_startzeile(z)]
        enden = [float(start) for start, _ in starts[1:]]
        for (start, nodeid), ende in zip(starts, [*enden, None], strict=True):
            dauer = UNBEKANNT_SEKUNDEN if ende is None else ende - float(start)
            je_test[nodeid] = round(dauer, 3)
    if not je_test:
        return
    ziel.parent.mkdir(parents=True, exist_ok=True)
    roh = json.dumps({"tests": dict(sorted(je_test.items()))}, indent=0)
    ziel.write_text(roh + "\n", encoding="utf-8")


def _ist_startzeile(zeile: str) -> bool:
    zeit, _, nodeid = zeile.partition(" ")
    return bool(nodeid) and zeit.replace(".", "", 1).isdigit()


def pytest_befehl(
    dateien: list[str], geschaetzt: float, abwahl: Iterable[str] = ()
) -> list[str]:
    """Baut den Aufruf für Stufe 4; ab der Schwelle mit vier Workern."""
    worker = "4" if geschaetzt >= PARALLEL_AB_SEKUNDEN else "0"
    abgewaehlt = [f"--deselect={nodeid}" for nodeid in abwahl]
    return [
        sys.executable,
        "-m",
        "pytest",
        "-q",
        "-rfE",
        "-p",
        "no:cacheprovider",
        "-m",
        OHNE_MARKER,
        "-n",
        worker,
        *abgewaehlt,
        *dateien,
    ]


def budget_warnung(sekunden: float) -> list[str]:
    """Gibt eine Warnung, wenn die schnelle Leiter ihr Budget überschreitet."""
    if sekunden <= BUDGET_SEKUNDEN:
        return []
    return [
        f"Warnung: {sekunden:.0f} s, Budget der schnellen Leiter {BUDGET_SEKUNDEN} s"
    ]


def mit_speicher(
    stufe: Callable[[TextIO], Ergebnis], datei: Path
) -> Callable[[TextIO], Ergebnis]:
    """Lässt Stufe 0 je Dateiinhalt Ergebnisse aus ``datei`` wiederverwenden."""

    def gespeichert(log: TextIO) -> Ergebnis:
        with waechter_speicher.aktiv(datei):
            return stufe(log)

    return gespeichert


def stufe_lint(
    log: TextIO, lauf: Lauf, ruff: str, dateien: list[str], basis: Path
) -> Ergebnis:
    """Stufe 1 auf den geänderten Python-Dateien; senkt keine Basis."""
    python = [d for d in dateien if d.endswith(".py") and (WURZEL / d).is_file()]
    if not python:
        return Ergebnis("1 Lint", True)
    form = lauf(log, [ruff, "format", "--check", *python])
    if form.returncode not in (0, 1):
        return Ergebnis("1 Lint", False, ["ruff format bricht ab:", *_zeilen(form)])
    if form.returncode == 1:
        nicht = [z for z in form.stdout.splitlines() if z.startswith("Would reformat")]
        return Ergebnis("1 Lint", False, ["ruff format: nicht formatiert", *nicht])
    pruefung = lauf(log, [ruff, "check", "--output-format", "json", *python])
    if pruefung.returncode not in (0, 1):
        return Ergebnis("1 Lint", False, ["ruff check bricht ab:", *_zeilen(pruefung)])
    zaehlbasis = lies_zaehlbasis(basis)
    zeilen = [
        f"{b.pfad}:{b.zeile} [{b.code}] erwartet höchstens {zaehlbasis[b.schluessel]}"
        f" je Datei: {b.text}"
        for b in neue_befunde(ruff_befunde(pruefung.stdout), zaehlbasis)
    ]
    return Ergebnis("1 Lint", not zeilen, zeilen)


def stufe_betroffen(
    log: TextIO, lauf: Lauf, wurzel: Path, dateien: list[str], zeiten: Path
) -> Ergebnis:
    """Stufe 4: Tests der direkt importierten geänderten Module, ohne lange Marker."""
    with waechter_speicher.aktiv(zeiten.parent / "speicher-tests.json"):
        auswahl = betroffene(wurzel, dateien)
    hinweise = []
    if auswahl.alle:
        alle = ", ".join(auswahl.alle)
        hinweise.append(f"Stufe 4: {alle} betrifft alle Tests, Stufe 5 im pre-push")
    if not auswahl.dateien:
        return Ergebnis("4 Betroffen", True, hinweise=hinweise)
    gemessen = lies_testzeiten(zeiten)
    vorrang = [d for d in dateien if d in auswahl.dateien]
    praefixe = geaenderte_tests(wurzel, vorrang)
    abgewaehlt = ohne(abwahl(auswahl.dateien, gemessen, vorrang), praefixe)
    geschaetzt = schaetzung(auswahl.dateien, gemessen, abgewaehlt)
    if abgewaehlt:
        hinweise.append(
            f"Stufe 4: {len(abgewaehlt)} langsame oder über {TESTBUDGET_SEKUNDEN:g} s"
            " Budget, Stufe 5 im pre-push"
        )
    befehl = pytest_befehl(auswahl.dateien, geschaetzt, abgewaehlt)
    ergebnis = lauf(log, befehl, {"COLUMNS": "1000"}, KAPPE_SEKUNDEN)
    if ergebnis.returncode == -signal.SIGKILL and ABGEBROCHEN in ergebnis.stderr:
        if rot := nachlauf(log, lauf, praefixe, gemessen, pytest_befehl):
            return rot
        hinweise.append(
            f"Warnung: Stufe 4 nach {KAPPE_SEKUNDEN} s gekappt"
            f" ({len(auswahl.dateien)} Dateien, geschätzt {geschaetzt:.0f} s),"
            " den Rest prüft Stufe 5 im pre-push"
        )
        return Ergebnis("4 Betroffen", True, hinweise=hinweise)
    if ergebnis.returncode in (0, 5):
        return Ergebnis("4 Betroffen", True, hinweise=hinweise)
    rot = rote_zeilen(ergebnis.stdout) or [
        f"pytest endet mit {ergebnis.returncode}:",
        *_zeilen(ergebnis)[-20:],
    ]
    return Ergebnis("4 Betroffen", False, rot, hinweise=hinweise)


def _zeilen(lauf: subprocess.CompletedProcess[str]) -> list[str]:
    return (lauf.stdout + lauf.stderr).splitlines()


def _lader(funktion: ast.expr) -> bool:
    name = getattr(funktion, "attr", None) or getattr(funktion, "id", None)
    return name in _LADER
