"""Die GitHub-CLI hinter der Belege-Ablage (``gh``): Aufrufe, Fehler, Zeitgrenze.

``Gh`` kapselt die Release-Aufrufe (Lesen, Anlegen, Hochladen, Löschen); ``runner`` ist
im Test austauschbar. Außer ``gh`` gibt es kein Netz; das Token liegt nur in der
Umgebung (``GH_TOKEN``), nie in Argumenten oder Ausgaben. ``beleg_ablage`` führt die
Regeln darüber und reicht diese Namen unverändert weiter.
"""

from __future__ import annotations

import json
import subprocess
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

from .beleg_regeln import REPO, ist_beleg_tag

ZEIT_JE_AUFRUF_S = 300
Runner = Callable[[Sequence[str]], "subprocess.CompletedProcess[str]"]


class GhFehler(RuntimeError):
    """Ein ``gh``-Aufruf ist gescheitert; die Meldung nennt nur den Befehl."""


@dataclass(frozen=True)
class ReleaseInfo:
    """ID und Entwurfsstatus eines Releases."""

    id: int
    entwurf: bool


def _lauf(argv: Sequence[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        argv, capture_output=True, text=True, timeout=ZEIT_JE_AUFRUF_S, check=False
    )


def runner_mit_frist(
    ende: float,
    uhr: Callable[[], float] = time.monotonic,
    lauf: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> Runner:
    """Ein ``gh``-Runner, dessen Timeout die Restzeit bis ``ende`` (monotone Zeit)
    ist, höchstens ``ZEIT_JE_AUFRUF_S``; ist sie aufgebraucht, scheitert der Aufruf
    sofort mit ``TimeoutExpired`` (``Gh`` macht daraus ``GhFehler``), ohne ``gh`` zu
    starten."""

    def runner(argv: Sequence[str]) -> subprocess.CompletedProcess[str]:
        rest = ende - uhr()
        if rest <= 0:
            raise subprocess.TimeoutExpired(list(argv), 0)
        return lauf(
            argv,
            capture_output=True,
            text=True,
            timeout=min(ZEIT_JE_AUFRUF_S, rest),
            check=False,
        )

    return runner


class Gh:
    """Die Release-Aufrufe der GitHub-CLI; ``runner`` ist im Test austauschbar."""

    def __init__(self, runner: Runner = _lauf, repo: str = REPO) -> None:
        self._runner, self._repo = runner, repo

    def _gh(self, *argumente: str) -> str:
        argv = ["gh", *argumente]
        try:
            fertig = self._runner(argv)
        except (OSError, subprocess.TimeoutExpired) as fehler:
            raise GhFehler(f"gh {argumente[0]} {argumente[1]}: {fehler}") from fehler
        if fertig.returncode != 0:
            letzte = (fertig.stderr or "").strip().splitlines()[-1:] or ["ohne Meldung"]
            raise GhFehler(
                f"gh {argumente[0]} {argumente[1]}: "
                f"Exit {fertig.returncode}: {letzte[0]}"
            )
        return fertig.stdout or ""

    def anhaenge(self) -> dict[str, list[str]]:
        """Alle Releases im Schema mit ihren Anhängen; wirft ``GhFehler`` bei
        Lesefehlern.

        Eine Zeile JSON je Release (``--paginate`` mit ``--jq``), damit seitenweises
        Lesen kein Listenende zerreißt.
        """
        ausgabe = self._gh(
            "api",
            "--paginate",
            f"repos/{self._repo}/releases?per_page=100",
            "--jq",
            ".[] | {tag: .tag_name, dateien: [.assets[].name]}",
        )
        ergebnis: dict[str, list[str]] = {}
        for zeile in ausgabe.splitlines():
            if not zeile.strip():
                continue
            try:
                eintrag = json.loads(zeile)
                tag, dateien = str(eintrag["tag"]), list(eintrag["dateien"])
            except (ValueError, KeyError, TypeError) as fehler:
                raise GhFehler(f"gh api: Antwort unlesbar: {fehler}") from fehler
            if ist_beleg_tag(tag):
                ergebnis[tag] = sorted(str(d) for d in dateien)
        return ergebnis

    def release_info(self, tag: str) -> ReleaseInfo | None:
        """ID und Entwurfsstatus des Releases zum Tag (auch Entwürfe), sonst ``None``.

        Liest die Liste statt ``releases/tags/<tag>``: Letzteres kennt keine Entwürfe.
        """
        ausgabe = self._gh(
            "api",
            "--paginate",
            f"repos/{self._repo}/releases?per_page=100",
            "--jq",
            f'.[] | select(.tag_name == "{tag}") | {{id: .id, draft: .draft}}',
        )
        for zeile in ausgabe.splitlines():
            if not zeile.strip():
                continue
            try:
                eintrag = json.loads(zeile)
                return ReleaseInfo(int(eintrag["id"]), bool(eintrag["draft"]))
            except (ValueError, KeyError, TypeError) as fehler:
                raise GhFehler(f"gh api: Antwort unlesbar: {fehler}") from fehler
        return None

    def release_anlegen(self, tag: str, titel: str) -> None:
        """Legt ein Pre-Release ohne „latest“ an."""
        self._gh(
            "release",
            "create",
            tag,
            "--repo",
            self._repo,
            "--title",
            titel,
            "--notes",
            titel,
            "--prerelease",
            "--latest=false",
        )

    def hochladen(self, tag: str, dateien: Sequence[Path]) -> None:
        """Lädt Dateien hoch; gleiche Namen werden überschrieben."""
        self._gh(
            "release",
            "upload",
            tag,
            *map(str, dateien),
            "--repo",
            self._repo,
            "--clobber",
        )

    def release_loeschen(self, tag: str) -> None:
        """Löscht Release und Tag."""
        self._gh(
            "release", "delete", tag, "--repo", self._repo, "--yes", "--cleanup-tag"
        )

    def asset_loeschen(self, tag: str, datei: str) -> None:
        """Löscht eine Datei eines Releases."""
        self._gh("release", "delete-asset", tag, datei, "--repo", self._repo, "--yes")
