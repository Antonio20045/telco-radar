"""Belegbilder in GitHub-Releases legen, Abgelaufenes löschen (``gh``, beleg_regeln).

Quelle der Wahrheit für die Seite sind allein die Anhänge der Releases. Es gibt keinen
Index im Repo: wer ein Bild ins richtige Release lädt, hat es veröffentlicht, wer eines
löscht, hat es zurückgenommen. ``beleg_manifest`` liest die Anhänge und schreibt, was
die Seite braucht.

``veroeffentliche`` (Klick-Job): Jedes Bild geht ins Tages-Release; eine große Änderung
geht zusätzlich ins Monats-Release (``beleg_regeln.gross_tag``). Fehlende Releases
entstehen als Pre-Release ohne „latest“. Dateien gehen in Paketen hoch (``PAKET``), mit
``--clobber`` (zweiter Lauf am selben Tag); kein Name doppelt (HTTP 404). Ein
gescheitertes Paket steht in der Bilanz, die übrigen laufen weiter (Clean Code 5).

``raeume_auf`` (Geräte-Job): Tages-Releases nach ``AUFBEWAHRUNG_TAGE``, Monats-Releases
nach ``AUFBEWAHRUNG_GROSS_TAGE`` löschen; in jüngeren Monats-Releases einzelne Bilder,
die älter sind. Was nicht im Schema liegt, rührt nichts an.

Ein Paket kann halb ankommen (``gh`` lädt die Dateien parallel und bricht beim ersten
Fehler ab) und frisch angelegte Releases antworten kurz mit 404. Darum liest
``veroeffentliche`` nach einem Fehler die Anhänge, zählt, was angekommen ist, und lädt
bei vorübergehenden Fehlern (404, „already exists“, 429, 5xx) nur den Rest mit Pause
erneut (``VERSUCHE``). Was fehlt, steht als ``fehlgeschlagen`` mit Fehlerzeile;
``ausgelassen`` heißt nur: Zeit abgelaufen.

Das Release wird je Tag einmal gesucht oder angelegt (``_sichere_release``; „existiert
schon“ heißt: ein anderer Lauf war schneller). Bei HTTP 404 liest die Ablage die ID
neu, legt ein fehlendes Release wieder an und lädt nach einem ID-Wechsel nach, was im
alten Release lag. Alles steht im Protokoll der Bilanz; ein Release löscht hier nie
etwas (nur ``raeume_auf``, nach Alter).
"""

from __future__ import annotations

import time
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Protocol

from .beleg_bilanz import Bilanz
from .beleg_gh import (
    ZEIT_JE_AUFRUF_S,
    Gh,
    GhFehler,
    ReleaseInfo,
    Runner,
    runner_mit_frist,
)
from .beleg_regeln import (
    MAX_ANHAENGE_JE_RELEASE,
    gross_tag,
    ist_abgelaufen,
    ist_gross_tag,
    release_abgelaufen,
    tages_tag,
    zerlege_dateiname,
)

__all__ = [
    "PAKET",
    "ZEIT_JE_AUFRUF_S",
    "Bild",
    "Gh",
    "GhFehler",
    "ReleaseInfo",
    "Releases",
    "Runner",
    "raeume_auf",
    "runner_mit_frist",
    "veroeffentliche",
]

PAKET = 40
"""Dateien je ``gh release upload``: klein genug, dass ein Fehler wenig kostet."""
VERSUCHE = 5
"""Hochladeversuche je Paket bei vorübergehenden Fehlern."""
PAUSE_S = 5.0
"""Pause vor Versuch n+1: ``PAUSE_S * n`` Sekunden, nur solange die Frist es zulässt."""
SCHON_DA = ("already exists", "already_exists", "HTTP 422")
"""Teile einer Meldung von ``gh release create``, wenn das Release schon besteht."""
VORUEBERGEHEND = ("HTTP 404", "already exists", "HTTP 429", "HTTP 50")
"""Teile einer ``GhFehler``-Meldung, die eine Wiederholung lohnen."""
Anhaenge = Mapping[str, Sequence[str]]
"""Tag eines Releases -> Dateinamen seiner Anhänge."""


