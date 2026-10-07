"""Manifest der Belege: eine JSONL-Datei je Tag und Anbieter, mit Prüffunktion.

Datenkonzept Geräteradar, Abschnitt 10. Jede Zeile ist ein JSON-Objekt mit ``art`` und
``version``: ``beleg`` (Schema ``klickbeleg.Beleg``) oder ``stempel`` (Schema
``Stempelzeile``: SHA-256 über alle Bytes davor, ihre Zeilenzahl und die Stempel aus
``belegstempel``). Das Manifest liegt unter ``<wurzel>/<anbieter>/<JJJJ-MM-TT>.jsonl``,
die Dateien eines Belegs in der Ablage unter ``<anbieter>/<JJJJ-MM-TT>/<name>``; der
Tag ist der UTC-Tag des Belegs. ``haenge_an`` schreibt Zeilen ans Ende,
``lies_manifest`` liest sie zurück und wirft ``ManifestFehler`` mit Zeilennummer.
``pruefe_manifest`` nennt jede unvollständige Zeile, jede fehlende Datei, jeden Hash,
jede Größe und jede ``beleg_id``, die nicht zur Datei passt, jeden Cookie- oder
Zugangskopf im Mitschnitt und jeden Stempel, dessen Digest nicht zu den Zeilen davor
passt; eine Datei, die die Ablage nicht herausgibt oder deren Name kein gültiger
Ablageschlüssel ist, ist ein Befund ihrer Zeile, und die Prüfung geht weiter. Ein
ausgefallener Stempel ist ein gültiger Zustand, kein Befund. Dieses Modul ruft kein
Netz.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable, Iterable, Mapping
from dataclasses import asdict, dataclass, fields
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from ...textwerkzeug import slug
from .belegablage import ArchivFehler
from .belegstempel import Stempel
from .klickbeleg import BELEGFELDER, Beleg, Belegdatei, Fundstelle, beleg_id, sha256
from .klickhar import HarFehler, har_eintrag, zugangskoepfe
from .klickkarte import DIMENSIONEN

MANIFEST_VERSION = 1
ART_BELEG = "beleg"
ART_STEMPEL = "stempel"
ENDUNG = ".jsonl"
ZEITFORMAT = "%Y-%m-%dT%H:%M:%SZ"
_HEX64 = re.compile(r"[0-9a-f]{64}")
_DATEINAME = re.compile(r"[0-9a-f]{64}\.(?:webp|png|har)")
_TEXTFELDER = ("beleg_id", "anbieter", "zeitpunkt", "adresse", "seite", "antwort_url")


class ManifestFehler(ValueError):
    """Eine Manifestzeile ist nicht lesbar oder unvollständig."""

    def __init__(self, zeile: int, grund: str) -> None:
        super().__init__(f"Zeile {zeile}: {grund}")
        self.zeile = zeile
        self.grund = grund


@dataclass(frozen=True)
class Stempelzeile:
    """Die Stempel über alle Zeilen davor: ihr Digest, ihre Zahl, der Zeitpunkt."""

    digest: str
    zeilen: int
    zeitpunkt: str
    stempel: tuple[Stempel, ...]
    version: int = MANIFEST_VERSION


@dataclass(frozen=True)
class Manifest:
    """Belege und Stempelzeilen eines Manifests in Dateireihenfolge."""

    belege: tuple[Beleg, ...]
    stempel: tuple[Stempelzeile, ...]


def manifestpfad(wurzel: Path, anbieter: str, tag: date) -> Path:
    """Das Manifest eines Anbieters an einem Tag."""
    return wurzel / slug(anbieter) / f"{tag.isoformat()}{ENDUNG}"


def belegzeit(beleg: Beleg) -> datetime:
    """Der Zeitpunkt eines Belegs in UTC."""
    return datetime.strptime(beleg.zeitpunkt, ZEITFORMAT).replace(tzinfo=UTC)


def belegtag(beleg: Beleg) -> date:
    """Der UTC-Tag eines Belegs."""
    return belegzeit(beleg).date()


def ablageschluessel(beleg: Beleg, datei: Belegdatei) -> str:
    """Wo eine Datei des Belegs in der Ablage liegt."""
    return f"{slug(beleg.anbieter)}/{belegtag(beleg).isoformat()}/{datei.name}"


def haenge_an(pfad: Path, zeilen: Iterable[Beleg | Stempelzeile]) -> None:
    """Hängt Zeilen ans Manifest an; legt Ordner und Datei bei Bedarf an."""
    pfad.parent.mkdir(parents=True, exist_ok=True)
    with pfad.open("a", encoding="utf-8") as datei:
        for zeile in zeilen:
            art = ART_BELEG if isinstance(zeile, Beleg) else ART_STEMPEL
            daten = {"art": art, **asdict(zeile)}
            datei.write(json.dumps(daten, ensure_ascii=False) + "\n")


def stand(pfad: Path) -> tuple[str, int]:
    """SHA-256 über alle Bytes des Manifests und seine Zeilenzahl."""
    daten = pfad.read_bytes() if pfad.exists() else b""
    return hashlib.sha256(daten).hexdigest(), len(daten.splitlines())


def lies_manifest(pfad: Path) -> Manifest:
    """Belege und Stempelzeilen; eine unlesbare Zeile wirft ``ManifestFehler``."""
    belege, stempel = [], []
    for nummer, zeile in enumerate(pfad.read_bytes().splitlines(), start=1):
        daten = _json(nummer, zeile)
        if daten.get("art") == ART_BELEG:
            belege.append(_beleg(nummer, daten))
        else:
            stempel.append(_stempelzeile(nummer, daten))
    return Manifest(tuple(belege), tuple(stempel))


def pruefe_manifest(pfad: Path, lies_datei: Callable[[str], bytes | None]) -> list[str]:
    """Jeder Befund des Manifests; leer, wenn jede Zeile vollständig ist und passt.

    ``lies_datei`` holt eine Datei über ihren Ablageschlüssel, ``None`` heißt fehlt.
    """
    befunde: list[str] = []
    zeilen = pfad.read_bytes().splitlines(keepends=True)
    for nummer, zeile in enumerate(zeilen, start=1):
        try:
            daten = _json(nummer, zeile)
            if daten.get("art") == ART_BELEG:
                beleg = _beleg(nummer, daten)
                befunde += [f"Zeile {nummer}: {b}" for b in _pruefe(beleg, lies_datei)]
            else:
                kopf = _stempelzeile(nummer, daten)
                davor = b"".join(zeilen[: nummer - 1])
                if kopf.zeilen != nummer - 1:
                    befunde.append(
                        f"Zeile {nummer}: Stempel zählt {kopf.zeilen} Zeilen"
                    )
                if kopf.digest != hashlib.sha256(davor).hexdigest():
                    befunde.append(f"Zeile {nummer}: Stempel-Digest passt nicht")
        except ManifestFehler as fehler:
            befunde.append(str(fehler))
    return befunde


def _pruefe(beleg: Beleg, lies_datei: Callable[[str], bytes | None]) -> list[str]:
    befunde = _fundstellenbefunde(beleg)
    inhalt: dict[str, bytes] = {}
    for rolle, datei in (("Bild", beleg.bild), ("Mitschnitt", beleg.mitschnitt)):
        try:
            daten = lies_datei(ablageschluessel(beleg, datei))
        except (ValueError, ArchivFehler) as fehler:
            befunde.append(f"{rolle} {datei.name!r} nicht lesbar: {fehler}")
            continue
        if daten is None:
            befunde.append(f"{rolle} {datei.name} fehlt in der Ablage")
            continue
        inhalt[rolle] = daten
        if sha256(daten) != datei.sha256:
            befunde.append(f"{rolle} {datei.name}: SHA-256 passt nicht zur Datei")
        if len(daten) != datei.groesse:
            befunde.append(f"{rolle} {datei.name}: Größe passt nicht zur Datei")
    if len(inhalt) == 2 and beleg_id(inhalt["Bild"], inhalt["Mitschnitt"]) != (
        beleg.beleg_id
    ):
        befunde.append("beleg_id passt nicht zu den Dateien")
    if "Mitschnitt" in inhalt:
        befunde += _mitschnittbefunde(beleg, inhalt["Mitschnitt"])
    return befunde


def _mitschnittbefunde(beleg: Beleg, har: bytes) -> list[str]:
    try:
        url, status, _ = har_eintrag(har)
        verboten = zugangskoepfe(har)
    except HarFehler as fehler:
        return [f"Mitschnitt unlesbar: {fehler}"]
    befunde = [f"Mitschnitt trägt {v}" for v in verboten]
    if (url, status) != (beleg.antwort_url, beleg.antwort_status):
        befunde.append("Mitschnitt nennt eine andere Antwort als die Zeile")
    return befunde


def _fundstellenbefunde(beleg: Beleg) -> list[str]:
    befunde = []
    stellen = {s.feld: s for s in beleg.fundstellen}
    for feld, wert in beleg.werte.items():
        stelle = stellen.get(feld)
        if wert is None:
            if stelle is not None:
                befunde.append(f"Fundstelle für {feld} ohne Wert")
        elif stelle is None or not (
            stelle.selektor and stelle.ausschnitt and stelle.json_pfad
        ):
            befunde.append(f"Wert {feld} ohne vollständige Fundstelle")
    if not any(w is not None for w in beleg.werte.values()):
        befunde.append("Beleg ohne gelesenen Wert")
    return befunde


def _json(nummer: int, zeile: bytes) -> dict[str, Any]:
    try:
        daten = json.loads(zeile.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as fehler:
        raise ManifestFehler(nummer, "kein JSON") from fehler
    if not isinstance(daten, dict):
        raise ManifestFehler(nummer, "kein JSON-Objekt")
    if daten.get("art") not in (ART_BELEG, ART_STEMPEL):
        raise ManifestFehler(nummer, f"unbekannte Art {daten.get('art')!r}")
    bekannt = BELEGFELDER if daten["art"] == ART_BELEG else (MANIFEST_VERSION,)
    version = daten.get("version")
    if not isinstance(version, int) or version not in bekannt:
        raise ManifestFehler(nummer, f"unbekannte Version {daten.get('version')!r}")
    return daten


def _felder(nummer: int, daten: Mapping, art: Any) -> dict[str, Any]:
    erwartet = {f.name for f in fields(art)}
    roh = {k: v for k, v in daten.items() if k != "art"}
    fehlend, fremd = sorted(erwartet - set(roh)), sorted(set(roh) - erwartet)
    if fehlend:
        raise ManifestFehler(nummer, f"Feld fehlt: {', '.join(fehlend)}")
    if fremd:
        raise ManifestFehler(nummer, f"unbekanntes Feld: {', '.join(fremd)}")
    return roh


def _beleg(nummer: int, daten: Mapping) -> Beleg:
    roh = _felder(nummer, daten, Beleg)
    for name in _TEXTFELDER:
        if not isinstance(roh[name], str) or not roh[name].strip():
            raise ManifestFehler(nummer, f"Feld {name} ist leer")
    if not _HEX64.fullmatch(roh["beleg_id"]):
        raise ManifestFehler(nummer, "beleg_id ist kein SHA-256")
    try:
        datetime.strptime(roh["zeitpunkt"], ZEITFORMAT).replace(tzinfo=UTC)
    except ValueError as fehler:
        raise ManifestFehler(nummer, "zeitpunkt ist keine UTC-Zeit") from fehler
    felder = set(BELEGFELDER[roh["version"]])
    if not isinstance(roh["werte"], dict) or set(roh["werte"]) != felder:
        raise ManifestFehler(nummer, "werte nennt nicht genau die Wertfelder")
    if not isinstance(roh["variante"], dict) or set(roh["variante"]) != set(
        DIMENSIONEN
    ):
        raise ManifestFehler(nummer, "variante nennt nicht genau die Dimensionen")
    if not isinstance(roh["antwort_status"], int):
        raise ManifestFehler(nummer, "antwort_status ist keine Zahl")
    try:
        roh["fundstellen"] = tuple(Fundstelle(**f) for f in roh["fundstellen"])
        roh["bild"] = _datei(roh["bild"])
        roh["mitschnitt"] = _datei(roh["mitschnitt"])
    except (TypeError, ValueError) as fehler:
        grund = f"Datei oder Fundstelle unvollständig: {fehler}"
        raise ManifestFehler(nummer, grund) from fehler
    return Beleg(**roh)


def _datei(roh: Mapping) -> Belegdatei:
    datei = Belegdatei(**roh)
    if not _DATEINAME.fullmatch(str(datei.name)):
        raise ValueError(f"Dateiname {datei.name!r} ist nicht <beleg_id>.<Endung>")
    groesse = datei.groesse
    if not _HEX64.fullmatch(str(datei.sha256)) or not isinstance(groesse, int):
        raise ValueError(f"Datei {datei.name} ohne Hash oder Größe")
    if groesse < 0:
        raise ValueError(f"Datei {datei.name} mit negativer Größe")
    return datei


def _stempelzeile(nummer: int, daten: Mapping) -> Stempelzeile:
    roh = _felder(nummer, daten, Stempelzeile)
    try:
        roh["stempel"] = tuple(Stempel(**s) for s in roh["stempel"])
    except TypeError as fehler:
        raise ManifestFehler(nummer, f"Stempel unvollständig: {fehler}") from fehler
    if not _HEX64.fullmatch(str(roh["digest"])):
        raise ManifestFehler(nummer, "Stempel ohne Digest")
    return Stempelzeile(**roh)
