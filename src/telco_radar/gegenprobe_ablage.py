"""Bilder der Gegenprobe in GitHub-Releases: Name, Release, Hochladen, Aufräumen.

Ein Bild heißt nach seinem Inhalt (``dateiname``: erste 16 Zeichen der SHA-256): zwei
Bündel, deren Seite gleich aussah (Farben desselben Tarifs), teilen ein Bild, und ein
zweiter Lauf am selben Tag lädt nichts doppelt. Es liegt im Release
``gegenprobe-<datum>-<job>`` (``release_tag``; ``job`` aus
``gegenprobe_fenster.job_von``): die Anbieter-Jobs der Matrix laden parallel, jeder in
sein eigenes Release, keiner legt das Release eines anderen an. Ab
``beleg_regeln.MAX_ANHAENGE_JE_RELEASE`` Anhängen geht es in ``…-t2`` usw. weiter
(GitHub nimmt höchstens 1000). Das Release vom 21.11.2026 heißt noch
``gegenprobe-<datum>`` und gilt weiter.

Hochladen (``veroeffentliche``) läuft über ``beleg_ablage`` (Pakete, Wiederholung bei
vorübergehenden Fehlern) und bis ``frist_ende`` (Restzeit des Jobs, CLAUDE.md Regel 8).
Ein nicht hochgeladenes Bild steht als ``bild_fehlt`` mit Grund an der Zeile, nie als
leeres Feld.

Aufräumen (``plane``, ``raeume_auf``; Aufruf aus ``scripts/belege_manifest.py``):
gelöscht wird nur, was keine Seite mehr zeigt (``gegenprobe_belege.verlinkte``,
geschrieben in ``verlinkt.json``) und älter als ``gegenprobe_belege.MINDEST_TAGE`` ist;
ein Release ohne ein verlinktes Bild geht als Ganzes (ein Aufruf), sonst einzelne
Dateien, älteste zuerst. Die Liste dessen, was bleibt, steht im Belege-Manifest
(``liste``); die Seite zeigt ein älteres Bild nur, wenn es dort steht.
"""

from __future__ import annotations

import hashlib
import json
import re
import time
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from datetime import date
from functools import partial
from pathlib import Path

from . import gegenprobe as gp
from .beleg_ablage import Bild, Gh, GhFehler, Releases, _freier_tag, _lade_tag
from .beleg_bilanz import Bilanz
from .beleg_regeln import REPO
from .gegenprobe_fenster import job_von

PREFIX = gp.RELEASE_PREFIX
TEIL = "-t"
_TAG = re.compile(r"^gegenprobe-(\d{4}-\d{2}-\d{2})(?:-[a-z0-9-]+)?$")
_URL = re.compile(
    rf"^https://github\.com/{re.escape(REPO)}/releases/download/([^/]+)/([^/]+)$"
)
SCHLUESSEL = "gegenprobe"
"""Abschnitt im Belege-Manifest: ``{"stand": Tag der Liste, "anhaenge": {…}}``."""
GRUND_FRIST = "Bild nicht hochgeladen: Zeitbudget des Jobs erschöpft"
GRUND_RELEASES = "Bild nicht hochgeladen: Releases nicht lesbar"
GRUND_FEHLER = "Bild nicht hochgeladen"


def ist_gegenprobe_tag(tag: str) -> bool:
    """Gehört das Release zur Gegenprobe? Fremde fasst nichts an."""
    return bool(_TAG.match(tag or ""))


def datum_des_tags(tag: str) -> date | None:
    """Der Prüftag im Release-Namen; None außerhalb des Schemas."""
    treffer = _TAG.match(tag or "")
    if not treffer:
        return None
    try:
        return date.fromisoformat(treffer.group(1))
    except ValueError:
        return None


def release_tag(datum: str, job: str, teil: int = 1) -> str:
    """``gegenprobe-<datum>-<job>``, ab dem zweiten Teil mit ``-t<teil>``."""
    basis = f"{PREFIX}{datum}-{job}"
    return basis if teil <= 1 else f"{basis}{TEIL}{teil}"


def dateiname(bild: bytes) -> str:
    """Name aus dem Inhalt: gleiches Bild, gleicher Name."""
    endung = "webp" if bild[:4] == b"RIFF" else "png"
    return f"{hashlib.sha256(bild).hexdigest()[:16]}.{endung}"


def url(tag: str, datei: str) -> str:
    """Die öffentliche Adresse eines Anhangs."""
    return f"https://github.com/{REPO}/releases/download/{tag}/{datei}"


