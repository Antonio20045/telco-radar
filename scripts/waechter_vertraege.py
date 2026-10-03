"""Verträge der Stufe 0, die ohne Basis gelten: jeder Verstoß ist rot.

CLAUDE.md bleibt klein, die Git- und Claude-Hooks rufen nur die Leiter, jede
Fixture unter ``tests/fixtures/`` ist ein belegter Abruf, kein Test liest Quelltext
über ``inspect``, und die Workflows halten die Griffe, an denen Datenläufe still grün
enden würden, gegen Code und Konfiguration.
"""

from __future__ import annotations

import ast
import gzip
import hashlib
import json
import os
import re
from collections.abc import Callable, Iterator
from pathlib import Path

import waechter_claude
import waechter_speicher
import yaml

CLAUDE_MD = "CLAUDE.md"
HOOKS = ".githooks"
HOOK_INHALT = {
    "pre-commit": (
        "#!/bin/sh\n"
        "exec .venv/bin/python scripts/pruefleiter.py --schnell --nur-vorgemerkt\n"
    ),
    "pre-push": (
        '#!/bin/sh\nexec .venv/bin/python scripts/pruefleiter.py --vor-push "$@"\n'
    ),
}
CLAUDE_MD_ZEILEN = 100
CLAUDE_MD_BYTES = 10000
FIXTURES = "tests/fixtures"
BESTAND = "tests/fixtures/bestand"
HERKUNFT = "_herkunft.json"
BELEGFELDER = ("url", "quelle", "abgeleitet_aus")
QUELLTEXT_LESER = frozenset({"getsource", "getsourcelines", "findsource", "linecache"})
RADAR = ".github/workflows/radar.yml"
GERAETE = ".github/workflows/geraete.yml"
SETTINGS = "config/settings.yaml"
DEPLOY = "scripts/render_deploy.sh"
GERAETE_PIPELINE = "src/telco_radar/geraete_pipeline.py"
FRIST_NAME = "FRIST_TAGESLAUF"
ZUSTANDSDATEIEN = (
    "geraete_db.json",
    "geraete_preise.jsonl",
    "geraete_tco.json",
    "geraete_tco_historie.jsonl",
)
OHNE_FEHLERSCHLUCKEN = ("Commit state", "Render site", "Commit site")
MINDEST_TERMINE = 3
HEUTE_GEMESSEN = "Heute schon gemessen?"
HEUTE_BEDINGUNG = "steps.heute.outputs.fertig != 'true'"
BUENDELWAECHTER = "Buendelabdeckung pruefen"
_CRON_FRIST = re.compile(
    r"--frist\s+\"\$\{\{\s*github\.event\.inputs\.frist\s*\|\|\s*(\d+)\s*\}\}\""
)


def pruefe(wurzel: Path) -> list[str]:
    """Alle Verträge; jede Zeile ist ein Verstoß mit Ort und Regel."""
    return [
        *claude_md(wurzel),
        *fixture_herkunft(wurzel),
        *quelltext_in_tests(wurzel),
        *workflows(wurzel),
        *git_hooks(wurzel),
        *waechter_claude.vertrag(wurzel),
    ]


def git_hooks(wurzel: Path) -> list[str]:
    """Jeder Hook unter ``.githooks`` ist ausführbar und ruft nur die Leiter.

    Ein fehlender Hook ist hier kein Verstoß, ``make stand`` nennt ihn.
    """
    meldungen = []
    for name, inhalt in HOOK_INHALT.items():
        pfad = wurzel / HOOKS / name
        if not pfad.exists():
            continue
        if pfad.read_text(encoding="utf-8", errors="replace") != inhalt:
            meldungen.append(f"{HOOKS}/{name} weicht vom Hook der Leiter ab")
        if not os.access(pfad, os.X_OK):
            meldungen.append(f"{HOOKS}/{name} ist nicht ausführbar")
    for fremd in sorted((wurzel / HOOKS).glob("*")):
        if fremd.name not in HOOK_INHALT:
            meldungen.append(f"{HOOKS}/{fremd.name} ist kein Hook der Leiter")
    return meldungen


