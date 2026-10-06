"""Ablage der Belegdateien: Schnittstelle, Ordner und S3-kompatibler Bucket.

Datenkonzept Geräteradar, Abschnitt 10. ``Ablage`` legt, liest und löscht Dateien unter
einem Schlüssel wie ``<anbieter>/<JJJJ-MM-TT>/<name>`` (``belegmanifest``).
``LokaleAblage`` schreibt in einen Ordner (Tests, Actions-Artefakt). ``B2Ablage``
spricht einen privaten Bucket über die S3-Schnittstelle (Backblaze B2, Cloudflare R2),
Pfadstil, jede Anfrage selbst signiert (``belegsignatur``), HTTP über
``collect.http.sende``. Den Zugang liest ``B2Ablage.aus_umgebung`` nur aus den
Umgebungsvariablen in ``UMGEBUNG``; fehlt eine, wirft sie ``ArchivNichtEingerichtet``
mit den Namen, nie mit Werten. Kein Schlüssel steht in Log, Fehler oder ``repr``.
Antwortet der Bucket anders als erwartet, wirft die Ablage ``ArchivFehler`` mit Status.
``waehle_ablage`` nimmt den Bucket, wenn er eingerichtet ist, sonst den Ordner; der
trägt dann selbst den Hinweis „Archiv nicht eingerichtet“ (``Ablage.hinweis``), und
``belegarchiv`` meldet ihn in jedem Bericht.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Protocol
from urllib.parse import quote

from .. import http
from .belegsignatur import signiere
from .klickbeleg import sha256

log = logging.getLogger(__name__)

UMGEBUNG = {
    "endpunkt": "BELEG_ARCHIV_ENDPUNKT",
    "region": "BELEG_ARCHIV_REGION",
    "bucket": "BELEG_ARCHIV_BUCKET",
    "schluessel_id": "BELEG_ARCHIV_KEY_ID",
    "schluessel": "BELEG_ARCHIV_KEY",
}
NICHT_EINGERICHTET = "Archiv nicht eingerichtet"
ABLAGE_FRIST_S = 60.0
GELEGT = frozenset({200, 201})
GELOESCHT = frozenset({200, 204, 404})
_SCHLUESSEL = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*(?:/[A-Za-z0-9][A-Za-z0-9._-]*)*")


class ArchivNichtEingerichtet(RuntimeError):
    """Der Zugang zum Bucket fehlt; ``fehlend`` nennt die Variablen ohne Wert."""

    def __init__(self, fehlend: tuple[str, ...]) -> None:
        super().__init__(f"{NICHT_EINGERICHTET}: es fehlen {', '.join(fehlend)}")
        self.fehlend = fehlend


class ArchivFehler(RuntimeError):
    """Die Ablage nahm eine Datei nicht an oder gab sie nicht heraus."""


class Ablage(Protocol):
    """Legt, liest und löscht Dateien unter einem Schlüssel."""

    @property
    def ort(self) -> str:
        """Wo die Ablage liegt, ohne Zugangsdaten."""

    @property
    def hinweis(self) -> str | None:
        """Was an der Ablage fehlt, etwa „Archiv nicht eingerichtet“; sonst ``None``."""

    def lege(self, schluessel: str, daten: bytes, typ: str) -> None:
        """Legt ``daten`` unter ``schluessel`` ab; wirft ``ArchivFehler``."""

    def lies(self, schluessel: str) -> bytes | None:
        """Die Datei unter ``schluessel``; ``None``, wenn es sie nicht gibt."""

    def loesche(self, schluessel: str) -> None:
        """Löscht die Datei; eine fehlende ist kein Fehler."""


def pruefe_schluessel(schluessel: str) -> str:
    """Der Schlüssel, wenn gültig; ``..``, Leerzeichen und ``/`` vorn werfen."""
    if not _SCHLUESSEL.fullmatch(schluessel) or ".." in schluessel:
        raise ValueError(f"ungültiger Ablageschlüssel: {schluessel!r}")
    return schluessel


@dataclass(frozen=True)
class LokaleAblage:
    """Eine Ablage in einem Ordner; ``hinweis`` sagt, warum es kein Bucket ist."""

    ordner: Path
    hinweis: str | None = None

    @property
    def ort(self) -> str:
        """Der Ordner."""
        return str(self.ordner)

    def lege(self, schluessel: str, daten: bytes, typ: str) -> None:
        """Schreibt die Datei; Unterordner entstehen bei Bedarf."""
        ziel = self.ordner / pruefe_schluessel(schluessel)
        ziel.parent.mkdir(parents=True, exist_ok=True)
        ziel.write_bytes(daten)

    def lies(self, schluessel: str) -> bytes | None:
        """Die Datei oder ``None``."""
        ziel = self.ordner / pruefe_schluessel(schluessel)
        return ziel.read_bytes() if ziel.is_file() else None

    def loesche(self, schluessel: str) -> None:
        """Löscht die Datei, wenn es sie gibt."""
        (self.ordner / pruefe_schluessel(schluessel)).unlink(missing_ok=True)


@dataclass(frozen=True)
class B2Zugang:
    """Endpunkt, Region, Bucket und Schlüssel; der Schlüssel steht nie im ``repr``."""

    endpunkt: str
    region: str
    bucket: str
    schluessel_id: str
    schluessel: str = field(repr=False)


@dataclass(frozen=True)
class B2Ablage:
    """Ein privater Bucket über die S3-Schnittstelle, Pfadstil, signiert mit SigV4."""

    zugang: B2Zugang
    uhr: Callable[[], datetime]
    frist: float = ABLAGE_FRIST_S

    @classmethod
    def aus_umgebung(
        cls, umgebung: Mapping[str, str], uhr: Callable[[], datetime]
    ) -> B2Ablage:
        """Der Zugang aus ``UMGEBUNG``; fehlt etwas, ``ArchivNichtEingerichtet``."""
        werte = {f: (umgebung.get(name) or "").strip() for f, name in UMGEBUNG.items()}
        fehlend = tuple(UMGEBUNG[f] for f, wert in werte.items() if not wert)
        if fehlend:
            raise ArchivNichtEingerichtet(fehlend)
        return cls(B2Zugang(**werte), uhr)

    @property
    def ort(self) -> str:
        """Endpunkt und Bucket, ohne Schlüssel."""
        return f"{self.zugang.endpunkt.rstrip('/')}/{self.zugang.bucket}"

    @property
    def hinweis(self) -> str | None:
        """Ein eingerichteter Bucket hat keinen Hinweis."""
        return None

    def lege(self, schluessel: str, daten: bytes, typ: str) -> None:
        """PUT der Datei; jede Antwort außer 200 oder 201 wirft ``ArchivFehler``."""
        antwort = self._rufe("PUT", schluessel, daten, {"content-type": typ})
        if antwort.status_code not in GELEGT:
            raise ArchivFehler(
                f"{schluessel}: Ablage antwortet HTTP {antwort.status_code}"
            )

    def lies(self, schluessel: str) -> bytes | None:
        """GET der Datei; 404 heißt ``None``, jede andere Störung ``ArchivFehler``."""
        antwort = self._rufe("GET", schluessel, b"", {})
        if antwort.status_code == 404:
            return None
        if antwort.status_code != 200:
            raise ArchivFehler(
                f"{schluessel}: Ablage antwortet HTTP {antwort.status_code}"
            )
        return antwort.content

    def loesche(self, schluessel: str) -> None:
        """DELETE der Datei; eine fehlende ist kein Fehler."""
        antwort = self._rufe("DELETE", schluessel, b"", {})
        if antwort.status_code not in GELOESCHT:
            raise ArchivFehler(
                f"{schluessel}: Ablage antwortet HTTP {antwort.status_code}"
            )

    def _rufe(
        self, methode: str, schluessel: str, daten: bytes, kopf: dict[str, str]
    ) -> http.Antwort:
        pfad = quote(f"{self.zugang.bucket}/{pruefe_schluessel(schluessel)}")
        url = f"{self.zugang.endpunkt.rstrip('/')}/{pfad}"
        signiert = signiere(
            methode,
            url,
            kopf,
            sha256(daten),
            schluessel_id=self.zugang.schluessel_id,
            schluessel=self.zugang.schluessel,
            region=self.zugang.region,
            zeitpunkt=self.uhr(),
        )
        try:
            return http.sende(methode, url, daten, signiert, self.frist)
        except http.HttpFehler as fehler:
            art = type(fehler).__name__
            log.warning(
                "Beleg-Archiv: %s %s gescheitert (%s)", methode, schluessel, art
            )
            raise ArchivFehler(
                f"{schluessel}: Ablage nicht erreichbar ({art})"
            ) from fehler


def waehle_ablage(
    umgebung: Mapping[str, str], ordner: Path, uhr: Callable[[], datetime]
) -> tuple[Ablage, str | None]:
    """Der Bucket, wenn eingerichtet; sonst der Ordner mit dem benannten Hinweis.

    Das zweite Glied wiederholt ``Ablage.hinweis``.
    """
    try:
        return B2Ablage.aus_umgebung(umgebung, uhr), None
    except ArchivNichtEingerichtet as fehler:
        log.warning("Beleg-Archiv: %s; Belege nur unter %s", fehler, ordner)
        hinweis = f"{fehler}; Belege nur im Ordner {ordner}"
        return LokaleAblage(ordner, hinweis), hinweis