def zerlege(adresse: str) -> tuple[str, str] | None:
    """(Release, Datei) einer Bildadresse der Gegenprobe; sonst None."""
    treffer = _URL.match(adresse or "")
    if not treffer or not ist_gegenprobe_tag(treffer.group(1)):
        return None
    return treffer.group(1), treffer.group(2)


class GhGegenprobe(Gh):
    """``beleg_ablage.Gh`` für die Releases der Gegenprobe."""

    _schema = staticmethod(ist_gegenprobe_tag)


def _lokal(
    ergebnisse: Iterable[gp.Ergebnis], bilder: Mapping[str, bytes], ordner: Path
) -> dict[str, Path]:
    """Schreibt jedes Bild einmal nach ``ordner``; je Bündel die Datei."""
    ordner.mkdir(parents=True, exist_ok=True)
    dateien: dict[str, Path] = {}
    for e in ergebnisse:
        bild = bilder.get(e.buendel_id)
        if bild is None:
            continue
        datei = ordner / dateiname(bild)
        if not datei.exists():
            datei.write_bytes(bild)
        dateien[e.buendel_id] = datei
    return dateien


def _teil(datum: str, job: str, _tag: date, teil: int) -> str:
    """``release_tag`` in der Form, die ``beleg_ablage._freier_tag`` aufruft."""
    return release_tag(datum, job, teil)


def _ziele(
    dateien: dict[str, Path], datum: str, vorhanden: dict[str, list[str]]
) -> dict[str, str]:
    """Je Datei das Release: schon da (zweiter Lauf) oder der erste Teil des Jobs mit
    Platz (``_freier_tag``)."""
    belegt = {tag: len(namen) for tag, namen in vorhanden.items()}
    ziel: dict[str, str] = {}
    for bid, datei in sorted(dateien.items()):
        job = job_von(gp.anbieter_aus_id(bid))
        if datei.name in ziel:
            continue
        da = [
            t
            for t, namen in vorhanden.items()
            if t.startswith(release_tag(datum, job)) and datei.name in namen
        ]
        if da:
            ziel[datei.name] = da[0]
            continue
        tag = _freier_tag(belegt, partial(_teil, datum, job), date.min)
        belegt[tag] = belegt.get(tag, 0) + 1
        ziel[datei.name] = tag
    return ziel


def veroeffentliche(
    ergebnisse: list[gp.Ergebnis],
    bilder: Mapping[str, bytes],
    datum: str,
    ordner: Path,
    gh: Releases | None,
    frist_ende: float | None = None,
    uhr: Callable[[], float] = time.monotonic,
    schlaf: Callable[[float], None] = time.sleep,
) -> Bilanz:
    """Legt die Bilder ab und lädt sie hoch (Modulkopf); ``gh`` None: nur lokal.
    Setzt an jeder Zeile ``bild`` (angekommen) oder ``bild_fehlt`` (Grund)."""
    bilanz = Bilanz()
    dateien = _lokal(ergebnisse, bilder, ordner)
    if gh is None:
        for e in ergebnisse:
            if e.buendel_id in dateien:
                e.bild_fehlt = f"nicht veröffentlicht (lokal: {dateien[e.buendel_id]})"
        return bilanz
    try:
        vorhanden = {t: list(n) for t, n in gh.anhaenge().items()}
    except GhFehler as fehler:
        bilanz.fehler.append(f"Releases nicht lesbar: {fehler}")
        _vermerke(ergebnisse, dateien, {}, {}, GRUND_RELEASES)
        return bilanz
    ziel = _ziele(dateien, datum, vorhanden)
    neu: dict[str, list[Bild]] = {}
    for name, tag in sorted(ziel.items()):
        if name not in vorhanden.get(tag, []):
            neu.setdefault(tag, []).append(Bild(ordner / name, False))
    for tag, liste in sorted(neu.items()):
        if tag not in vorhanden and not (frist_ende and uhr() >= frist_ende):
            try:
                gh.release_anlegen(tag, f"Gegenprobe {tag.removeprefix(PREFIX)}")
                vorhanden[tag] = []
            except GhFehler as fehler:
                bilanz.fehler.append(f"{tag}: {fehler}")
        _lade_tag(tag, liste, vorhanden, gh, bilanz, frist_ende, uhr, schlaf)
    grund = GRUND_FRIST if bilanz.ausgelassen else GRUND_FEHLER
    if bilanz.fehler:
        grund = f"{GRUND_FEHLER}: {bilanz.fehler[-1][:160]}"
    _vermerke(ergebnisse, dateien, ziel, vorhanden, grund)
    return bilanz