def claude_md(wurzel: Path) -> list[str]:
    pfad = wurzel / CLAUDE_MD
    if not pfad.exists():
        return [f"{CLAUDE_MD} fehlt"]
    roh = pfad.read_bytes()
    zeilen = len(roh.decode("utf-8", "replace").splitlines())
    meldungen = []
    if zeilen > CLAUDE_MD_ZEILEN:
        meldungen.append(f"{CLAUDE_MD} hat {zeilen} Zeilen, erlaubt {CLAUDE_MD_ZEILEN}")
    if len(roh) > CLAUDE_MD_BYTES:
        meldungen.append(f"{CLAUDE_MD} hat {len(roh)} Bytes, erlaubt {CLAUDE_MD_BYTES}")
    return meldungen


def fixture_herkunft(wurzel: Path) -> list[str]:
    """Jede Datei unter ``tests/fixtures/`` außerhalb der Schnappschüsse steht in
    der ``_herkunft.json`` ihres Ordners, mit Beleg und passendem sha256."""
    meldungen: list[str] = []
    ordner = wurzel / FIXTURES
    bestand = wurzel / BESTAND
    dateien = [
        d
        for d in sorted(ordner.rglob("*"))
        if d.is_file()
        and d.name != HERKUNFT
        and bestand not in d.parents
        and "__pycache__" not in d.parts
    ]
    gelesen: dict[Path, dict[str, dict] | str] = {}
    for datei in dateien:
        relativ = datei.relative_to(wurzel).as_posix()
        eintraege = gelesen.setdefault(datei.parent, _eintraege(datei.parent))
        if isinstance(eintraege, str):
            meldungen.append(f"{relativ}: {eintraege}")
            continue
        eintrag = eintraege.get(datei.name)
        if eintrag is None:
            meldungen.append(f"{relativ}: kein Eintrag in {HERKUNFT}")
            continue
        if not any(eintrag.get(feld) for feld in BELEGFELDER):
            meldungen.append(f"{relativ}: Eintrag ohne {' oder '.join(BELEGFELDER)}")
        if eintrag.get("sha256_roh") != _sha256_roh(datei):
            meldungen.append(f"{relativ}: sha256 weicht vom Eintrag in {HERKUNFT} ab")
    for pfad, eintraege in gelesen.items():
        if isinstance(eintraege, dict):
            meldungen += [
                f"{(pfad / name).relative_to(wurzel).as_posix()}: in {HERKUNFT}"
                " eingetragen, Datei fehlt"
                for name in sorted(eintraege)
                if not (pfad / name).is_file()
            ]
    return meldungen


def _eintraege(ordner: Path) -> dict[str, dict] | str:
    try:
        roh = json.loads((ordner / HERKUNFT).read_text(encoding="utf-8"))
        return {e["datei"]: e for e in roh["eintraege"]}
    except FileNotFoundError:
        return f"{HERKUNFT} fehlt im Ordner"
    except (OSError, KeyError, TypeError, ValueError):
        return f"{HERKUNFT} nicht lesbar"


def _sha256_roh(datei: Path) -> str:
    roh = datei.read_bytes()
    if datei.suffix == ".gz":
        roh = gzip.decompress(roh)
    return hashlib.sha256(roh).hexdigest()


def quelltext_in_tests(wurzel: Path) -> list[str]:
    """Kein Test liest Quelltext über ``inspect`` oder ``linecache``; das Lesen
    über Dateien sperrt der Audit-Hook in ``tests/conftest.py``."""
    meldungen = []
    for datei in sorted((wurzel / "tests").rglob("*.py")):
        if "__pycache__" in datei.parts:
            continue
        text = datei.read_text(encoding="utf-8", errors="replace")
        relativ = datei.relative_to(wurzel).as_posix()
        meldungen += [
            f"{relativ}:{fund}"
            for fund in waechter_speicher.hole(
                "quelltext", relativ, text, lambda t=text: _quelltext_funde(t)
            )
        ]
    return meldungen


def _quelltext_funde(text: str) -> list[str]:
    try:
        baum = ast.parse(text)
    except SyntaxError:
        return []
    return [
        f"{zeile}: liest Quelltext über {name}"
        for zeile, name in _quelltext_leser(baum)
    ]


