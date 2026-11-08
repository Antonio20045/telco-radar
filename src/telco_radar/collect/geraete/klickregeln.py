"""Die Regeln eines Anbieters aus seiner Klick-Karte (``ratenplan``, ``tarifslug``).

Der Rohsatz und der Bündelbau kennen nur den Anbieternamen des Satzes. Dieses Modul
sucht unter ``KARTENORDNER`` die Karten mit diesem ``anbieter`` und gibt ihre Regeln
zurück; der Code verzweigt nie nach dem Namen, sondern nach der ``art`` der Regel.

Fail-closed: Nennen zwei Karten desselben Anbieters verschiedene Regeln (auch: die eine
nennt eine, die andere keine), gilt keine, und das Protokoll sagt es. Eine kaputte Karte
des Anbieters wirft ``KlickkartenFehler``, sie wird nie übersprungen. Kein Netz.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from functools import cache
from pathlib import Path

import yaml

from .klickkarte import (
    Klickkarte,
    KlickkartenFehler,
    Ratenplanregel,
    Tarifslugregel,
    lade_klickkarte,
)

log = logging.getLogger(__name__)

NACHWEISFELD_RATENPLAN = "ratenplan"
KARTENORDNER = Path(__file__).resolve().parents[4] / "config" / "klickkarten"


@dataclass(frozen=True)
class Kartenregeln:
    """Die Regeln eines Anbieters; ``None`` heißt: keine (oder uneinige) Karte."""

    ratenplan: Ratenplanregel | None = None
    tarifslug: Tarifslugregel | None = None
    liest_ratenplan_nachweis: bool = False
    """Wahr, wenn eine Karte des Anbieters den Nachweis ``ratenplan`` liest
    (``antwort.pfade.ratenplan``): dann braucht sie auch die Regel dazu."""


def regeln(anbieter: object, ordner: Path | None = None) -> Kartenregeln:
    """Die Regeln der Karten, deren ``anbieter`` gleich ``anbieter`` ist."""
    name = str(anbieter or "").strip().casefold()
    if not name:
        return Kartenregeln()
    return _lade(str(ordner or KARTENORDNER), name)


@cache
def _lade(ordner: str, anbieter: str) -> Kartenregeln:
    karten = _karten_von(Path(ordner), anbieter)
    if not karten:
        return Kartenregeln()
    return Kartenregeln(
        ratenplan=_einig(anbieter, "ratenplan", [k.ratenplan for k in karten]),
        tarifslug=_einig(anbieter, "tarifslug", [k.tarifslug for k in karten]),
        liest_ratenplan_nachweis=any(
            NACHWEISFELD_RATENPLAN in q.pfade for k in karten for q in k.lesequellen
        ),
    )


def _karten_von(ordner: Path, anbieter: str) -> list[Klickkarte]:
    karten: list[Klickkarte] = []
    for pfad in sorted(ordner.glob("*.yaml")):
        try:
            kopf = yaml.safe_load(pfad.read_text(encoding="utf-8"))
        except yaml.YAMLError as fehler:
            raise KlickkartenFehler(str(pfad), "", "kein lesbares YAML") from fehler
        genannt = kopf.get("anbieter") if isinstance(kopf, dict) else None
        if str(genannt or "").strip().casefold() == anbieter:
            karten.append(lade_klickkarte(pfad))
    return karten


def _einig(anbieter: str, feld: str, werte: list):
    erste = werte[0]
    if all(w == erste for w in werte):
        return erste
    log.warning(
        "Klick-Karten %s: Feld %s uneinig (nicht in jeder Karte gleich), "
        "es gilt keine Regel",
        anbieter,
        feld,
    )
    return None
