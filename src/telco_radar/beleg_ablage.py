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

``frist_ende`` ist die monotone Zeit, bis zu der ein neues Paket beginnen darf
(CLAUDE.md Regel 8); der Rest heißt ``ausgelassen``. Außer ``gh`` gibt es kein Netz; das
Token liegt nur in der Umgebung (``GH_TOKEN``), nie in Argumenten oder Ausgaben.
"""

from __future__ import annotations

import json
import subprocess
import time
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Protocol

from .beleg_bilanz import Bilanz
from .beleg_regeln import (
    MAX_ANHAENGE_JE_RELEASE,
    REPO,
    datum_der_datei,
    gross_tag,
    ist_abgelaufen,
    ist_beleg_tag,
    ist_gross_tag,
    release_abgelaufen,
    tages_tag,
)

PAKET = 40
"""Dateien je ``gh release upload``: klein genug, dass ein Fehler wenig kostet."""
ZEIT_JE_AUFRUF_S = 300
VERSUCHE = 5
"""Hochladeversuche je Paket bei vorübergehenden Fehlern."""
PAUSE_S = 5.0
"""Pause vor Versuch n+1: ``PAUSE_S * n`` Sekunden, nur solange die Frist es zulässt."""
VORUEBERGEHEND = ("HTTP 404", "already exists", "HTTP 429", "HTTP 50")
"""Teile einer ``GhFehler``-Meldung, die eine Wiederholung lohnen."""
Runner = Callable[[Sequence[str]], "subprocess.CompletedProcess[str]"]
Anhaenge = Mapping[str, Sequence[str]]
"""Tag eines Releases -> Dateinamen seiner Anhänge."""


class GhFehler(RuntimeError):
    """Ein ``gh``-Aufruf ist gescheitert; die Meldung nennt nur den Befehl."""


class Releases(Protocol):
    """Was die Ablage von GitHub braucht (im Test durch eine Attrappe ersetzt)."""

    def anhaenge(self) -> dict[str, list[str]]:
        """Release-Tag -> Dateinamen."""
        ...

    def hochgeladen_am(self) -> dict[str, dict[str, str]]:
        """Release-Tag -> Dateiname -> Uploadzeit (ISO 8601)."""
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

    def _releases(self, feld: str, jq: str) -> dict[str, Any]:
        """Je Belege-Release das ``feld``, das ``jq`` aus dem Release bildet.

        Eine Zeile JSON je Release (``--paginate`` mit ``--jq``), damit seitenweises
        Lesen kein Listenende zerreißt; ``GhFehler`` bei Lese- und Formatfehlern."""
        argv = ["api", "--paginate", f"repos/{self._repo}/releases?per_page=100"]
        ausgabe = self._gh(*argv, "--jq", f".[] | {{tag: .tag_name, {feld}: {jq}}}")
        ergebnis: dict[str, Any] = {}
        for zeile in ausgabe.splitlines():
            if not zeile.strip():
                continue
            try:
                eintrag = json.loads(zeile)
                tag, wert = str(eintrag["tag"]), eintrag[feld]
            except (ValueError, KeyError, TypeError) as fehler:
                raise GhFehler(f"gh api: Antwort unlesbar: {fehler}") from fehler
            if ist_beleg_tag(tag):
                ergebnis[tag] = wert
        return ergebnis

    def anhaenge(self) -> dict[str, list[str]]:
        """Alle Releases im Schema mit ihren Anhängen; wirft ``GhFehler`` bei
        Lesefehlern."""
        roh = self._releases("dateien", "[.assets[].name]")
        try:
            return {
                tag: sorted(str(d) for d in dateien) for tag, dateien in roh.items()
            }
        except TypeError as fehler:
            raise GhFehler(f"gh api: Antwort unlesbar: {fehler}") from fehler

    def hochgeladen_am(self) -> dict[str, dict[str, str]]:
        """Uploadzeit jedes Anhangs der Belege-Releases (für ``beleg_veraltet``);
        wirft ``GhFehler`` bei Lesefehlern."""
        jq = "([.assets[] | {key: .name, value: .created_at}] | from_entries)"
        roh = self._releases("zeiten", jq)
        try:
            return {t: {str(k): str(v) for k, v in z.items()} for t, z in roh.items()}
        except (AttributeError, TypeError) as fehler:
            raise GhFehler(f"gh api: Antwort unlesbar: {fehler}") from fehler

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
    """Legt das Release an (falls nötig) und lädt die Bilder paketweise hoch."""
    if frist_ende is not None and uhr() >= frist_ende:
        bilanz.ausgelassen += len(eintraege)
        return
    if tag not in vorhanden:
        try:
            gh.release_anlegen(tag, f"Belege {tag.removeprefix('belege-')}")
        except GhFehler as fehler:
            bilanz.fehler.append(f"{tag}: {fehler}")
            bilanz.fehlgeschlagen += len(eintraege)
            return
        vorhanden[tag] = []
    for start in range(0, len(eintraege), PAKET):
        paket = eintraege[start : start + PAKET]
        if frist_ende is not None and uhr() >= frist_ende:
            bilanz.ausgelassen += len(paket)
            continue
        angekommen = len(
            _lade_paket(tag, paket, vorhanden, gh, bilanz, frist_ende, uhr, schlaf)
        )
        if ist_gross_tag(tag):
            bilanz.gross += angekommen
        else:
            bilanz.hochgeladen += angekommen


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
            datum = datum_der_datei(datei)
            if datum is None or not ist_abgelaufen(datum, heute, ist_gross_tag(tag)):
                rest[tag].append(datei)
                continue
            try:
                gh.asset_loeschen(tag, datei)
                bilanz.assets_geloescht += 1
            except GhFehler as fehler:
                bilanz.fehler.append(f"{tag}/{datei} nicht gelöscht: {fehler}")
                rest[tag].append(datei)
    return bilanz, rest
