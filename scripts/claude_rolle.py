"""Rollen der Auftragsagenten: wohin eine Rolle schreiben darf, für Hook und Skript.

``tools/auftrag.py`` startet jeden Agenten mit ``TELCO_ROLLE`` und ``claude --settings``
aus ``einstellungen``; diese Datei ist dann sein PreToolUse-Hook für Bash und jedes
Schreibwerkzeug und endet mit Exit 2 und Begründung, wenn die Rolle dort nicht schreiben
darf. Dieselbe Regel ``verstoss`` hält das Skript nach jeder Runde gegen den Git-Stand.
Außerhalb des Repos schreibt eine Rolle nur in den Temp-Ordner, nie neben das Repo.
Ohne Rolle lässt der Hook alles durch, was die deny-Liste erlaubt.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
import sys
import tempfile
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path

BLOCKIERT = 2
ROLLEN = ("test", "bau", "pruefer", "entwurf", "suchen")
TESTS = "tests/"
BEREICH_WURZEL = "src/telco_radar/"
ENTWURF = "outputs/auftraege/"
NIE_NEU = frozenset(
    {
        "conftest.py",
        "__init__.py",
        "pytest.ini",
        "tox.ini",
        "setup.cfg",
        "pyproject.toml",
    }
)
VORSATZ = frozenset(
    {"env", "command", "exec", "nice", "nohup", "timeout", "time", "xargs", "sudo"}
)
REGEL = {
    "test": "nur neue Dateien unter tests/ und die Abnahme",
    "bau": "nur der Bereich des Auftrags und neue Dateien unter tests/",
    "pruefer": "nur der eigene Ordner aus TELCO_PRUEFER_ORDNER",
    "entwurf": f"nur {ENTWURF}",
    "suchen": "nichts",
}
SCHREIBWERKZEUGE = frozenset({"Edit", "Write", "MultiEdit", "NotebookEdit"})
GIT_LESEN = frozenset(
    {"status", "diff", "log", "show", "ls-files", "rev-parse", "blame", "grep"}
)
GIT_OPTIONEN_MIT_WERT = frozenset({"-c", "-C", "--git-dir", "--work-tree"})
ALLE_ZIELE = frozenset(
    {"rm", "mv", "tee", "truncate", "touch", "chmod", "chown", "mkdir", "unlink"}
    | {"rmdir", "shred", "patch"}
    | {"ed", "ex", "vi", "vim", "nvim", "emacs", "nano"}
)
LETZTES_ZIEL = frozenset({"cp", "ln", "install", "rsync"})
ZIEL_OPTIONEN = {
    "cp": ("-t", "--target-directory"),
    "mv": ("-t", "--target-directory"),
    "ln": ("-t", "--target-directory"),
    "install": ("-t", "--target-directory"),
    "git": ("--output",),
    "curl": ("-o", "--output", "--output-dir"),
    "wget": ("-O", "--output-document", "-P", "--directory-prefix"),
    "tar": ("-C", "--directory"),
    "unzip": ("-d",),
}
HIER_AUSPACKEN = frozenset({"tar", "unzip", "wget", "curl"})
LOESCHT = frozenset({"-delete", "-exec", "-execdir", "-fprint", "-fprintf", "-fls"})
IM_ORT = frozenset({"sed", "perl", "ruby"})
UNBERECHENBAR = frozenset({"eval", "source", ".", "exec"})
UMLEITUNG = frozenset({">", ">>", ">|", "&>", "&>>"})
KEIN_ZIEL = frozenset({"/dev/null", "/dev/stdout", "/dev/stderr"})
TRENNZEICHEN = frozenset(";&|()\n")
INTERPRETER = re.compile(r"^(python3?(\.\d+)?|perl|ruby|node|sh|bash|zsh)$")
AWK = frozenset({"awk", "gawk", "mawk"})
SCHREIB_API = re.compile(
    r"write|open\(|unlink|rename|replace|rmtree|remove|shutil|truncate|chmod|symlink"
    r"|subprocess|system|exec|popen|spawn|fork|__import__|importlib|pathlib|Path\b"
    r"|eval|compile|getattr|ctypes|pty|os\.",
    re.IGNORECASE,
)
GIT_SPERREN = tuple(
    f"Bash(git {befehl}*)"
    for befehl in (
        "add",
        "apply",
        "checkout",
        "clean",
        "commit",
        "merge",
        "mv",
        "push",
        "rebase",
        "reset",
        "restore",
        "rm",
        "stash",
        "switch",
    )
)


@dataclass(frozen=True)
class Ziel:
    """Was eine Rolle in einem Auftrag schreiben darf."""

    rolle: str
    bereich: str | None = None
    abnahme: str | None = None
    pruefer: Path | None = None


def ziel_aus_umgebung(umgebung: Mapping[str, str]) -> Ziel | None:
    """Liest Rolle, Bereich, Abnahme und Prüferordner; ohne Rolle ``None``."""
    rolle = umgebung.get("TELCO_ROLLE")
    if not rolle:
        return None
    auftrag: dict = {}
    if datei := umgebung.get("TELCO_AUFTRAG"):
        try:
            auftrag = json.loads(Path(datei).read_text("utf-8"))
        except (OSError, ValueError):
            auftrag = {}
    ordner = umgebung.get("TELCO_PRUEFER_ORDNER")
    return Ziel(
        rolle,
        auftrag.get("bereich") if isinstance(auftrag, dict) else None,
        auftrag.get("abnahme") if isinstance(auftrag, dict) else None,
        Path(ordner) if ordner else None,
    )


def verstoss(ziel: Ziel, wurzel: Path, pfad: Path, neu: bool) -> str | None:
    """Gibt den Grund, warum die Rolle ``pfad`` nicht schreiben darf, sonst ``None``.

    ``neu`` heißt: Die Datei gab es im letzten Commit nicht.
    """
    absolut = Path(os.path.realpath(pfad if pfad.is_absolute() else wurzel / pfad))
    if ziel.rolle not in ROLLEN:
        return f"Rolle {ziel.rolle} ist unbekannt; erlaubt sind {', '.join(ROLLEN)}"
    regel = f"Rolle {ziel.rolle} darf {absolut} nicht ändern ({REGEL[ziel.rolle]})"
    if ziel.rolle == "pruefer":
        ordner = Path(os.path.realpath(ziel.pruefer)) if ziel.pruefer else None
        return None if ordner and absolut.is_relative_to(ordner) else regel
    try:
        relativ = absolut.relative_to(os.path.realpath(wurzel)).as_posix()
    except ValueError:
        neben = absolut.is_relative_to(os.path.realpath(wurzel.parent))
        frei = absolut.is_relative_to(os.path.realpath(tempfile.gettempdir()))
        return None if frei and not neben and ziel.rolle != "suchen" else regel
    neuer_test = neu and relativ.startswith(TESTS) and absolut.name not in NIE_NEU
    bereich = ziel.bereich or ""
    im_bereich = bereich.startswith(BEREICH_WURZEL) and bereich.endswith("/")
    erlaubt = {
        "test": neuer_test or relativ == ziel.abnahme,
        "bau": neuer_test or (im_bereich and relativ.startswith(bereich)),
        "entwurf": relativ.startswith(ENTWURF),
        "suchen": False,
    }[ziel.rolle]
    return None if erlaubt else regel.replace(str(absolut), relativ)


def ist_neu(wurzel: Path, pfad: Path) -> bool:
    """Wahr, wenn ``pfad`` im letzten Commit von ``wurzel`` fehlt."""
    try:
        relativ = Path(os.path.realpath(wurzel / pfad)).relative_to(
            os.path.realpath(wurzel)
        )
    except ValueError:
        return True
    lauf = subprocess.run(
        ["git", "cat-file", "-e", f"HEAD:{relativ.as_posix()}"],
        cwd=wurzel,
        capture_output=True,
        check=False,
    )
    return lauf.returncode != 0


def _befehle(text: str, tiefe: int = 3) -> list[list[str]]:
    zerleger = shlex.shlex(text, posix=True, punctuation_chars=True)
    zerleger.whitespace_split = True
    try:
        woerter = list(zerleger)
    except ValueError:
        woerter = text.split()
    befehle: list[list[str]] = [[]]
    for wort in woerter:
        if wort and set(wort) <= TRENNZEICHEN:
            befehle.append([])
        else:
            befehle[-1].append(wort)
    innen = [w for b in befehle for w in b if tiefe and any(z.isspace() for z in w)]
    for wort in innen:
        befehle += _befehle(wort, tiefe - 1)
    return [b for b in befehle if b]


def _git_unterbefehl(argumente: list[str]) -> str | None:
    stelle = 0
    while stelle < len(argumente) and argumente[stelle].startswith("-"):
        stelle += 2 if argumente[stelle] in GIT_OPTIONEN_MIT_WERT else 1
    return argumente[stelle] if stelle < len(argumente) else None


def _im_ort(option: str) -> bool:
    kurz = option.startswith("-") and not option.startswith("--") and "i" in option
    return kurz or option.startswith("--in-place")


def _ohne_vorsatz(befehl: list[str]) -> list[str]:
    while befehl and (Path(befehl[0]).name in VORSATZ or "=" in befehl[0]):
        befehl = befehl[1:]
        while befehl and (befehl[0].startswith("-") or befehl[0].isdigit()):
            befehl = befehl[1:]
    return befehl


def _schreibziele(befehl: list[str]) -> list[str]:
    name, argumente = Path(befehl[0]).name, befehl[1:]
    ziele = [
        folgend
        for wort, folgend in zip(befehl, befehl[1:], strict=False)
        if wort in UMLEITUNG
        and folgend not in KEIN_ZIEL
        and not folgend.startswith("&")
    ]
    pfade = [a for a in argumente if not a.startswith("-") and a not in UMLEITUNG]
    pfade = [a for a in pfade if a not in ziele]
    if name in ALLE_ZIELE:
        ziele += pfade
    elif name in LETZTES_ZIEL and pfade:
        ziele.append(pfade[-1])
    elif name in IM_ORT and any(map(_im_ort, argumente)):
        ziele += pfade[1:] if name == "sed" else pfade
    elif name == "dd":
        ziele += [a[3:] for a in argumente if a.startswith("of=")]
    elif name == "find" and LOESCHT & set(argumente):
        ziele += pfade
    optionen = _optionswerte(argumente, ZIEL_OPTIONEN.get(name, ()))
    ziele += optionen
    if name in HIER_AUSPACKEN and not optionen and _packt_hier_aus(name, argumente):
        ziele.append(".")
    return ziele


def _optionswerte(argumente: list[str], optionen: tuple[str, ...]) -> list[str]:
    werte = []
    for stelle, wort in enumerate(argumente):
        for option in optionen:
            kurz = len(option) == 2 and not wort.startswith("--")
            gebuendelt = kurz and wort.startswith("-") and wort.endswith(option[1])
            if (wort == option or gebuendelt) and stelle + 1 < len(argumente):
                werte.append(argumente[stelle + 1])
            elif option.startswith("--") and wort.startswith(option + "="):
                werte.append(wort[len(option) + 1 :])
            elif len(option) == 2 and wort.startswith(option) and len(wort) > 2:
                werte.append(wort[2:])
    return werte


def _packt_hier_aus(name: str, argumente: list[str]) -> bool:
    if name == "tar":
        modus = next((a for a in argumente if not a.startswith("--")), "")
        return "x" in modus or bool({"--extract", "--get"} & set(argumente))
    if name == "curl":
        return any(
            a in {"-O", "--remote-name", "--remote-name-all"}
            or (a.startswith("-") and not a.startswith("--") and "O" in a)
            for a in argumente
        )
    if name == "unzip":
        return not {"-l", "-t", "-v", "-Z", "-p", "-z"} & set(argumente)
    return True


def befehl_verstoss(
    ziel: Ziel,
    wurzel: Path,
    ort: Path,
    text: str,
    neu: Callable[[Path, Path], bool] = ist_neu,
) -> str | None:
    """PreToolUse Bash einer Rolle: kein schreibendes Git, kein Schreiben außerhalb
    der Rolle über Umleitung, Dateibefehl oder eingebetteten Interpretercode."""
    if "`" in text or "$(" in text or "<(" in text or ">(" in text:
        return f"Rolle {ziel.rolle}: Befehlsersetzung ist gesperrt; schreib sie aus"
    for befehl in filter(None, map(_ohne_vorsatz, _befehle(text))):
        name = Path(befehl[0]).name
        if name in UNBERECHENBAR or any(z in befehl[0] for z in "$`"):
            return (
                f"Rolle {ziel.rolle}: ein Befehl aus Variable, Ersetzung oder eval"
                " ist gesperrt; schreib ihn aus"
            )
        if name == "git":
            unter = _git_unterbefehl(befehl[1:])
            if unter not in GIT_LESEN:
                return f"Rolle {ziel.rolle}: git {unter} führt nur tools/auftrag.py aus"
        if name in AWK and any(">" in w or "system" in w for w in befehl[1:]):
            return f"Rolle {ziel.rolle}: awk mit Umleitung oder system ist gesperrt"
        eingebettet = {"-c", "-", "-e", "<<", "<<<"} & set(befehl[1:])
        if INTERPRETER.match(name) and eingebettet and SCHREIB_API.search(text):
            return (
                f"Rolle {ziel.rolle}: eingebetteter Code, der Dateien schreibt, ist"
                " gesperrt; schreib mit Edit oder Write"
            )
        for pfad in _schreibziele(befehl):
            ziel_pfad = Path(pfad) if Path(pfad).is_absolute() else ort / pfad
            if grund := verstoss(ziel, wurzel, ziel_pfad, neu(wurzel, ziel_pfad)):
                return grund
    return None


def einstellungen(rolle: str) -> dict:
    """Die Einstellungen für ``claude --settings`` einer Rolle."""
    hook = 'python3 "$CLAUDE_PROJECT_DIR"/scripts/claude_rolle.py'
    werkzeuge = "Bash|" + "|".join(sorted(SCHREIBWERKZEUGE))
    eintrag = {"type": "command", "command": hook, "timeout": 10}
    return {
        "env": {"TELCO_ROLLE": rolle},
        "permissions": {"deny": list(GIT_SPERREN)},
        "hooks": {"PreToolUse": [{"matcher": werkzeuge, "hooks": [eintrag]}]},
    }


def _wurzel(ort: Path) -> Path:
    lauf = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        cwd=ort,
        capture_output=True,
        text=True,
        check=False,
    )
    return Path(lauf.stdout.strip()) if lauf.returncode == 0 else ort


def pruefe(ereignis: dict, umgebung: Mapping[str, str]) -> str | None:
    """Urteil über ein PreToolUse-Ereignis; ``None`` lässt das Werkzeug laufen."""
    ziel = ziel_aus_umgebung(umgebung)
    if ziel is None:
        return None
    ort = Path(str(ereignis.get("cwd") or Path.cwd()))
    wurzel = _wurzel(ort)
    werkzeug, eingabe = ereignis.get("tool_name"), ereignis.get("tool_input") or {}
    if werkzeug == "Bash":
        return befehl_verstoss(ziel, wurzel, ort, str(eingabe.get("command", "")))
    if werkzeug in SCHREIBWERKZEUGE:
        roh = eingabe.get("file_path") or eingabe.get("notebook_path") or ""
        pfad = Path(str(roh)) if Path(str(roh)).is_absolute() else ort / str(roh)
        return verstoss(ziel, wurzel, pfad, ist_neu(wurzel, pfad))
    return None


def main(
    lesen: Callable[[], str] = sys.stdin.read,
    umgebung: Mapping[str, str] = os.environ,
) -> int:
    """Liest das Ereignis von stdin; Exit 2 mit Begründung auf stderr blockiert."""
    try:
        ereignis = json.loads(lesen() or "{}")
        ereignis = ereignis if isinstance(ereignis, dict) else {}
        grund = pruefe(ereignis, umgebung)
    except (ValueError, OSError, TypeError, AttributeError) as fehler:
        name = type(fehler).__name__
        print(
            f"Rollen-Hook gescheitert, also gesperrt: {name}: {fehler}", file=sys.stderr
        )
        return BLOCKIERT
    if grund:
        print(grund, file=sys.stderr)
        return BLOCKIERT
    return 0


if __name__ == "__main__":
    sys.exit(main())
