"""Shelltext einer Rolle zerlegen: einfache Befehle, Vorsätze, Git- und Python-Sperren
und die Pfade, in die ein Befehl schreibt. Die Regel selbst steht in ``claude_rolle``.
"""

from __future__ import annotations

import os
import re
import shlex
from collections.abc import Callable
from pathlib import Path

VORSATZ = frozenset({"env", "command", "nice", "nohup", "timeout", "time", "xargs"})
ERLAUBT = frozenset(
    {"cat", "head", "tail", "grep", "egrep", "rg", "find", "ls", "wc", "sort", "uniq"}
    | {"diff", "cmp", "comm", "cut", "tr", "nl", "tac", "column", "paste", "jq"}
    | {"echo", "printf", "sed", "awk", "gawk", "mawk", "true", "false", "test", "["}
    | {"basename", "dirname", "realpath", "readlink", "stat", "file", "du", "pwd"}
    | {"cd", "which", "date", "md5sum", "sha256sum", "od", "xxd"}
    | {"git", "python", "python3", "pytest", "ruff", "mypy", "sh", "bash", "zsh"}
    | {"cp", "mv", "ln", "install", "mkdir", "touch", "rm", "rmdir", "tee"}
    | {"truncate", "dd", "tar", "unzip", "curl", "wget"}
)
VARIABLEN = frozenset({"PYTHONPATH", "LANG", "LC_ALL", "TZ", "NO_COLOR", "COLUMNS"})
PYTHON_MODULE = frozenset({"pytest", "ruff", "mypy"})
PYTHON_SKRIPTE = ("scripts/", "tools/")
GIT_OHNE_WERT = frozenset({"--no-pager", "-P", "--no-optional-locks"})
GIT_PAGER = ("-O", "--open-files-in-pager")
STARTER = frozenset({"sh", "bash", "zsh", "env"})
FIND_STARTET = frozenset({"-exec", "-execdir", "-ok", "-okdir"})
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
UMLEITUNG = frozenset({">", ">>", ">|", "&>", "&>>"})
KEIN_ZIEL = frozenset({"/dev/null", "/dev/stdout", "/dev/stderr"})
TRENNZEICHEN = frozenset(";&|()\n")
PYTHON = re.compile(r"^python3?(\.\d+)?$")
SHELLS = frozenset({"sh", "bash", "zsh"})
AWK = frozenset({"awk", "gawk", "mawk"})
SCHREIB_API = re.compile(
    r"write|open\(|unlink|rename|replace|rmtree|remove|shutil|truncate|chmod|symlink"
    r"|subprocess|system|exec|popen|spawn|fork|__import__|importlib|pathlib|Path\b"
    r"|eval|compile|getattr|ctypes|pty|os\."
    r"|__\w+__|globals|vars\s*\(|locals|['\"]\s*\+|\+\s*['\"]|chr\s*\("
    r"|\\x|\\u|bytes|decode|codecs|base64|\.join\s*\(|format",
    re.IGNORECASE,
)


def einfache_befehle(
    text: str, tiefe: int = 3, streng: bool = True
) -> list[tuple[list[str], bool]]:
    """Die einfachen Befehle eines Shelltexts; ``streng``: die Shell führt sie aus.
    Wörter mit Leerraum werden selbst zerlegt; ausgeführt werden sie nur hinter einer
    Shell oder ``env -S``, sonst sind sie Text (``echo 'X = 2'``)."""
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
    ergebnis = [(b, streng) for b in befehle if b]
    for befehl in befehle:
        startet = streng and any(Path(w).name in STARTER for w in befehl)
        for wort in befehl:
            if tiefe and any(z.isspace() for z in wort):
                ergebnis += einfache_befehle(wort, tiefe - 1, startet)
    return ergebnis


def im_ort(option: str) -> bool:
    kurz = option.startswith("-") and not option.startswith("--") and "i" in option
    return kurz or option.startswith("--in-place")


def ohne_vorsatz(befehl: list[str]) -> tuple[list[str], list[str]]:
    """Der Befehl ohne Vorsätze und die Namen der davor gesetzten Variablen."""
    variablen = []
    while befehl and (Path(befehl[0]).name in VORSATZ or "=" in befehl[0]):
        if "=" in befehl[0]:
            variablen.append(befehl[0].split("=", 1)[0])
        befehl = befehl[1:]
        while befehl and (befehl[0].startswith("-") or befehl[0].isdigit()):
            befehl = befehl[1:]
    return befehl, variablen


def git_sperre(argumente: list[str]) -> str | None:
    """Was an einem git-Aufruf gesperrt ist: Schreiben, Optionen vor dem Unterbefehl,
    die ein Programm starten können (``-c``, ``--exec-path`` …), und ``grep -O``."""
    stelle = 0
    while stelle < len(argumente) and argumente[stelle].startswith("-"):
        option = argumente[stelle]
        if option in GIT_OPTIONEN_MIT_WERT - {"-c"}:
            stelle += 2
        elif option in GIT_OHNE_WERT:
            stelle += 1
        else:
            return f"git {option}"
    unter = argumente[stelle] if stelle < len(argumente) else None
    if unter not in GIT_LESEN:
        return f"git {unter}"
    rest = argumente[stelle + 1 :]
    if unter == "grep" and any(a.startswith(GIT_PAGER) for a in rest):
        return "git grep -O"
    return None


def python_sperre(
    wurzel: Path,
    ort: Path,
    argumente: list[str],
    text: str,
    neu: Callable[[Path, Path], bool],
) -> bool:
    """Python nur als ``-m pytest|ruff|mypy``, als bestehendes Skript unter
    ``scripts/`` oder ``tools/`` oder mit eingebettetem Code ohne Schreib-API."""
    stelle = 0
    while stelle < len(argumente) and argumente[stelle] in {"-u", "-B", "-X", "-W"}:
        stelle += 2 if argumente[stelle] in {"-X", "-W"} else 1
    erstes = argumente[stelle] if stelle < len(argumente) else None
    if erstes == "-m":
        return argumente[stelle + 1 : stelle + 2] not in ([m] for m in PYTHON_MODULE)
    if erstes == "-c" or (erstes == "-" and "<<" in argumente):
        return bool(SCHREIB_API.search(text))
    if erstes is None or erstes.startswith("-") or "<" in argumente:
        return True
    skript = Path(os.path.realpath(ort / erstes))
    relativ = (
        skript.relative_to(wurzel).as_posix() if skript.is_relative_to(wurzel) else ""
    )
    return not relativ.startswith(PYTHON_SKRIPTE) or neu(wurzel, skript)


def schreibziele(befehl: list[str]) -> list[str]:
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
    elif name in IM_ORT and any(map(im_ort, argumente)):
        ziele += pfade[1:] if name == "sed" else pfade
    elif name == "dd":
        ziele += [a[3:] for a in argumente if a.startswith("of=")]
    elif name == "find" and LOESCHT & set(argumente):
        ziele += pfade
    optionen = optionswerte(argumente, ZIEL_OPTIONEN.get(name, ()))
    ziele += optionen
    if name in HIER_AUSPACKEN and not optionen and packt_hier_aus(name, argumente):
        ziele.append(".")
    return ziele


def optionswerte(argumente: list[str], optionen: tuple[str, ...]) -> list[str]:
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


def packt_hier_aus(name: str, argumente: list[str]) -> bool:
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