class Releases(Protocol):
    """Was die Ablage von GitHub braucht (im Test durch eine Attrappe ersetzt)."""

    def anhaenge(self) -> dict[str, list[str]]:
        """Release-Tag -> Dateinamen."""
        ...

    def release_info(self, tag: str) -> ReleaseInfo | None:
        """ID des Releases zum Tag oder ``None``, wenn es keines gibt."""
        ...

    def release_anlegen(self, tag: str, titel: str) -> None:
        """Legt ein Pre-Release an."""
        ...

    def hochladen(self, tag: str, dateien: Sequence[Path]) -> None:
        """Lädt Dateien hoch (überschreibt gleiche Namen)."""
        ...

    def release_loeschen(self, tag: str) -> None:
        """Löscht Release samt Tag."""
        ...

    def asset_loeschen(self, tag: str, datei: str) -> None:
        """Löscht eine Datei eines Releases."""
        ...


@dataclass(frozen=True)
class Bild:
    """Ein Bild mit endgültigem Dateinamen; ``gross`` = große Änderung."""

    datei: Path
    gross: bool


def _freier_tag(
    belegt: dict[str, int], bauen: Callable[[date, int], str], tag: date
) -> str:
    teil = 1
    while belegt.get(bauen(tag, teil), 0) >= MAX_ANHAENGE_JE_RELEASE:
        teil += 1
    return bauen(tag, teil)


def ist_voruebergehend(fehler: GhFehler) -> bool:
    """Lohnt eine Wiederholung (Release noch nicht sichtbar, Wettlauf, Last)?"""
    return any(teil in str(fehler) for teil in VORUEBERGEHEND)


def _sichere_release(tag: str, gh: Releases, bilanz: Bilanz) -> bool:
    """Findet das Release zum Tag oder legt es an; nie löschen. Wirft ``GhFehler``.

    Gibt ``True`` zurück, wenn es nicht mehr das Release ist, das dieser Lauf zuvor
    gesehen hat (neue ID oder neu angelegt): was dort lag, ist weg."""
    alt = bilanz.release_ids.get(tag)
    info = gh.release_info(tag)
    if info is None:
        try:
            gh.release_anlegen(tag, f"Belege {tag.removeprefix('belege-')}")
        except GhFehler as fehler:
            if not any(teil in str(fehler) for teil in SCHON_DA):
                raise
            bilanz.protokoll.append(f"{tag}: Release schon angelegt (anderer Lauf)")
        info = gh.release_info(tag)
        if info is None:
            raise GhFehler(f"gh release create {tag}: Release danach nicht auffindbar")
        bilanz.protokoll.append(f"{tag}: Release angelegt, ID {info.id}")
    if info.entwurf:
        bilanz.protokoll.append(f"{tag}: Release {info.id} ist ein Entwurf")
    gewechselt = alt is not None and alt != info.id
    if gewechselt:
        bilanz.protokoll.append(f"{tag}: Release-ID gewechselt von {alt} auf {info.id}")
        bilanz.erneuert.add(tag)
    bilanz.release_ids[tag] = info.id
    return gewechselt


