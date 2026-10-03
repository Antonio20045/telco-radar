"""Claude-Code-Hooks: dieselben Prüfungen wie die Leiter, nur früher aufgerufen.

Aufruf aus ``.claude/settings.json`` als ``claude_hooks.py <hook>`` mit dem Ereignis
als JSON auf stdin. Exit 2 blockiert das Werkzeug oder lässt Claude weiterarbeiten,
die Begründung steht auf stderr. Die Grenze bleibt die Leiter im pre-push; der
Stop-Hook ruft ``pruefleiter.py --schnell`` und lässt Claude weiterarbeiten, solange
sie rot ist.
"""

from __future__ import annotations

import io
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

WURZEL = Path(__file__).resolve().parents[1]
BLOCKIERT = 2
GROSS_AB_ZEILEN = 800
BINAER_PROBE = 8192
STOP_HOECHSTENS_ROT = 3
STOP_ZAEHLER = "stop-rot.json"
STOP_SITZUNGEN = 20
STOP_HOECHSTENS_GESAMT = 10
NACH_EDIT_SEKUNDEN = 25
STOP_BEFUND = "stop-befund.txt"
HOOKS = ".githooks"
NIE_UEBERSPRINGEN = "--no-verify"
HOOKS_PFAD = re.compile(r"\bgit\b[^;&|\n]*core\.hookspath", re.IGNORECASE)
HOOKS_ORDNER = re.compile(
    r"\b(chmod|rm|mv|ln|cp|truncate|tee)\b[^;&|\n]*\.githooks|>\s*\S*\.githooks"
)
LANGE_OPTION = re.compile(r"(?<![\w-])--no-v[a-z]*")
QUOTING = str.maketrans("", "", "'\"\\")
TRENNER = frozenset({";", "&&", "||", "|", "&"})
GIT_OPTIONEN_MIT_WERT = frozenset({"-c", "-C", "--git-dir", "--work-tree"})
COMMIT_OPTIONEN_MIT_WERT = frozenset("mFcCt")
SITZUNG_STAND = "import stand; print('; '.join(stand.ungepruefte()))"


def befehl(ereignis: dict) -> str | None:
    """PreToolUse Bash: sperrt Befehle, die Git-Hooks abschalten oder überspringen,
    force-pushen oder alles vormerken; auch hinter Quoting und ``sh -c``."""
    text = str(ereignis.get("tool_input", {}).get("command", ""))
    flach = text.translate(QUOTING)
    if HOOKS_PFAD.search(flach):
        return "core.hooksPath ändert nur Antonio von Hand; die Hooks bleiben an."
    if HOOKS_ORDNER.search(flach):
        return "Die Git-Hooks unter .githooks ändert nur Antonio von Hand."
    for treffer in LANGE_OPTION.finditer(flach):
        if NIE_UEBERSPRINGEN.startswith(treffer.group()):
            return f"{NIE_UEBERSPRINGEN} ist gesperrt; mach die Leiter grün."
    for global_optionen, unterbefehl, argumente in _git_aufrufe(_woerter(text)):
        if any(o.startswith("alias.") for o in global_optionen):
            return "git -c alias.… ist gesperrt; rufe den Git-Befehl direkt."
        if unterbefehl == "commit" and _kurzoption(argumente, "n"):
            return "git commit -n überspringt den pre-commit und ist gesperrt."
        if unterbefehl == "push" and (
            _kurzoption(argumente, "f")
            or any(a.startswith(("--force", "+")) or ":+" in a for a in argumente)
        ):
            return "Force-Push ist gesperrt; erst git pull --rebase origin main."
        if unterbefehl == "add" and (
            _kurzoption(argumente, "A") or {".", "--all"} & set(argumente)
        ):
            return "git add nur mit Dateinamen, nie -A, --all oder ."
    return None


def _woerter(text: str, tiefe: int = 3) -> list[str]:
    try:
        woerter = shlex.split(text, posix=True)
    except ValueError:
        woerter = text.split()
    innen = [w for w in woerter if tiefe and any(z.isspace() for z in w)]
    return woerter + [";"] + [x for w in innen for x in [*_woerter(w, tiefe - 1), ";"]]


def _git_aufrufe(woerter: list[str]) -> list[tuple[list[str], str, list[str]]]:
    aufrufe = []
    for start, wort in enumerate(woerter):
        if wort.rsplit("/", 1)[-1] != "git":
            continue
        teil = []
        for folgend in woerter[start + 1 :]:
            if folgend in TRENNER:
                break
            teil.append(folgend.rstrip(";"))
            if folgend.endswith(";"):
                break
        global_optionen, stelle = [], 0
        while stelle < len(teil) and teil[stelle].startswith("-"):
            if teil[stelle] in GIT_OPTIONEN_MIT_WERT and stelle + 1 < len(teil):
                global_optionen.append(teil[stelle + 1])
                stelle += 1
            stelle += 1
        if stelle < len(teil):
            aufrufe.append((global_optionen, teil[stelle], teil[stelle + 1 :]))
    return aufrufe


