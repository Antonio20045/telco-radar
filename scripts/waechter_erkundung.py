"""Stufe 0: der Workflow der Klick-Erkundung (Datenkonzept Schritt 5a) hält Grenzen.

Fehlt ``.github/workflows/klick-erkundung.yml``, gilt nichts. Sonst: nur von Hand
(``workflow_dispatch`` mit ``anbieter``, Vorgabe ``alle``), eine eigene
Concurrency-Gruppe ohne Abbruch, ``contents: write`` und nirgends ein Secret oder der
Render-Hook. Jeder Job, der ``scripts/klick_erkunden.py`` erkunden lässt, installiert
Chromium vorher und gibt eine Frist mit; seine ``timeout-minutes`` sind dieselbe Zahl
wie ``JOB_MINUTEN`` der Fristrechnung, und nach Abzug von ``RESERVE_SEKUNDEN`` bleibt
mindestens ``ZEIT_JE_ANBIETER_S`` (CLAUDE.md Regel 8). ``git add`` nimmt nur
``erkundung``, ``git push`` geht ohne jeden Zusatz nur nach
``HEAD:refs/heads/klick-erkundung``, ``git pull`` holt nur ``klick-erkundung``: kein
Force-Push, nie ``main``, nie ``data/`` oder ``site/``.
"""

from __future__ import annotations

import ast
import re
import shlex
from collections.abc import Iterator
from pathlib import Path

import yaml

WORKFLOW = ".github/workflows/klick-erkundung.yml"
ZWEIG = "klick-erkundung"
GRUPPE = "klick-erkundung"
VORGABE = "alle"
SKRIPT = "scripts/klick_erkunden.py"
PLAN = "--plan"
FRIST = "--frist-sekunden"
INSTALLATION = "playwright install"
MINUTEN = "JOB_MINUTEN"
RESERVE = "RESERVE_SEKUNDEN"
MODUL = "src/telco_radar/collect/geraete/klickerkundung.py"
ZEIT_NAME = "ZEIT_JE_ANBIETER_S"
RECHTE = {"contents": "write"}
ERLAUBT = {
    "add": ("erkundung",),
    "push": ("origin", f"HEAD:refs/heads/{ZWEIG}"),
    "pull": ("--rebase", "origin", ZWEIG),
}
VERBOTEN = re.compile(r"secrets\.|render_deploy|RENDER_DEPLOY", re.I)
TRENNER = frozenset({";", "&&", "||", "|", "&", "(", ")", "((", "))"})
GIT_OPTION_MIT_WERT = frozenset({"-c", "-C"})
_RECHENARTEN = {ast.Mult: float.__mul__, ast.Add: float.__add__, ast.Sub: float.__sub__}


def vertrag(wurzel: Path) -> list[str]:
    """Jeder Verstoß des Erkundungs-Workflows als Zeile; ohne Workflow nichts."""
    pfad = wurzel / WORKFLOW
    if not pfad.is_file():
        return []
    try:
        daten = yaml.safe_load(pfad.read_text(encoding="utf-8"))
        return rahmen(daten) + fristjobs(wurzel, daten) + git_befehle(daten)
    except (
        OSError,
        KeyError,
        TypeError,
        ValueError,
        AttributeError,
        yaml.YAMLError,
    ) as fehler:
        return [f"{WORKFLOW}: nicht prüfbar ({type(fehler).__name__}: {fehler})"]


def rahmen(daten: dict) -> list[str]:
    """Auslöser, Concurrency, Rechte und kein Secret."""
    meldungen = []
    ausloeser = daten.get("on", daten.get(True))
    if not isinstance(ausloeser, dict) or set(ausloeser) != {"workflow_dispatch"}:
        meldungen.append(
            f"{WORKFLOW}: Auslöser nur workflow_dispatch, ist {ausloeser!r}"
        )
    else:
        eingaben = (ausloeser["workflow_dispatch"] or {}).get("inputs") or {}
        if (eingaben.get("anbieter") or {}).get("default") != VORGABE:
            meldungen.append(f"{WORKFLOW}: Eingabe anbieter ohne Vorgabe {VORGABE!r}")
    gruppe = daten.get("concurrency") or {}
    if gruppe.get("group") != GRUPPE or gruppe.get("cancel-in-progress") is not False:
        meldungen.append(
            f"{WORKFLOW}: Concurrency-Gruppe {GRUPPE!r} ohne Abbruch, ist {gruppe!r}"
        )
    if daten.get("permissions") != RECHTE:
        meldungen.append(
            f"{WORKFLOW}: permissions {RECHTE!r}, ist {daten.get('permissions')!r}"
        )
    treffer = sorted({t for s in _texte(daten) for t in VERBOTEN.findall(s)})
    if treffer:
        meldungen.append(f"{WORKFLOW}: Secret oder Render-Hook ({', '.join(treffer)})")
    return meldungen