def _lade_paket(
    tag: str,
    paket: list[Bild],
    vorhanden: dict[str, list[str]],
    gh: Releases,
    bilanz: Bilanz,
    frist_ende: float | None,
    uhr: Callable[[], float],
    schlaf: Callable[[float], None],
) -> list[Bild]:
    """Lädt ein Paket, wiederholt den Rest, gibt das Angekommene zurück."""
    vorher = set(vorhanden.get(tag, []))
    offen = list(paket)
    fertig: list[Bild] = []
    letzter: GhFehler | None = None
    for versuch in range(1, VERSUCHE + 1):
        try:
            gh.hochladen(tag, [bild.datei for bild in offen])
            fertig.extend(offen)
            offen = []
            break
        except GhFehler as fehler:
            letzter = fehler
        if "HTTP 404" in str(letzter):
            bilanz.protokoll.append(
                f"{tag}: HTTP 404 beim Hochladen (Versuch {versuch}), "
                "Release-ID wird neu gelesen"
            )
            try:
                if _sichere_release(tag, gh, bilanz):
                    vorher, fertig, offen = set(), [], list(paket)
                    vorhanden[tag] = []
            except GhFehler as fehler:
                bilanz.protokoll.append(f"{tag}: Release nicht prüfbar: {fehler}")
        try:
            da = set(gh.anhaenge().get(tag, []))
        except GhFehler:
            da = set()
        angekommen = [b for b in offen if b.datei.name in da - vorher]
        fertig.extend(angekommen)
        offen = [b for b in offen if b not in angekommen]
        if not offen or versuch == VERSUCHE or not ist_voruebergehend(letzter):
            break
        pause = PAUSE_S * versuch
        if frist_ende is not None and uhr() + pause >= frist_ende:
            break
        schlaf(pause)
    if offen and letzter is not None:
        bilanz.fehler.append(
            f"{tag}: {len(offen)} von {len(paket)} Bildern fehlen: {letzter}"
        )
        bilanz.fehlgeschlagen += len(offen)
    vorhanden.setdefault(tag, []).extend(b.datei.name for b in fertig)
    return fertig


def _lade_pakete(
    tag: str,
    eintraege: list[Bild],
    vorhanden: dict[str, list[str]],
    gh: Releases,
    bilanz: Bilanz,
    frist_ende: float | None,
    uhr: Callable[[], float],
    schlaf: Callable[[float], None],
) -> list[Bild]:
    """Lädt paketweise, zählt in der Bilanz und gibt das Angekommene zurück."""
    angekommen: list[Bild] = []
    for start in range(0, len(eintraege), PAKET):
        paket = eintraege[start : start + PAKET]
        if frist_ende is not None and uhr() >= frist_ende:
            bilanz.ausgelassen += len(paket)
            continue
        fertig = _lade_paket(tag, paket, vorhanden, gh, bilanz, frist_ende, uhr, schlaf)
        angekommen.extend(fertig)
        if ist_gross_tag(tag):
            bilanz.gross += len(fertig)
        else:
            bilanz.hochgeladen += len(fertig)
    return angekommen


def _hole_verlorene_nach(
    tag: str,
    angekommen: list[Bild],
    vorhanden: dict[str, list[str]],
    gh: Releases,
    bilanz: Bilanz,
    frist_ende: float | None,
    uhr: Callable[[], float],
    schlaf: Callable[[float], None],
) -> None:
    """Wurde das Release mitten im Lauf ersetzt, fehlen frühere Bilder: noch einmal
    lesen, was wirklich liegt, und den Rest nachladen (ein Durchgang)."""
    try:
        da = set(gh.anhaenge().get(tag, []))
    except GhFehler as fehler:
        bilanz.protokoll.append(
            f"{tag}: Abgleich nach Release-Wechsel unlesbar: {fehler}"
        )
        return
    fehlend = [b for b in angekommen if b.datei.name not in da]
    if not fehlend:
        return
    bilanz.protokoll.append(
        f"{tag}: {len(fehlend)} Bilder lagen im ersetzten Release, werden erneut "
        "hochgeladen"
    )
    if ist_gross_tag(tag):
        bilanz.gross -= len(fehlend)
    else:
        bilanz.hochgeladen -= len(fehlend)
    vorhanden[tag] = sorted(da)
    _lade_pakete(tag, fehlend, vorhanden, gh, bilanz, frist_ende, uhr, schlaf)


