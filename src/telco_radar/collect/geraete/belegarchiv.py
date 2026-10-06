"""Archiv eines Klick-Laufs: Dateien in die Ablage, Zeilen ins Manifest, Stempel.

``archiviere`` legt je Beleg Screenshot und Mitschnitt in die Ablage
(``belegablage``), hängt die Zeilen an das Manifest ihres Tages und Anbieters
(``belegmanifest``) und stempelt jedes berührte Manifest mit einer Stempelzeile über
alle Zeilen davor (``belegstempel``). Ein Beleg kommt erst ins Manifest, wenn beide
Dateien liegen. Scheitert die Ablage, ist das Archiv ``gestoert`` mit Grund; Belege bis
dahin stehen im Manifest. Ein ausgefallener Stempel steht im Manifest und stört nichts.
Hat der Lauf keinen Beleg, heißt das ``ohne_beleg``, nicht „archiviert“. ``raeume_auf``
löscht die Dateien, die ``belegaufbewahrung`` nicht mehr behält. Zeitpunkt und
Stichtag kommen vom Aufrufer.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path

from .belegablage import Ablage, ArchivFehler
from .belegaufbewahrung import Entscheidung, aufbewahrung
from .belegmanifest import (
    ZEITFORMAT,
    Stempelzeile,
    ablageschluessel,
    belegtag,
    haenge_an,
    manifestpfad,
    stand,
)
from .belegstempel import Stempel, stemple
from .klickbeleg import Beleg
from .klicklauf import Klicklauf

log = logging.getLogger(__name__)

ARCHIVIERT = "archiviert"
GESTOERT = "gestoert"
OHNE_BELEG = "ohne_beleg"


@dataclass(frozen=True)
class Archivbericht:
    """Was das Archiv eines Laufs erreicht hat, mit Grund und Hinweis."""

    zustand: str
    grund: str | None
    ort: str
    belege: int
    manifeste: tuple[Path, ...]
    stempel: tuple[Stempel, ...]
    hinweis: str | None = None


def archiviere(
    lauf: Klicklauf,
    ablage: Ablage,
    wurzel: Path,
    zeitpunkt: datetime,
    *,
    stempler: Callable[[str], tuple[Stempel, ...]] = stemple,
    hinweis: str | None = None,
) -> Archivbericht:
    """Legt die Belege des Laufs ab, schreibt und stempelt ihre Manifeste."""
    pakete = [e.beleg for e in lauf.ergebnisse if e.beleg is not None]
    if not pakete:
        leer = "keine Belege im Lauf"
        return Archivbericht(OHNE_BELEG, leer, ablage.ort, 0, (), (), hinweis)
    je_manifest: dict[Path, list[Beleg]] = {}
    grund: str | None = None
    for paket in pakete:
        beleg = paket.beleg
        try:
            for datei, daten in (
                (beleg.bild, paket.bild),
                (beleg.mitschnitt, paket.mitschnitt),
            ):
                ablage.lege(ablageschluessel(beleg, datei), daten, datei.typ)
        except ArchivFehler as fehler:
            grund = f"Archiv gestört: {fehler}"
            log.warning("Beleg-Archiv %s: %s", lauf.anbieter, grund)
            break
        pfad = manifestpfad(wurzel, beleg.anbieter, belegtag(beleg))
        je_manifest.setdefault(pfad, []).append(beleg)
    stempel: list[Stempel] = []
    for pfad, belege in je_manifest.items():
        haenge_an(pfad, belege)
        digest, zeilen = stand(pfad)
        neu = stempler(digest)
        zeit = zeitpunkt.astimezone(UTC).strftime(ZEITFORMAT)
        haenge_an(pfad, [Stempelzeile(digest, zeilen, zeit, neu)])
        stempel += neu
    return Archivbericht(
        GESTOERT if grund else ARCHIVIERT,
        grund,
        ablage.ort,
        sum(map(len, je_manifest.values())),
        tuple(je_manifest),
        tuple(stempel),
        hinweis,
    )


def raeume_auf(
    belege: Iterable[Beleg], stichtag: date, ablage: Ablage
) -> list[Entscheidung]:
    """Löscht die Dateien jedes Belegs, den die Aufbewahrung nicht mehr behält."""
    entscheidungen = aufbewahrung(belege, stichtag)
    for entscheidung in entscheidungen:
        if not entscheidung.behalten:
            for schluessel in entscheidung.dateien:
                ablage.loesche(schluessel)
    return entscheidungen
