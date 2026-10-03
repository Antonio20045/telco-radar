"""Prüfstempel: Ein grüner Volllauf stempelt den Baum, den er geprüft hat.

Ein Stempel ist eine leere Datei ``<git-common-dir>/pruefleiter/gruen/<baum>``; ``baum``
ist die Kennung des Syntaxbaums aus ``git write-tree`` über den Arbeitsstand. Ein
Commit gilt als geprüft, wenn sein Baum (``<commit>^{tree}``) gestempelt ist. Stempel
gelten nur im eigenen Klon und in seinen Worktrees.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

BOT = "telco-radar-bot"
BOT_PFADE = ("data/", "site/")
EINFUEHRUNG = "scripts/pruefstempel.py"
_LEERE_KENNUNG = "0" * 40


class StempelFehler(RuntimeError):
    """Git konnte den Baum oder den Verlauf nicht liefern."""


@dataclass(frozen=True)
class Ungeprueft:
    """Commits auf dem Zweig, die seit dem jüngsten gestempelten Commit kamen."""

    commits: list[str]
    stempel_gefunden: bool


def git(
    wurzel: Path, *argumente: str, index: Path | None = None, mit_hook: bool = False
) -> str:
    """Ruft git, ohne ``mit_hook`` ohne die Git-Umgebung eines Hooks.

    ``index`` ersetzt den Index.
    """
    umgebung = {
        k: v for k, v in os.environ.items() if mit_hook or not k.startswith("GIT_")
    }
    if index is not None:
        umgebung["GIT_INDEX_FILE"] = str(index)
    lauf = subprocess.run(
        ["git", *argumente],
        cwd=wurzel,
        env=umgebung,
        capture_output=True,
        text=True,
        check=False,
    )
    if lauf.returncode != 0:
        raise StempelFehler(f"git {' '.join(argumente)}: {lauf.stderr.strip()}")
    return lauf.stdout


def stempel_ordner(wurzel: Path) -> Path:
    """Gibt ``pruefleiter/gruen`` im gemeinsamen Git-Ordner aller Worktrees zurück."""
    gemeinsam = Path(git(wurzel, "rev-parse", "--git-common-dir").strip())
    return (gemeinsam if gemeinsam.is_absolute() else wurzel / gemeinsam).resolve() / (
        "pruefleiter/gruen"
    )


def arbeitsbaum(wurzel: Path) -> str:
    """Gibt die Baumkennung des Arbeitsstands samt nicht ignorierter neuer Dateien."""
    echter_index = Path(git(wurzel, "rev-parse", "--git-path", "index").strip())
    if not echter_index.is_absolute():
        echter_index = wurzel / echter_index
    with tempfile.TemporaryDirectory() as ordner:
        index = Path(ordner) / "index"
        if echter_index.is_file():
            shutil.copyfile(echter_index, index)
        else:
            git(wurzel, "read-tree", "HEAD", index=index)
        git(wurzel, "add", "-A", ".", index=index)
        return git(wurzel, "write-tree", index=index).strip()


def geaenderte_pfade(wurzel: Path, alt: str, neu: str) -> set[str]:
    """Gibt die Pfade zurück, in denen sich zwei Bäume unterscheiden."""
    return set(git(wurzel, "diff-tree", "-r", "--name-only", alt, neu).split())


def stempeln(wurzel: Path, baum: str) -> Path:
    """Legt den Stempel für ``baum`` an und gibt seinen Pfad zurück."""
    ordner = stempel_ordner(wurzel)
    ordner.mkdir(parents=True, exist_ok=True)
    stempel = ordner / baum
    stempel.touch()
    return stempel


def ist_gestempelt(wurzel: Path, baum: str) -> bool:
    """Wahr, wenn ein grüner Volllauf genau diesen Baum geprüft hat."""
    return (stempel_ordner(wurzel) / baum).is_file()


def einfuehrung(wurzel: Path, ref: str) -> str | None:
    """Gibt den Commit zurück, mit dem die Stempel kamen; ältere tragen keinen."""
    befehl = ["log", "--format=%H", "--diff-filter=A", ref, "--", EINFUEHRUNG]
    commits = git(wurzel, *befehl).split()
    return commits[-1] if commits else None


def ungestempelte(wurzel: Path, ref: str = "origin/main") -> Ungeprueft:
    """Gibt die Commits auf ``ref`` zurück, die nach dem jüngsten Stempel kamen.

    Ein Commit von ``BOT``, der nur ``data/`` und ``site/`` ändert, ist ein Datenlauf:
    Die Tests lesen diese Ordner nicht, er braucht keinen Stempel. Gesucht wird bis
    zum Commit, der die Stempel einführte.
    """
    start = einfuehrung(wurzel, ref)
    if start is None:
        return Ungeprueft([], stempel_gefunden=False)
    ordner = stempel_ordner(wurzel)
    bereich = [ref, f"^{start}^"] if _hat_eltern(wurzel, start) else [ref]
    befehl = ["log", "--format=%x00%H %T %an", "--name-only", *bereich]
    commits = []
    for block in git(wurzel, *befehl).split("\x00")[1:]:
        kopf, *pfade = block.strip().splitlines()
        commit, baum, autor = kopf.split(" ", 2)
        if (ordner / baum).is_file():
            return Ungeprueft(commits, stempel_gefunden=True)
        datenlauf = autor == BOT and all(p.startswith(BOT_PFADE) for p in pfade if p)
        if not datenlauf:
            commits.append(commit)
    return Ungeprueft(commits, stempel_gefunden=False)


def _hat_eltern(wurzel: Path, commit: str) -> bool:
    return len(git(wurzel, "rev-list", "--parents", "-n", "1", commit).split()) > 1


def ist_loeschung(zeilen: list[str]) -> bool:
    """Wahr, wenn jede Zeile, die git an pre-push gibt, einen Zweig löscht."""
    lokale = [z.split()[1] for z in zeilen if len(z.split()) == 4]
    return bool(lokale) and all(sha == _LEERE_KENNUNG for sha in lokale)


def gepushte_commits(zeilen: list[str]) -> set[str]:
    """Gibt die lokalen Commits, die git an pre-push meldet, ohne Löschungen."""
    lokale = {z.split()[1] for z in zeilen if len(z.split()) == 4}
    return lokale - {_LEERE_KENNUNG}


def vor_push(wurzel: Path, zeilen: list[str]) -> tuple[int, str] | None:
    """Prüft vor ``--voll`` im pre-push; ``None`` heißt weiter, sonst Exit und Grund."""
    if ist_loeschung(zeilen):
        return 0, "pre-push: nur Löschungen, keine Prüfung"
    kopf = git(wurzel, "rev-parse", "HEAD").strip()
    fremd = {sha for sha in gepushte_commits(zeilen) if sha != kopf}
    if fremd:
        kurz = ", ".join(sorted(sha[:7] for sha in fremd))
        return 1, f"pre-push: gepusht wird nicht HEAD ({kurz}); nur HEAD wird geprüft"
    if arbeitsbaum(wurzel) != git(wurzel, "rev-parse", "HEAD^{tree}").strip():
        return 1, (
            "pre-push: Arbeitsstand weicht von HEAD ab (geänderte oder neue Dateien);"
            " geprüft würde nicht, was gepusht wird"
        )
    try:
        git(wurzel, "fetch", "--quiet", "origin", "main")
    except StempelFehler as fehler:
        return 1, f"pre-push: origin/main nicht abrufbar ({fehler})"
    try:
        git(wurzel, "merge-base", "--is-ancestor", "origin/main", "HEAD")
    except StempelFehler:
        return 1, "pre-push: origin/main ist neuer, erst git pull --rebase origin main"
    return None


def baum_oder_nichts(wurzel: Path) -> str | None:
    """Gibt den Baum des Arbeitsstands, oder ``None`` außerhalb eines Repos."""
    try:
        return arbeitsbaum(wurzel)
    except StempelFehler:
        return None


def stemple_lauf(wurzel: Path, vorher: str | None, geschrieben: list[str]) -> str:
    """Stempelt den geprüften Baum nach einem grünen Volllauf.

    Hat die Leiter selbst nur Basen gesenkt oder Untergrenzen gehoben, ist auch der
    Baum danach geprüft und bekommt einen Stempel. Hat sich während des Laufs etwas
    anderes geändert, ist offen, welcher Stand geprüft wurde: kein Stempel.
    """
    nachher = baum_oder_nichts(wurzel)
    if vorher is None or nachher is None:
        return "nicht gestempelt: kein Git-Baum lesbar"
    if nachher == vorher:
        stempeln(wurzel, vorher)
        return f"gestempelt {vorher[:12]}"
    fremd = geaenderte_pfade(wurzel, vorher, nachher) - set(geschrieben)
    if fremd:
        return (
            f"nicht gestempelt: während des Laufs geändert: {', '.join(sorted(fremd))}"
        )
    stempeln(wurzel, vorher)
    stempeln(wurzel, nachher)
    return f"gestempelt {vorher[:12]} und {nachher[:12]}"