def _lade_tag(
    tag: str,
    eintraege: list[Bild],
    vorhanden: dict[str, list[str]],
    gh: Releases,
    bilanz: Bilanz,
    frist_ende: float | None,
    uhr: Callable[[], float],
    schlaf: Callable[[float], None] = time.sleep,
) -> None:
    """Sucht oder legt das Release an und lädt die Bilder paketweise hoch."""
    if frist_ende is not None and uhr() >= frist_ende:
        bilanz.ausgelassen += len(eintraege)
        return
    try:
        _sichere_release(tag, gh, bilanz)
    except GhFehler as fehler:
        bilanz.fehler.append(f"{tag}: {fehler}")
        bilanz.fehlgeschlagen += len(eintraege)
        return
    vorhanden.setdefault(tag, [])
    angekommen = _lade_pakete(
        tag, eintraege, vorhanden, gh, bilanz, frist_ende, uhr, schlaf
    )
    if tag in bilanz.erneuert:
        _hole_verlorene_nach(
            tag, angekommen, vorhanden, gh, bilanz, frist_ende, uhr, schlaf
        )


def veroeffentliche(
    bilder: Sequence[Bild],
    heute: date,
    gh: Releases,
    frist_ende: float | None = None,
    uhr: Callable[[], float] = time.monotonic,
    schlaf: Callable[[float], None] = time.sleep,
) -> Bilanz:
    """Lädt hoch (Modulkopf). Kein Zugriff auf ``gh`` ohne Bilder."""
    bilanz = Bilanz()
    if not bilder:
        return bilanz
    try:
        vorhanden = {tag: list(dateien) for tag, dateien in gh.anhaenge().items()}
    except GhFehler as fehler:
        bilanz.fehler.append(f"Releases nicht lesbar: {fehler}")
        bilanz.fehlgeschlagen = len(bilder)
        return bilanz
    belegt = {tag: len(dateien) for tag, dateien in vorhanden.items()}
    je_tag: dict[str, list[Bild]] = {}
    einmalig = {b.datei.name: b for b in sorted(bilder, key=lambda b: b.datei.name)}
    bilanz.doppelt = sorted(
        n for n, z in Counter(b.datei.name for b in bilder).items() if z > 1
    )
    for bild in einmalig.values():
        ziele = [_freier_tag(belegt, tages_tag, heute)]
        if bild.gross:
            ziele.append(_freier_tag(belegt, gross_tag, heute))
        for tag in ziele:
            belegt[tag] = belegt.get(tag, 0) + 1
            je_tag.setdefault(tag, []).append(bild)
    for tag in sorted(je_tag):
        _lade_tag(tag, je_tag[tag], vorhanden, gh, bilanz, frist_ende, uhr, schlaf)
    return bilanz


def raeume_auf(
    anhaenge: Anhaenge, heute: date, gh: Releases
) -> tuple[Bilanz, dict[str, list[str]]]:
    """Löscht Abgelaufenes (Modulkopf); gibt Bilanz und verbleibende Anhänge zurück."""
    bilanz = Bilanz()
    rest: dict[str, list[str]] = {}
    for tag in sorted(anhaenge):
        if release_abgelaufen(tag, heute):
            try:
                gh.release_loeschen(tag)
                bilanz.releases_geloescht.append(tag)
            except GhFehler as fehler:
                bilanz.fehler.append(f"{tag} nicht gelöscht: {fehler}")
                rest[tag] = list(anhaenge[tag])
            continue
        rest[tag] = []
        for datei in anhaenge[tag]:
            name = zerlege_dateiname(datei)
            if name is None or not ist_abgelaufen(
                name.datum, heute, ist_gross_tag(tag)
            ):
                rest[tag].append(datei)
                continue
            try:
                gh.asset_loeschen(tag, datei)
                bilanz.assets_geloescht += 1
            except GhFehler as fehler:
                bilanz.fehler.append(f"{tag}/{datei} nicht gelöscht: {fehler}")
                rest[tag].append(datei)
    return bilanz, rest