def _quelltext_leser(baum: ast.AST) -> Iterator[tuple[int, str]]:
    for knoten in ast.walk(baum):
        if isinstance(knoten, ast.Attribute) and knoten.attr in QUELLTEXT_LESER:
            yield knoten.lineno, knoten.attr
        elif isinstance(knoten, ast.Name) and knoten.id in QUELLTEXT_LESER:
            yield knoten.lineno, knoten.id
        elif isinstance(knoten, ast.alias):
            name = knoten.name.split(".")[-1]
            if name in QUELLTEXT_LESER or knoten.name.split(".")[0] in QUELLTEXT_LESER:
                yield getattr(knoten, "lineno", 0), knoten.name


def workflows(wurzel: Path) -> list[str]:
    """Die Workflow-Griffe, an denen ein Datenlauf still grün enden würde."""
    meldungen: list[str] = []
    for regel in REGELN:
        try:
            meldungen += regel(wurzel)
        except (OSError, KeyError, TypeError, ValueError, yaml.YAMLError) as fehler:
            meldungen.append(f"{regel.__name__}: nicht prüfbar ({fehler!r})")
    return meldungen


def _yaml(wurzel: Path, pfad: str) -> dict:
    return yaml.safe_load((wurzel / pfad).read_text(encoding="utf-8"))


def _schritte(wurzel: Path) -> list[dict]:
    return _yaml(wurzel, GERAETE)["jobs"]["geraete"]["steps"]


def _schritt(wurzel: Path, name: str) -> dict:
    treffer = [s for s in _schritte(wurzel) if s.get("name") == name]
    if len(treffer) != 1:
        raise ValueError(f"Schritt {name!r} {len(treffer)}-mal in {GERAETE}")
    return treffer[0]


def _schluckt(schritt: dict) -> bool:
    return schritt.get("continue-on-error") not in (None, False)


def jobfrist_passt_zu_radar(wurzel: Path) -> list[str]:
    minuten = _yaml(wurzel, RADAR)["jobs"]["radar"]["timeout-minutes"]
    frist = _yaml(wurzel, SETTINGS)["job_frist_sekunden"]
    if frist == minuten * 60:
        return []
    return [f"{SETTINGS}: job_frist_sekunden {frist} ≠ {RADAR} timeout {minuten} min"]


def nachtlauf_committet_zustand(wurzel: Path) -> list[str]:
    text = (wurzel / GERAETE).read_text(encoding="utf-8")
    zeilen = [z for z in text.splitlines() if "git add data/state" in z]
    if not zeilen:
        return [f"{GERAETE}: kein 'git add data/state' mehr"]
    block = text[text.index(zeilen[0]) : text.index(zeilen[0]) + 300]
    return [
        f"{GERAETE}: 'git add data/state' nimmt {datei} nicht mit"
        for datei in ZUSTANDSDATEIEN
        if datei not in block
    ]


def seitenbau_schluckt_nichts(wurzel: Path) -> list[str]:
    return [
        f"{GERAETE}: Schritt {name!r} schluckt Fehler (continue-on-error)"
        for name in OHNE_FEHLERSCHLUCKEN
        if _schluckt(_schritt(wurzel, name))
    ]


def render_hook_prueft_live(wurzel: Path) -> list[str]:
    hook = _schritt(wurzel, "Trigger Render deploy")
    skript = (wurzel / DEPLOY).read_text(encoding="utf-8")
    pruefungen = [
        (not _schluckt(hook), "der Render-Hook schluckt Fehler"),
        (
            "steps.commit_site.outcome == 'success'" in hook.get("if", ""),
            "der Render-Hook läuft auch ohne gebaute Seite",
        ),
        (
            "render_deploy.sh geraete.html" in hook.get("run", ""),
            "der Render-Hook prüft geraete.html nicht live",
        ),
        ("for versuch in 1 2 3" in skript, f"{DEPLOY} versucht nicht dreimal"),
        ("date -u +%Y-%m-%d" in skript, f"{DEPLOY} sucht das Tagesdatum nicht"),
        (
            skript.rstrip().splitlines()[-1].endswith("exit 1"),
            f"{DEPLOY} endet nicht rot",
        ),
    ]
    return [f"{GERAETE}: {text}" for gilt, text in pruefungen if not gilt]