def _kurzoption(argumente: list[str], buchstabe: str) -> bool:
    rest = iter(argumente)
    for option in rest:
        if option == "--":
            return False
        if option.startswith("--") or not option.startswith("-"):
            continue
        for stelle, zeichen in enumerate(option[1:], start=2):
            if zeichen == buchstabe:
                return True
            if zeichen in COMMIT_OPTIONEN_MIT_WERT:
                if stelle == len(option):
                    next(rest, None)
                break
    return False


def datei_lesen(ereignis: dict) -> str | None:
    """PreToolUse Read: große Dateien nur mit ``limit`` bis ``GROSS_AB_ZEILEN``."""
    eingabe = ereignis.get("tool_input", {})
    pfad = Path(str(eingabe.get("file_path", "")))
    try:
        inhalt = pfad.read_bytes()
    except OSError:
        return None
    if b"\0" in inhalt[:BINAER_PROBE]:
        return None
    zeilen = inhalt.count(b"\n")
    limit = eingabe.get("limit")
    if zeilen <= GROSS_AB_ZEILEN or (
        isinstance(limit, int) and 0 < limit <= GROSS_AB_ZEILEN
    ):
        return None
    return (
        f"{pfad.name} hat {zeilen} Zeilen: lies mit offset und limit "
        f"(höchstens {GROSS_AB_ZEILEN}) oder suche mit grep."
    )


def nach_edit(ereignis: dict, wurzel: Path = WURZEL) -> str | None:
    """PostToolUse Edit/Write: ruff format und ruff check auf die eine Datei.

    Läuft der Hook nicht im ``.venv``, ruft er sich dort auf; ohne ``.venv`` prüft er
    nichts, das meldet ``sitzung``.
    """
    pfad = Path(str(ereignis.get("tool_input", {}).get("file_path", "")))
    if pfad.suffix != ".py" or not pfad.is_file() or not pfad.is_relative_to(wurzel):
        return None
    eigenes_venv = sys.prefix != sys.base_prefix
    if not (eigenes_venv and (Path(sys.executable).parent / "ruff").exists()):
        venv = wurzel / ".venv" / "bin"
        if not (venv / "python").exists() or not (venv / "ruff").exists():
            return None
        aufruf = [str(venv / "python"), str(Path(__file__).resolve()), "nach_edit"]
        try:
            lauf = subprocess.run(
                aufruf,
                input=json.dumps(ereignis),
                capture_output=True,
                text=True,
                timeout=NACH_EDIT_SEKUNDEN,
            )
        except subprocess.TimeoutExpired:
            return f"ruff im .venv nach {NACH_EDIT_SEKUNDEN} s abgebrochen"
        if lauf.returncode == 0:
            return None
        return lauf.stderr.strip() or f"nach_edit im .venv endet mit {lauf.returncode}"
    import pruefleiter
    from leiter_schnell import stufe_lint

    ruff = str(pruefleiter.BIN / "ruff")
    ergebnis = stufe_lint(
        io.StringIO(), pruefleiter._lauf, ruff, [str(pfad)], pruefleiter.RUFF_BASIS
    )
    return None if ergebnis.gruen else "\n".join(ergebnis.zeilen)


def sitzung(ereignis: dict, wurzel: Path = WURZEL) -> str | None:
    """SessionStart: ``.venv`` aus ``.python-version``, Git-Hooks und ungeprüfte Commits
    in einer Zeile."""
    zeilen = []
    if not (wurzel / ".venv" / "bin" / "python").exists():
        lauf = subprocess.run(
            ["make", "venv"], cwd=wurzel, capture_output=True, text=True
        )
        letzte = (lauf.stdout + lauf.stderr).strip().splitlines()[-1:]
        zeilen.append(
            "make venv fertig"
            if lauf.returncode == 0
            else f"make venv gescheitert ({''.join(letzte)}{_python_fehlt(wurzel)}),"
            " Edit- und Stop-Hook prüfen nichts"
        )
    if (wurzel / HOOKS / "pre-commit").exists():
        subprocess.run(
            ["git", "config", "core.hooksPath", HOOKS], cwd=wurzel, check=False
        )
    else:
        zeilen.append(f"{HOOKS} fehlt, Commits laufen ohne Leiter")
    python = wurzel / ".venv" / "bin" / "python"
    if python.exists():
        befehl = [str(python), "-c", SITZUNG_STAND]
        lauf = subprocess.run(
            befehl, cwd=wurzel / "scripts", capture_output=True, text=True
        )
        zeilen += [lauf.stdout.strip()] if lauf.stdout.strip() else []
    print("Telco Radar: " + ("; ".join(zeilen) or "Umgebung bereit, alles geprüft"))
    return None


