"""Attrappe für `beleg_ablage.Releases`: merkt sich jeden Aufruf, kein Netz."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from telco_radar.beleg_ablage import GhFehler


class AttrappeReleases:
    """GitHub im Speicher: Tag -> Dateinamen, dazu das Protokoll der Aufrufe."""

    def __init__(
        self,
        anhaenge: dict[str, list[str]] | None = None,
        lesefehler: bool = False,
        scheitern_bei: tuple[str, ...] = (),
    ) -> None:
        self.stand = {tag: list(d) for tag, d in (anhaenge or {}).items()}
        self.zaehler = 0
        self.zeiten: dict[tuple[str, str], str] = {}
        for tag, dateien in self.stand.items():
            for datei in dateien:
                self._stempel(tag, datei)
        self.lesefehler = lesefehler
        self.scheitern_bei = scheitern_bei
        self.angelegt: list[str] = []
        self.hochgeladen: list[tuple[str, list[str]]] = []
        self.releases_geloescht: list[str] = []
        self.assets_geloescht: list[tuple[str, str]] = []

    def _stempel(self, tag: str, datei: str) -> None:
        """Uploadzeit: eine aufsteigende Zahl als Text, später ist größer."""
        self.zaehler += 1
        self.zeiten[(tag, datei)] = f"2026-11-09T{self.zaehler:08d}Z"

    def hochgeladen_am(self) -> dict[str, dict[str, str]]:
        if self.lesefehler or "zeiten" in self.scheitern_bei:
            raise GhFehler("gh api: Exit 1: kein Zugriff")
        return {
            tag: {d: self.zeiten[(tag, d)] for d in dateien if (tag, d) in self.zeiten}
            for tag, dateien in self.stand.items()
        }

    def _pruefe(self, aufruf: str, tag: str) -> None:
        if aufruf in self.scheitern_bei or tag in self.scheitern_bei:
            raise GhFehler(f"gh {aufruf} {tag}: Exit 1: kaputt")

    def anhaenge(self) -> dict[str, list[str]]:
        if self.lesefehler:
            raise GhFehler("gh api: Exit 1: kein Zugriff")
        return {tag: list(d) for tag, d in self.stand.items()}

    def release_anlegen(self, tag: str, titel: str) -> None:
        self._pruefe("anlegen", tag)
        self.angelegt.append(tag)
        self.stand.setdefault(tag, [])

    def hochladen(self, tag: str, dateien: Sequence[Path]) -> None:
        """Wie GitHub: paralleles ``--clobber`` desselben Namens gibt HTTP 404."""
        self._pruefe("hochladen", tag)
        namen = [d.name for d in dateien]
        if len(set(namen)) != len(namen):
            raise GhFehler(
                f"gh release upload: Exit 1: HTTP 404: Not Found "
                f"(https://uploads.github.com/repos/x/y/releases/1/assets?name={namen[0]})"
            )
        self.hochgeladen.append((tag, namen))
        liste = self.stand.setdefault(tag, [])
        for name in namen:
            if name not in liste:
                liste.append(name)
                self._stempel(tag, name)

    def release_loeschen(self, tag: str) -> None:
        self._pruefe("loeschen", tag)
        self.releases_geloescht.append(tag)
        self.stand.pop(tag, None)

    def asset_loeschen(self, tag: str, datei: str) -> None:
        self._pruefe("asset", tag)
        self.assets_geloescht.append((tag, datei))
        self.stand[tag].remove(datei)