def commit_site_bricht_laut_ab(wurzel: Path) -> list[str]:
    rumpf = _schritt(wurzel, "Commit site")["run"]
    pruefungen = [
        ("reset --hard" in rumpf, "der Wiederholungsweg ist weg"),
        ("|| exit 0" not in rumpf, "der Neuaufbau verschluckt einen Renderfehler"),
        ("exit 1" in rumpf, "der Neuaufbau bricht nicht laut ab"),
        (
            "Seite konnte nicht gepusht werden" in rumpf,
            "das verlorene Push-Rennen meldet sich nicht",
        ),
        (
            rumpf.rstrip().splitlines()[-1].strip().startswith("echo "),
            "das verlorene Push-Rennen endet nicht grün",
        ),
    ]
    return [f"{GERAETE}: Commit site: {text}" for gilt, text in pruefungen if not gilt]


def frist_ist_eine(wurzel: Path) -> list[str]:
    """Cron-Rückfall und Vorgabe von ``workflow_dispatch`` sind ``FRIST_TAGESLAUF``."""
    text = (wurzel / GERAETE).read_text(encoding="utf-8")
    cron = _CRON_FRIST.search(text)
    vorgabe = _yaml(wurzel, GERAETE)[True]["workflow_dispatch"]["inputs"]["frist"]
    soll = _konstante(wurzel / GERAETE_PIPELINE, FRIST_NAME)
    werte = {
        "Cron-Rückfall": float(cron.group(1)) if cron else None,
        "workflow_dispatch-Vorgabe": float(vorgabe["default"]),
    }
    return [
        f"{GERAETE}: {art} {wert} ≠ {FRIST_NAME} {soll}"
        for art, wert in werte.items()
        if wert != soll
    ]


def _konstante(pfad: Path, name: str) -> float | None:
    for knoten in ast.parse(pfad.read_text(encoding="utf-8")).body:
        if (
            isinstance(knoten, ast.Assign)
            and [getattr(z, "id", None) for z in knoten.targets] == [name]
            and isinstance(knoten.value, ast.Constant)
        ):
            return float(knoten.value.value)
    return None


def buendelwaechter_zuletzt(wurzel: Path) -> list[str]:
    letzter = _schritte(wurzel)[-1]
    pruefungen = [
        (
            letzter.get("name") == BUENDELWAECHTER,
            f"letzter Schritt ist nicht {BUENDELWAECHTER!r}",
        ),
        (
            str(letzter.get("if", "")).startswith("always()"),
            "der Bündelwächter läuft nicht immer",
        ),
        (not _schluckt(letzter), "der Bündelwächter schluckt Fehler"),
        (
            "geraete_abdeckungswaechter.py" in letzter.get("run", ""),
            "der Bündelwächter ruft geraete_abdeckungswaechter.py nicht",
        ),
        (
            not any("SMTP" in k or "MAIL" in k for k in letzter.get("env") or {}),
            "der Bündelwächter bekommt Mail-Zugangsdaten",
        ),
    ]
    return [f"{GERAETE}: {text}" for gilt, text in pruefungen if not gilt]


def ein_crawl_je_tag(wurzel: Path) -> list[str]:
    termine = _yaml(wurzel, GERAETE)[True].get("schedule") or []
    meldungen = []
    if len(termine) < MINDEST_TERMINE:
        meldungen.append(
            f"{GERAETE}: {len(termine)} Termine, mindestens {MINDEST_TERMINE}"
        )
    schritte = _schritte(wurzel)
    namen = [s.get("name") for s in schritte]
    if HEUTE_GEMESSEN not in namen:
        return [*meldungen, f"{GERAETE}: Schritt {HEUTE_GEMESSEN!r} fehlt"]
    meldungen += [
        f"{GERAETE}: Schritt {s.get('name') or s.get('uses')!r} läuft auch, wenn heute"
        " schon gemessen ist"
        for s in schritte[namen.index(HEUTE_GEMESSEN) + 1 :]
        if HEUTE_BEDINGUNG not in str(s.get("if", ""))
    ]
    return meldungen


REGELN: tuple[Callable[[Path], list[str]], ...] = (
    jobfrist_passt_zu_radar,
    nachtlauf_committet_zustand,
    seitenbau_schluckt_nichts,
    render_hook_prueft_live,
    commit_site_bricht_laut_ab,
    frist_ist_eine,
    buendelwaechter_zuletzt,
    ein_crawl_je_tag,
)
