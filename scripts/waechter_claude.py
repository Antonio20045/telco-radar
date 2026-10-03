"""Stufe-0-Verträge für die Claude-Einstellungen und die Ordner-CLAUDE.md.

``.claude/settings.json`` muss jeden Hook aus ``PFLICHT_HOOKS`` und jede Sperre aus
``PFLICHT_SPERREN`` tragen, sobald sie die Hooks der Leiter überhaupt nennt; fehlen sie
ganz, meldet ``make stand`` Schritt 5 als offen. Jede CLAUDE.md unter ``src/`` bleibt
klein, und die Ordner aus ``ORDNER_CLAUDE_MD`` haben eine.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

EINSTELLUNGEN = ".claude/settings.json"
HOOK_SKRIPT = "scripts/claude_hooks.py"
PROJEKT = '"$CLAUDE_PROJECT_DIR"'
SHELL_ZUSATZ = re.compile(r"[;&|`$<>()]|\bexit\b|\btrue\b")
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


def vertrag(wurzel: Path) -> list[str]:
    """Stufe 0: Ordner-CLAUDE.md und, sobald eingerichtet, die vollen Einstellungen."""
    pfad = wurzel / EINSTELLUNGEN
    text = pfad.read_text("utf-8") if pfad.is_file() else ""
    eingerichtet = HOOK_SKRIPT in text
    return ordner_claude_md(wurzel) + (einstellungen(wurzel) if eingerichtet else [])


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
    rechte = daten.get("permissions", {}) if isinstance(daten, dict) else {}
    sperren = set(rechte.get("deny", []))
    meldungen += [
        f"{EINSTELLUNGEN}: Sperre {s} fehlt"
        for s in PFLICHT_SPERREN
        if s not in sperren
    ]
    return meldungen


def _hat_hook(gruppen: list, matcher: str, befehl: str) -> bool:
    for gruppe in gruppen if isinstance(gruppen, list) else []:
        if not isinstance(gruppe, dict) or gruppe.get("matcher", "") != matcher:
            continue
        for hook in gruppe.get("hooks", []):
            if isinstance(hook, dict) and _ruft_nur(
                str(hook.get("command", "")), befehl
            ):
                return True
    return False


def _ruft_nur(kommando: str, befehl: str) -> bool:
    """Der Hook ruft genau ``befehl``, ohne Shell-Zusatz, der den Exit-Code schluckt."""
    rest = kommando.replace(PROJEKT, "").strip()
    return rest.endswith(befehl) and not SHELL_ZUSATZ.search(rest)


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
