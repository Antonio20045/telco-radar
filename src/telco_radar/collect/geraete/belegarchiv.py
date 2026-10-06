"""Archiv eines Klick-Laufs: Dateien in die Ablage, Zeilen ins Manifest, Stempel.

``archiviere`` legt je offenem Beleg Screenshot und Mitschnitt in die Ablage
(``belegablage``), hängt die Zeilen an das Manifest ihres Tages und Anbieters
(``belegmanifest``) und stempelt jedes berührte Manifest mit einer Stempelzeile über
alle Zeilen davor (``belegstempel``). Erst wenn beide Dateien liegen und die Zeile im
Manifest steht, heißt die Kombination im Lauf ``belegt`` und kann gültig sein. Scheitert
die Ablage, ist das Archiv ``gestoert`` mit Grund; jede Kombination, deren Beleg nicht
in Ablage und Manifest kam, wird ``fehlt`` mit Grund (``klicklauf.beleg_fehlt``), und
der Bericht nennt ihre Varianten. Ein ausgefallener Stempel steht im Manifest und stört
nichts. Den Hinweis der Ablage („Archiv nicht eingerichtet“) trägt jeder Bericht. Hat
der Lauf keinen Beleg, heißt das ``ohne_beleg``. ``raeume_auf`` löscht die Dateien, die
``belegaufbewahrung`` nicht mehr behält. Zeitpunkt und Stichtag kommen vom Aufrufer.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterable
from dataclasses import dataclass, replace
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
from .klickbeleg import Beleg, Belegpaket
from .klickecho import Variante
from .klicklauf import BELEG_OFFEN, BELEGT, Klicklauf, beleg_fehlt

log = logging.getLogger(__name__)

ARCHIVIERT = "archiviert"
GESTOERT = "gestoert"
OHNE_BELEG = "ohne_beleg"
NICHT_ABGELEGT = "Beleg nicht archiviert"

Stempler = Callable[[str], tuple[Stempel, ...]]


@dataclass(frozen=True)
class Archivbericht:
    """Was das Archiv eines Laufs erreicht hat, mit Grund, Hinweis und Lücken.

    ``fehlend`` nennt die Varianten, deren Beleg nicht in Ablage und Manifest kam.
    """

    zustand: str
    grund: str | None
    ort: str
    belege: int
    manifeste: tuple[Path, ...]
    stempel: tuple[Stempel, ...]
    hinweis: str | None = None
    fehlend: tuple[Variante, ...] = ()


def archiviere(
    lauf: Klicklauf,
    ablage: Ablage,
    wurzel: Path,
    zeitpunkt: datetime,
    *,
    stempler: Stempler = stemple,
) -> Archivbericht:
    """Legt die offenen Belege ab, schreibt ihre Manifeste und setzt ihren Status."""
    offen = [
        (stelle, e.beleg)
        for stelle, e in enumerate(lauf.ergebnisse)
        if e.beleg is not None and e.beleg_status == BELEG_OFFEN
    ]
    if not offen:
        leer = "keine Belege im Lauf"
        return Archivbericht(OHNE_BELEG, leer, ablage.ort, 0, (), (), ablage.hinweis)
    gelegt, grund = _lege(offen, ablage)
    je_manifest: dict[Path, list[tuple[int, Belegpaket]]] = {}
    for stelle, paket in gelegt:
        pfad = manifestpfad(wurzel, paket.beleg.anbieter, belegtag(paket.beleg))
        je_manifest.setdefault(pfad, []).append((stelle, paket))
    stempel: list[Stempel] = []
    belegt: set[int] = set()
    geschrieben: list[Path] = []
    for pfad, eintraege in je_manifest.items():
        try:
            haenge_an(pfad, [p.beleg for _, p in eintraege])
            geschrieben.append(pfad)
            belegt.update(stelle for stelle, _ in eintraege)
            stempel += _stemple(pfad, zeitpunkt, stempler)
        except OSError as fehler:
            grund = grund or f"Archiv gestört: Manifest {pfad.name} ({fehler})"
            log.warning("Beleg-Archiv %s: %s", lauf.anbieter, grund)
    fehlend = _setze_status(lauf, [s for s, _ in offen], belegt, grund)
    return Archivbericht(
        GESTOERT if grund else ARCHIVIERT,
        grund,
        ablage.ort,
        len(belegt),
        tuple(geschrieben),
        tuple(stempel),
        ablage.hinweis,
        fehlend,
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


def _lege(
    offen: list[tuple[int, Belegpaket]], ablage: Ablage
) -> tuple[list[tuple[int, Belegpaket]], str | None]:
    """Legt Beleg für Beleg ab; nach der ersten Störung wird nichts mehr versucht."""
    gelegt: list[tuple[int, Belegpaket]] = []
    for stelle, paket in offen:
        beleg = paket.beleg
        try:
            for datei, daten in (
                (beleg.bild, paket.bild),
                (beleg.mitschnitt, paket.mitschnitt),
            ):
                ablage.lege(ablageschluessel(beleg, datei), daten, datei.typ)
        except ArchivFehler as fehler:
            grund = f"Archiv gestört: {fehler}"
            log.warning("Beleg-Archiv %s: %s", beleg.anbieter, grund)
            return gelegt, grund
        gelegt.append((stelle, paket))
    return gelegt, None


def _stemple(
    pfad: Path, zeitpunkt: datetime, stempler: Stempler
) -> tuple[Stempel, ...]:
    digest, zeilen = stand(pfad)
    neu = stempler(digest)
    zeit = zeitpunkt.astimezone(UTC).strftime(ZEITFORMAT)
    haenge_an(pfad, [Stempelzeile(digest, zeilen, zeit, neu)])
    return neu


def _setze_status(
    lauf: Klicklauf, stellen: list[int], belegt: set[int], grund: str | None
) -> tuple[Variante, ...]:
    """Belegt, was in Ablage und Manifest steht; jeder andere Beleg fehlt mit Grund."""
    fehlend = []
    for stelle in stellen:
        ergebnis = lauf.ergebnisse[stelle]
        if stelle in belegt:
            lauf.ergebnisse[stelle] = replace(ergebnis, beleg_status=BELEGT)
            continue
        warum = f"{NICHT_ABGELEGT}: {grund or 'nicht versucht'}"
        lauf.ergebnisse[stelle] = beleg_fehlt(ergebnis, warum)
        fehlend.append(ergebnis.variante)
    return tuple(fehlend)