def fristjobs(wurzel: Path, daten: dict) -> list[str]:
    """Jeder Erkundungsjob: Chromium vorher, Frist mit, Zeitgrenze aus einer Zahl."""
    zeit = _zahl(wurzel / MODUL, ZEIT_NAME)
    meldungen = []
    gefunden = False
    for name, job in daten["jobs"].items():
        schritte = job.get("steps") or []
        stellen = [i for i, s in enumerate(schritte) if _erkundet(s)]
        if not stellen:
            continue
        gefunden = True
        ort = f"{WORKFLOW} Job {name}"
        schritt = schritte[stellen[0]]
        vorher = " ".join(str(s.get("run") or "") for s in schritte[: stellen[0]])
        if INSTALLATION not in vorher:
            meldungen.append(f"{ort}: kein {INSTALLATION!r} vor {SKRIPT}")
        lauf = str(schritt["run"])
        fehlt = [w for w in (FRIST, MINUTEN, RESERVE) if w not in lauf]
        if fehlt:
            meldungen.append(f"{ort}: {SKRIPT} ohne {', '.join(fehlt)}")
        umgebung = schritt.get("env") or {}
        minuten = job.get("timeout-minutes")
        if umgebung.get(MINUTEN) != minuten:
            meldungen.append(
                f"{ort}: {MINUTEN} {umgebung.get(MINUTEN)!r}"
                f" ≠ timeout-minutes {minuten!r}"
            )
        elif zeit is None:
            meldungen.append(f"{ort}: {ZEIT_NAME} in {MODUL} nicht lesbar")
        elif minuten * 60 - int(umgebung.get(RESERVE, 0)) < zeit:
            meldungen.append(
                f"{ort}: {minuten} min minus {RESERVE} lassen weniger als"
                f" {ZEIT_NAME} {zeit:g} s"
            )
    if not gefunden:
        meldungen.append(f"{WORKFLOW}: kein Job ruft {SKRIPT} ohne {PLAN}")
    return meldungen


def git_befehle(daten: dict) -> list[str]:
    """``git add``, ``git push`` und ``git pull`` nur mit den erlaubten Argumenten."""
    meldungen = []
    for name, job in daten["jobs"].items():
        for schritt in job.get("steps") or []:
            for befehl, argumente in _git(str(schritt.get("run") or "")):
                soll = ERLAUBT.get(befehl)
                if soll is not None and argumente != soll:
                    ort = f"{WORKFLOW} Job {name}"
                    ist, erlaubt = " ".join(argumente), " ".join(soll)
                    meldungen.append(f"{ort}: git {befehl} {ist} statt {erlaubt}")
    return meldungen


def _erkundet(schritt: dict) -> bool:
    lauf = str(schritt.get("run") or "")
    return SKRIPT in lauf and PLAN not in lauf


def _git(lauf: str) -> Iterator[tuple[str, tuple[str, ...]]]:
    """Unterbefehl und Argumente jedes ``git``-Aufrufs, Kommentarzeilen ausgenommen."""
    for zeile in lauf.replace("\\\n", " ").splitlines():
        if zeile.lstrip().startswith("#"):
            continue
        leser = shlex.shlex(zeile, posix=True, punctuation_chars=True)
        leser.whitespace_split = True
        leser.commenters = ""
        woerter = list(leser)
        for stelle, wort in enumerate(woerter):
            if wort != "git":
                continue
            rest: list[str] = []
            for folgendes in woerter[stelle + 1 :]:
                if folgendes in TRENNER:
                    break
                rest.append(folgendes)
            while rest and rest[0].startswith("-"):
                rest = rest[2:] if rest[0] in GIT_OPTION_MIT_WERT else rest[1:]
            if rest:
                yield rest[0], tuple(rest[1:])


def _texte(knoten: object) -> Iterator[str]:
    if isinstance(knoten, dict):
        for schluessel, wert in knoten.items():
            yield str(schluessel)
            yield from _texte(wert)
    elif isinstance(knoten, list):
        for wert in knoten:
            yield from _texte(wert)
    else:
        yield str(knoten)


def _zahl(pfad: Path, name: str) -> float | None:
    """Der Wert einer Modulkonstante aus Zahlen und ``* + -``; sonst ``None``."""
    for knoten in ast.parse(pfad.read_text(encoding="utf-8")).body:
        if isinstance(knoten, ast.Assign) and [
            getattr(z, "id", None) for z in knoten.targets
        ] == [name]:
            return _rechne(knoten.value)
    return None


def _rechne(knoten: ast.expr) -> float | None:
    if isinstance(knoten, ast.Constant) and isinstance(knoten.value, int | float):
        return float(knoten.value)
    if isinstance(knoten, ast.BinOp) and type(knoten.op) in _RECHENARTEN:
        links, rechts = _rechne(knoten.left), _rechne(knoten.right)
        if links is None or rechts is None:
            return None
        return _RECHENARTEN[type(knoten.op)](links, rechts)
    return None
