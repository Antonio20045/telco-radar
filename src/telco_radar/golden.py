"""Goldener Lauf: Netz und LLM für ``pipeline.run`` aufnehmen und wiedergeben.

Eine Aufnahme liegt unter ``tests/fixtures/golden/<tag>/``: ``http.jsonl.gz`` je
Anfrage (Methode, Adresse, Kennung, Hash des Inhalts), ``llm.jsonl.gz`` je Stufe,
Modell und Hash aus Prompt und Aufnahmetag, die Konfiguration des Laufs unter
``config/`` und ``_herkunft.json`` mit Uhr und Umgebung. Die Wiedergabe meldet jede
fehlende Antwort mit dem Hinweis auf ``make golden-aufnehmen``.
"""

from __future__ import annotations

import base64
import gzip
import hashlib
import json
import os
import shutil
import sys
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import time_machine

from . import pipeline
from .analyze import llm
from .collect import http
from .naehte import PRODUKTION, LlmClient, Naehte

HINWEIS = "neu aufnehmen mit make golden-aufnehmen"
HERKUNFT = "_herkunft.json"
HTTP_DATEI = "http.jsonl.gz"
LLM_DATEI = "llm.jsonl.gz"
# Alles, was der Lauf aus der Umgebung liest. Die Wiedergabe setzt nur die
# Schlüssel, die bei der Aufnahme da waren, und zwar mit einem Ersatzwert.
UMGEBUNG = (
    "LLM_API_KEY",
    "LLM_API_BASE",
    "ANTHROPIC_API_KEY",
    "AWS_BEARER_TOKEN_BEDROCK",
    "BEDROCK_REGION",
    "BRAVE_API_KEY",
    "LLM_HTTP_TIMEOUT",
    "LLM_CALL_BUDGET",
    "TEAMS_WEBHOOK",
    "SMTP_HOST",
    "SMTP_PORT",
    "SMTP_USER",
    "SMTP_PASSWORD",
    "MAIL_FROM",
    "MAIL_TO",
    "GITHUB_OUTPUT",
    "PLAYWRIGHT_PROXY_SERVER",
)
SCHLUESSEL = ("LLM_API_KEY", "ANTHROPIC_API_KEY", "AWS_BEARER_TOKEN_BEDROCK")
ERSATZWERT = "golden-wiedergabe"
_FEHLER = {
    "AufnahmeFehlt": llm.LLMFatalError,
    "LLMModelUnavailable": llm.LLMModelUnavailable,
    "LLMFatalError": llm.LLMFatalError,
}


class AufnahmeFehlt(llm.LLMFatalError):
    """Die Wiedergabe kennt eine Anfrage nicht; der Lauf ist nicht mehr golden."""


@dataclass
class Band:
    """Antworten je Schlüssel in Aufnahmereihenfolge; die letzte wiederholt sich."""

    eintraege: dict[tuple[str, ...], list[dict]] = field(default_factory=dict)
    fehlend: list[str] = field(default_factory=list)
    _gelesen: dict[tuple[str, ...], int] = field(default_factory=dict)
    _sperre: threading.Lock = field(default_factory=threading.Lock)

    def merke(self, schluessel: tuple[str, ...], antwort: dict) -> None:
        """Hängt eine Antwort an; die Aufnahme ruft das je Anfrage."""
        with self._sperre:
            self.eintraege.setdefault(schluessel, []).append(antwort)

    def naechste(self, schluessel: tuple[str, ...], meldung: str) -> dict | None:
        """Nächste Antwort; fehlt sie, ``None`` und ein Eintrag in ``fehlend``."""
        with self._sperre:
            liste = self.eintraege.get(schluessel)
            if not liste:
                self.fehlend.append(f"{meldung} fehlt, {HINWEIS}")
                return None
            stelle = self._gelesen.get(schluessel, -1) + 1
            self._gelesen[schluessel] = min(stelle, len(liste) - 1)
            return liste[self._gelesen[schluessel]]


def stufe() -> str:
    """Das Modul, das ``llm.complete`` gerufen hat, etwa ``editor``."""
    rahmen = sys._getframe(1)
    while rahmen.f_back and rahmen.f_globals.get("__name__") in (
        __name__,
        llm.__name__,
    ):
        rahmen = rahmen.f_back
    return str(rahmen.f_globals.get("__name__", "?")).rsplit(".", 1)[-1]


