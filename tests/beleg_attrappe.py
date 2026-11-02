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
        self.lesefehler = lesefehler
        self.scheitern_bei = scheitern_bei
        self.angelegt: list[str] = []
        self.hochgeladen: list[tuple[str, list[str]]] = []
        self.releases_geloescht: list[str] = []
        self.assets_geloescht: list[tuple[str, str]] = []

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
        self._pruefe("hochladen", tag)
        namen = [d.name for d in dateien]
        self.hochgeladen.append((tag, namen))
        liste = self.stand.setdefault(tag, [])
        liste.extend(n for n in namen if n not in liste)

    def release_loeschen(self, tag: str) -> None:
        self._pruefe("loeschen", tag)
        self.releases_geloescht.append(tag)
        self.stand.pop(tag, None)

    def asset_loeschen(self, tag: str, datei: str) -> None:
        self._pruefe("asset", tag)
        self.assets_geloescht.append((tag, datei))
        self.stand[tag].remove(datei)
