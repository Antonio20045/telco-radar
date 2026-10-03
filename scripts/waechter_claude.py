"""Stufe-0-Verträge für die Claude-Einstellungen und die Ordner-CLAUDE.md.

``.claude/settings.json`` muss jeden Hook aus ``PFLICHT_HOOKS`` und jede Sperre aus
``PFLICHT_SPERREN`` tragen, sobald sie ``scripts/claude_hooks.py`` nennt oder je in
der Git-Historie genannt hat; vorher meldet nur
``make stand`` Schritt 5 als offen. Jede CLAUDE.md unter ``src/`` bleibt
klein, und die Ordner aus ``ORDNER_CLAUDE_MD`` haben eine.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

EINSTELLUNGEN = ".claude/settings.json"
HOOK_SKRIPT = "scripts/claude_hooks.py"
PROJEKT = '"$CLAUDE_PROJECT_DIR"'
LOKAL = ".claude/settings.local.json"
ALLE_AUS = "disableAllHooks"
HOOK_FELDER = frozenset({"type", "command", "timeout"})
# Erlaubte Aufrufer eines Hooks; danach folgt genau Skriptpfad und Unterbefehl.
AUFRUFER = ("python3", f"{PROJEKT}/.venv/bin/python")
PFLICHT_HOOKS = (
    ("SessionStart", "", f"{HOOK_SKRIPT} sitzung"),
    ("PreToolUse", "Bash", f"{HOOK_SKRIPT} befehl"),
    ("PreToolUse", "Read", f"{HOOK_SKRIPT} datei_lesen"),
    ("PostToolUse", "Edit|Write", f"{HOOK_SKRIPT} nach_edit"),
    ("Stop", "", f"{HOOK_SKRIPT} stop"),
)
PFLICHT_SPERREN = (
    "Edit(site/**)",
    "Edit(data/**)",
    "Edit(pruef/**)",
    "Edit(.githooks/**)",
    "Edit(.claude/settings.json)",
    "Edit(.importlinter)",
    "Edit(pyproject.toml)",
    "Edit(tests/fixtures/bestand/**)",
    "Bash(git add -A*)",
    "Bash(git add .*)",
    "Bash(git push --force*)",
    "Bash(git push -f*)",
    "Bash(*--no-verify*)",
    "Bash(git commit -n*)",
    "Bash(git config core.hooksPath*)",
    "Bash(git checkout -- *)",
    "Bash(git reset --hard*)",
    "Bash(rm -rf*)",
)
ORDNER_CLAUDE_MD = (
    "src/telco_radar/collect/geraete",
    "src/telco_radar/analyze",
    "src/telco_radar/report",
)
ORDNER_ZEILEN = 40
STOP_RESERVE_SEKUNDEN = 60


def vertrag(wurzel: Path) -> list[str]:
    """Stufe 0: Ordner-CLAUDE.md und, sobald eingerichtet, die vollen Einstellungen."""
    if not eingerichtet(wurzel):
        return ordner_claude_md(wurzel)
    skript = [] if (wurzel / HOOK_SKRIPT).is_file() else [f"{HOOK_SKRIPT} fehlt"]
    return ordner_claude_md(wurzel) + skript + einstellungen(wurzel) + lokal(wurzel)


def eingerichtet(wurzel: Path) -> bool:
    """Wahr, wenn die Einstellungen die Hooks nennen oder einmal genannt haben.

    Ein Commit, der die Hooks, die Einstellungen oder das Skript wieder entfernt, hebt
    den Vertrag nicht auf; ohne lesbare Historie (kein Repo) zählt nur der Arbeitsstand.
    """
    pfad = wurzel / EINSTELLUNGEN
    if pfad.is_file() and HOOK_SKRIPT in pfad.read_text("utf-8", "replace"):
        return True
    suche = ["git", "log", "-1", "--format=%H", "-S", HOOK_SKRIPT, "--", EINSTELLUNGEN]
    umgebung = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    try:
        lauf = subprocess.run(
            suche, cwd=wurzel, env=umgebung, capture_output=True, text=True, check=False
        )
    except OSError:
        return False
    return lauf.returncode == 0 and bool(lauf.stdout.strip())


def einstellungen(wurzel: Path) -> list[str]:
    """Nennt jeden fehlenden Pflicht-Hook und jede fehlende Sperre."""
    try:
        daten = json.loads((wurzel / EINSTELLUNGEN).read_text("utf-8"))
    except (OSError, ValueError) as fehler:
        return [f"{EINSTELLUNGEN} nicht lesbar ({type(fehler).__name__})"]
    hooks = daten.get("hooks", {}) if isinstance(daten, dict) else {}
    meldungen = [
        f"{EINSTELLUNGEN}: Hook {ereignis} {matcher or '*'} ruft nicht {befehl}"
        for ereignis, matcher, befehl in PFLICHT_HOOKS
        if not _hat_hook(hooks.get(ereignis, []), matcher, befehl)
    ]
    meldungen += fremde_hooks(hooks if isinstance(hooks, dict) else {})
    meldungen += stop_frist(hooks.get("Stop", []))
    if isinstance(daten, dict) and daten.get(ALLE_AUS) is not None:
        meldungen.append(f"{EINSTELLUNGEN}: {ALLE_AUS} ist verboten")
    rechte = daten.get("permissions", {}) if isinstance(daten, dict) else {}
    sperren = set(rechte.get("deny", []))
    meldungen += [
        f"{EINSTELLUNGEN}: Sperre {s} fehlt"
        for s in PFLICHT_SPERREN
        if s not in sperren
    ]
    return meldungen


def stop_frist(gruppen: list) -> list[str]:
    """Der Stop-Hook hat Zeit für die gekappte Stufe 4, ihren Nachlauf und eine Reserve;
    sonst bricht Claude Code ihn ab, und ein roter geänderter Test bleibt unbemerkt."""
    from geaenderte_tests import NACHLAUF_SEKUNDEN
    from leiter_schnell import KAPPE_SEKUNDEN

    noetig = KAPPE_SEKUNDEN + NACHLAUF_SEKUNDEN + STOP_RESERVE_SEKUNDEN
    fristen = [
        hook.get("timeout")
        for gruppe in (gruppen if isinstance(gruppen, list) else [])
        if isinstance(gruppe, dict)
        for hook in gruppe.get("hooks", [])
        if isinstance(hook, dict) and HOOK_SKRIPT in str(hook.get("command", ""))
    ]
    return [
        f"{EINSTELLUNGEN}: Stop-Hook hat {frist} s, braucht mindestens {noetig} s"
        for frist in fristen
        if not isinstance(frist, int) or frist < noetig
    ]


def fremde_hooks(hooks: dict) -> list[str]:
    """Jeder Hook ruft einen Unterbefehl des Hook-Skripts, nur mit ``HOOK_FELDER``;
    ein fremder Hook daneben (etwa ``{"continue": false}``) könnte die Leiter
    entschärfen."""
    erlaubt = {befehl for _, _, befehl in PFLICHT_HOOKS}
    meldungen = []
    for ereignis, gruppen in sorted(hooks.items()):
        for gruppe in gruppen if isinstance(gruppen, list) else [gruppen]:
            liste = gruppe.get("hooks", []) if isinstance(gruppe, dict) else [gruppe]
            for hook in liste if isinstance(liste, list) else [liste]:
                kommando = (
                    str(hook.get("command", "")) if isinstance(hook, dict) else ""
                )
                if not (
                    isinstance(hook, dict)
                    and set(hook) <= HOOK_FELDER
                    and any(_ruft_nur(kommando, befehl) for befehl in erlaubt)
                ):
                    meldungen.append(f"{EINSTELLUNGEN}: fremder Hook unter {ereignis}")
    return meldungen


def lokal(wurzel: Path) -> list[str]:
    """``.claude/settings.local.json`` darf keine Hooks setzen oder abschalten."""
    pfad = wurzel / LOKAL
    try:
        daten = json.loads(pfad.read_text("utf-8")) if pfad.is_file() else {}
    except (OSError, ValueError) as fehler:
        return [f"{LOKAL} nicht lesbar ({type(fehler).__name__})"]
    verboten = sorted(
        {"hooks", ALLE_AUS} & set(daten if isinstance(daten, dict) else {})
    )
    return [f"{LOKAL}: {schluessel} ist verboten" for schluessel in verboten]


def _hat_hook(gruppen: list, matcher: str, befehl: str) -> bool:
    """Eine Gruppe mit ``matcher`` trägt genau einen Hook, nur mit ``HOOK_FELDER``,
    der ``befehl`` ruft; ein zweiter Hook daneben oder ``async`` könnte ihn
    entschärfen."""
    for gruppe in gruppen if isinstance(gruppen, list) else []:
        if not isinstance(gruppe, dict) or gruppe.get("matcher", "") != matcher:
            continue
        hooks = gruppe.get("hooks", [])
        if not isinstance(hooks, list) or len(hooks) != 1:
            continue
        hook = hooks[0]
        if (
            isinstance(hook, dict)
            and set(hook) <= HOOK_FELDER
            and _ruft_nur(str(hook.get("command", "")), befehl)
        ):
            return True
    return False


def _ruft_nur(kommando: str, befehl: str) -> bool:
    """Der Hook ist genau ein Aufrufer aus ``AUFRUFER`` mit ``befehl``; ein anderer
    Anfang (``echo``, ``:``) oder Zusatz (``|| true``) schluckte den Exit-Code."""
    return kommando.strip() in {f"{a} {PROJEKT}/{befehl}" for a in AUFRUFER}


def ordner_claude_md(wurzel: Path) -> list[str]:
    """Die Ordner aus ``ORDNER_CLAUDE_MD`` haben eine CLAUDE.md, jede ist klein."""
    meldungen = [
        f"{ordner}/CLAUDE.md fehlt"
        for ordner in ORDNER_CLAUDE_MD
        if not (wurzel / ordner / "CLAUDE.md").is_file()
    ]
    for datei in sorted((wurzel / "src").rglob("CLAUDE.md")):
        zeilen = len(datei.read_text("utf-8", "replace").splitlines())
        if zeilen > ORDNER_ZEILEN:
            relativ = datei.relative_to(wurzel)
            meldungen.append(f"{relativ} hat {zeilen} Zeilen, erlaubt {ORDNER_ZEILEN}")
    return meldungen