@dataclass
class LlmBand:
    """LLM-Client, der ``innen`` aufnimmt oder ohne ``innen`` wiedergibt."""

    band: Band
    tag: str
    innen: LlmClient | None = None

    def __call__(self, system: str, user: str, modell: str, mx: int, vs: int) -> str:
        """Gleiche Signatur wie ``naehte.LlmClient``."""
        name = stufe()
        prompt = json.dumps([system, user, self.tag], ensure_ascii=False).encode()
        schluessel = (name, modell, hashlib.sha256(prompt).hexdigest())
        if self.innen is not None:
            try:
                text = self.innen(system, user, modell, mx, vs)
            except RuntimeError as exc:
                self.band.merke(schluessel, {"fehler": type(exc).__name__})
                raise
            self.band.merke(schluessel, {"antwort": text})
            return text
        eintrag = self.band.naechste(schluessel, f"LLM-Antwort für Stufe {name}")
        if eintrag is None:
            raise AufnahmeFehlt(self.band.fehlend[-1])
        if "fehler" in eintrag:
            raise _FEHLER.get(eintrag["fehler"], RuntimeError)("aufgenommen")
        return str(eintrag["antwort"])


def schreibe_band(pfad: Path, band: Band) -> None:
    """Sortiert und ohne Zeitstempel, damit dieselbe Aufnahme dieselben Bytes gibt."""
    zeilen = []
    for schluessel, liste in sorted(band.eintraege.items()):
        roh = [
            {
                k: base64.b64encode(v).decode() if k == "inhalt" else v
                for k, v in e.items()
            }
            for e in liste
        ]
        zeilen.append(json.dumps([schluessel, roh], ensure_ascii=False))
    pfad.write_bytes(gzip.compress("\n".join(zeilen).encode(), mtime=0))


def lies_band(pfad: Path) -> Band:
    """Gegenstück zu ``schreibe_band``."""
    band = Band()
    for zeile in gzip.decompress(pfad.read_bytes()).decode().splitlines():
        schluessel, liste = json.loads(zeile)
        for e in liste:
            if "inhalt" in e:
                e["inhalt"] = base64.b64decode(e["inhalt"])
        band.eintraege[tuple(schluessel)] = liste
    return band


def wurzel_bauen(ziel: Path, aufnahme: Path, bestand: Path) -> Path:
    """Arbeitsordner aus der Konfiguration der Aufnahme und dem Schnappschuss."""
    shutil.copytree(aufnahme / "config", ziel / "config")
    for teil in ("state", "reports"):
        shutil.copytree(bestand / teil, ziel / "data" / teil)
    return ziel


@contextmanager
def umgebung(vorhanden: list[str], wert: str = ERSATZWERT) -> Iterator[None]:
    """Die Umgebung der Aufnahme: nur ``vorhanden`` gesetzt, alles andere leer."""
    alt = {name: os.environ.pop(name, None) for name in UMGEBUNG}
    os.environ.update({name: alt[name] or wert for name in vorhanden})
    try:
        yield
    finally:
        for name, vorher in alt.items():
            os.environ.pop(name, None)
            if vorher is not None:
                os.environ[name] = vorher


def herkunft(aufnahme: Path) -> dict:
    """``_herkunft.json`` der Aufnahme: Uhr, Umgebung, Schnappschuss, Dateien."""
    return json.loads((aufnahme / HERKUNFT).read_text(encoding="utf-8"))


def wiedergabe(aufnahme: Path, guthaben_leer: bool = False) -> tuple[Naehte, Band]:
    """Nähte für einen Lauf aus der Aufnahme; das Band sammelt jede Lücke."""
    uhr = datetime.fromisoformat(herkunft(aufnahme)["zeit"])
    band = lies_band(aufnahme / HTTP_DATEI)
    llm_band = lies_band(aufnahme / LLM_DATEI)
    llm_band.fehlend = band.fehlend
    naehte = Naehte(
        transport=http.Wiedergabe(band, guthaben_leer),
        bilder=http.KEIN_BILD,
        llm_client=None if guthaben_leer else LlmBand(llm_band, uhr.date().isoformat()),
        uhr=lambda: uhr,
        stoppuhr=lambda: 0.0,
    )
    return naehte, band


def lauf(aufnahme: Path, wurzel: Path, guthaben_leer: bool = False) -> Band:
    """Ein Lauf von ``pipeline.run`` in ``wurzel`` ganz aus der Aufnahme."""
    naehte, band = wiedergabe(aufnahme, guthaben_leer)
    angaben = herkunft(aufnahme)
    uhr = datetime.fromisoformat(angaben["zeit"])
    try:
        with umgebung(angaben["umgebung"]), time_machine.travel(uhr, tick=False):
            pipeline.run(wurzel, use_llm=True, naehte=naehte)
    finally:
        PRODUKTION.setzen()
    return band


def seiten(wurzel: Path) -> dict[str, str]:
    """sha256 je Datei unter ``site/``; der goldene Lauf vergleicht genau das."""
    site = wurzel / "site"
    return {
        p.relative_to(site).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(site.rglob("*"))
        if p.is_file()
    }