def _python_fehlt(wurzel: Path) -> str:
    """Gibt den Installationshinweis, wenn das Python aus ``.python-version`` fehlt."""
    try:
        version = (wurzel / ".python-version").read_text("utf-8").strip()
    except OSError:
        return ""
    if not version or shutil.which(f"python{version}"):
        return ""
    return f"; python{version} fehlt, auf dem Mac: brew install python@{version}"


def stop_ausgang(ordner: Path, gruen: bool, ausgabe: list[str], ereignis: dict) -> int:
    """Gibt den Exit-Code des Stop-Hooks: 2, solange die schnelle Leiter rot ist.

    Jede Sitzung zählt ihre roten Stopps selbst; ein Stopp, den kein Hook erzwungen
    hat (``stop_hook_active`` falsch), beginnt neu. Nach ``STOP_HOECHSTENS_ROT``
    erzwungenen Fortsetzungen in Folge oder ``STOP_HOECHSTENS_GESAMT`` insgesamt endet
    die Sitzung doch, und der Befund steht in ``STOP_BEFUND``; sonst wäre Rot eine
    Schleife. Ein grüner Stopp setzt nur die Folge zurück, die Summe bleibt.
    """
    zaehler = ordner / STOP_ZAEHLER
    sitzung_id = str(ereignis.get("session_id", ""))
    try:
        stand = json.loads(zaehler.read_text("utf-8"))
    except (OSError, ValueError):
        stand = {}
    stand = stand if isinstance(stand, dict) else {}
    bisher = stand.pop(sitzung_id, None)
    paar = isinstance(bisher, list) and [type(z) for z in bisher] == [int, int]
    gueltig = paar and min(bisher) >= 0
    rot, gesamt = bisher if gueltig else (0, 0)
    rot = 0 if ereignis.get("stop_hook_active") is False else rot
    ende = rot >= STOP_HOECHSTENS_ROT or gesamt >= STOP_HOECHSTENS_GESAMT
    ordner.mkdir(parents=True, exist_ok=True)
    if not gruen and ende:
        (ordner / STOP_BEFUND).write_text("\n".join(ausgabe) + "\n", "utf-8")
    rot, gesamt = (0, gesamt) if gruen or ende else (rot + 1, gesamt + 1)
    if gesamt:
        stand[sitzung_id] = [rot, gesamt]
    behalten = dict(list(stand.items())[-STOP_SITZUNGEN:])
    neu = zaehler.with_suffix(f".{os.getpid()}")
    neu.write_text(json.dumps(behalten), "utf-8")
    os.replace(neu, zaehler)
    if gruen or ende:
        return 0
    print("\n".join(ausgabe), file=sys.stderr)
    return BLOCKIERT


def stop(ereignis: dict, wurzel: Path = WURZEL) -> int:
    """Stop: die schnelle Leiter auf dem Arbeitsstand, Exit 2 solange sie rot ist."""
    python = wurzel / ".venv" / "bin" / "python"
    ordner = wurzel / ".pruefleiter"
    if not python.exists():
        hinweis = f"{python} fehlt, die Leiter lief nicht: make venv"
        print(json.dumps({"systemMessage": hinweis}))
        return 0
    leiter = [str(python), str(wurzel / "scripts" / "pruefleiter.py"), "--schnell"]
    lauf = subprocess.run(leiter, cwd=wurzel, capture_output=True, text=True)
    ausgabe = (lauf.stdout + lauf.stderr).splitlines()
    return stop_ausgang(ordner, lauf.returncode == 0, ausgabe, ereignis)


HOOK: dict[str, Callable[[dict], str | None]] = {
    "befehl": befehl,
    "datei_lesen": datei_lesen,
    "nach_edit": nach_edit,
    "sitzung": sitzung,
}


def lies_ereignis(roh: str) -> dict:
    """Gibt das Ereignis aus stdin; ein unlesbares Ereignis ist leer."""
    try:
        ereignis = json.loads(roh or "{}")
    except ValueError:
        return {}
    return ereignis if isinstance(ereignis, dict) else {}


def main(argv: list[str]) -> int:
    """Führt den Hook ``argv[0]`` aus; Exit 2 mit Grund auf stderr blockiert."""
    if len(argv) != 1 or argv[0] not in [*HOOK, "stop"]:
        print(f"Aufruf: claude_hooks.py {{{','.join(HOOK)},stop}}", file=sys.stderr)
        return 1
    ereignis = lies_ereignis(sys.stdin.read())
    if argv[0] == "stop":
        return stop(ereignis)
    grund = HOOK[argv[0]](ereignis)
    if grund is None:
        return 0
    print(grund, file=sys.stderr)
    return BLOCKIERT


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