def _vermerke(ergebnisse, dateien, ziel, vorhanden, grund: str) -> None:
    """``bild`` für angekommene, ``bild_fehlt`` mit Grund für alle anderen Bilder."""
    for e in ergebnisse:
        datei = dateien.get(e.buendel_id)
        if datei is None:
            continue
        tag = ziel.get(datei.name)
        if tag is not None and datei.name in vorhanden.get(tag, []):
            e.bild, e.bild_fehlt = url(tag, datei.name), None
        else:
            e.bild, e.bild_fehlt = None, grund


@dataclass(frozen=True)
class Plan:
    """Was ``raeume_auf`` löscht und was danach bleibt."""

    releases: list[str]
    dateien: list[tuple[str, str]]
    bleibt: dict[str, list[str]]


def plane(
    anhaenge: Mapping[str, Iterable[str]],
    verlinkt: set[str],
    heute: date,
    mindest_tage: int,
) -> Plan:
    """Nur nicht verlinkte Bilder aus Releases, die älter als ``mindest_tage`` sind;
    ein Release ohne verlinktes Bild ganz. Fremde Releases bleiben unberührt."""
    releases: list[str] = []
    dateien: list[tuple[str, str]] = []
    bleibt: dict[str, list[str]] = {}
    for tag in sorted(anhaenge, key=lambda t: (datum_des_tags(t) or date.max, t)):
        namen = sorted(anhaenge[tag])
        tag_datum = datum_des_tags(tag)
        if tag_datum is None or (heute - tag_datum).days < mindest_tage:
            bleibt[tag] = namen
            continue
        weg = [n for n in namen if url(tag, n) not in verlinkt]
        if len(weg) == len(namen):
            releases.append(tag)
            continue
        dateien += [(tag, n) for n in weg]
        bleibt[tag] = [n for n in namen if n not in weg]
    return Plan(releases, dateien, bleibt)


def raeume_auf(plan: Plan, gh: Releases, weiter: Callable[[], bool]) -> Bilanz:
    """Löscht nach ``plan``: Releases zuerst, dann Dateien, solange ``weiter()``."""
    bilanz = Bilanz()
    schritte = [(t, None) for t in plan.releases] + list(plan.dateien)
    for tag, datei in schritte:
        if not weiter():
            bilanz.ausgelassen += 1
            continue
        try:
            if datei is None:
                gh.release_loeschen(tag)
                bilanz.releases_geloescht.append(tag)
            else:
                gh.asset_loeschen(tag, datei)
                bilanz.assets_geloescht += 1
        except GhFehler as fehler:
            ort = tag if datei is None else f"{tag}/{datei}"
            bilanz.fehler.append(f"{ort} nicht gelöscht: {fehler}")
    return bilanz


@dataclass(frozen=True)
class Liste:
    """Die Anhänge der Gegenprobe-Releases am Tag ``stand`` (Belege-Manifest)."""

    stand: date
    urls: frozenset[str]

    def vorhanden(self, adresse: str, mindest_tage: int) -> bool:
        """Zeigt die Seite das Bild? Ja, wenn es in der Liste steht oder jünger ist,
        als je gelöscht wird (``mindest_tage`` vor ``stand``: nach der Liste
        hochgeladen). Eine Adresse außerhalb des Schemas zählt als vorhanden."""
        teile = zerlege(adresse)
        if teile is None or adresse in self.urls:
            return True
        tag_datum = datum_des_tags(teile[0])
        return tag_datum is not None and (self.stand - tag_datum).days < mindest_tage


def als_abschnitt(stand: date, bleibt: Mapping[str, Iterable[str]]) -> dict:
    """Der Abschnitt ``SCHLUESSEL`` für das Belege-Manifest."""
    return {
        "stand": stand.isoformat(),
        "anhaenge": {t: sorted(n) for t, n in sorted(bleibt.items())},
    }


def liste(manifest: Path) -> Liste | None:
    """Die Liste aus dem Belege-Manifest; None ohne Datei oder Abschnitt (dann gilt
    jedes Bild als vorhanden). ``ValueError`` bei einem kaputten Abschnitt."""
    if not manifest.is_file():
        return None
    daten = json.loads(manifest.read_text(encoding="utf-8")).get(SCHLUESSEL)
    if daten is None:
        return None
    try:
        urls = frozenset(
            url(tag, n) for tag, namen in daten["anhaenge"].items() for n in namen
        )
        return Liste(date.fromisoformat(daten["stand"]), urls)
    except (KeyError, TypeError, AttributeError) as fehler:
        raise ValueError(
            f"{manifest.name}: Abschnitt {SCHLUESSEL}: {fehler}"
        ) from fehler
