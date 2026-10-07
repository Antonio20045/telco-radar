"""Probenprotokoll der Stichprobe Mensch (Datenkonzept Geräte, Abschnitt 11).

Ein Mensch prüft Bündel gegen die Anbieterseite und schreibt je Probe eine Zeile JSONL::

    {"tag": "2026-10-07", "anbieter": "o2", "buendel": "<Bündel-ID>",
     "ergebnis": "ok", "beleg": "<Screenshot>", "notiz": "…"}

``ergebnis`` ist ``ok`` oder ``fehler``, ``beleg`` Pfad oder Adresse des Screenshots.
Eine ok-Probe ohne Beleg ist unlesbar; ein Fehler gilt auch ohne Beleg. Je Anbieter und
Tag zählt jedes Bündel einmal, ein Fehler an ihm gewinnt; ein Tag mit Fehler setzt die
Folge auf 0. Eine Probe, deren Bündel nicht im Bestand steht oder einem anderen Anbieter
gehört, ist nicht zuordenbar (``nicht_zuordenbar``); solange es eine solche Zeile oder
eine unlesbare gibt, wird die Stichprobe nicht grün.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date

log = logging.getLogger(__name__)

OK = "ok"
FEHLER = "fehler"
PROBEN_IN_FOLGE = 30
PFLICHTFELDER = ("tag", "anbieter", "buendel", "ergebnis")
FELD_BELEG = "beleg"


@dataclass(frozen=True)
class Probe:
    """Eine Zeile des Probenprotokolls; ``beleg`` ist None nur bei einem Fehler."""

    tag: str
    anbieter: str
    buendel: str
    ergebnis: str
    beleg: str | None


@dataclass(frozen=True)
class Probenprotokoll:
    """Die lesbaren Proben und die Zahl der unlesbaren Zeilen."""

    proben: tuple[Probe, ...]
    unlesbar: int = 0


@dataclass(frozen=True)
class Folge:
    """Fehlerfreie Proben seit dem letzten Tag mit Fehler, Fehler insgesamt."""

    fehlerfrei: int = 0
    fehler: int = 0


def lies_proben(text: str) -> Probenprotokoll:
    """Das Probenprotokoll aus JSONL; jede unlesbare Zeile steht im Log."""
    proben: list[Probe] = []
    unlesbar = 0
    for nummer, zeile in enumerate(text.splitlines(), start=1):
        if not zeile.strip():
            continue
        try:
            proben.append(_probe(json.loads(zeile)))
        except ValueError as exc:
            log.warning("Probenprotokoll Zeile %d unlesbar: %s", nummer, exc)
            unlesbar += 1
    return Probenprotokoll(tuple(proben), unlesbar)


def _probe(roh: object) -> Probe:
    if not isinstance(roh, Mapping):
        raise ValueError("Zeile ist keine Zuordnung")
    werte = {f: str(roh.get(f) or "").strip() for f in (*PFLICHTFELDER, FELD_BELEG)}
    fehlt = [f for f in PFLICHTFELDER if not werte[f]]
    if werte["ergebnis"] == OK and not werte[FELD_BELEG]:
        fehlt.append(FELD_BELEG)
    if fehlt:
        raise ValueError(f"es fehlt {', '.join(fehlt)}")
    if werte["ergebnis"] not in (OK, FEHLER):
        raise ValueError(f"Ergebnis {werte['ergebnis']!r} ist weder ok noch fehler")
    return Probe(
        date.fromisoformat(werte["tag"]).isoformat(),
        werte["anbieter"],
        werte["buendel"],
        werte["ergebnis"],
        werte[FELD_BELEG] if werte[FELD_BELEG] else None,
    )


def folgen(proben: Iterable[Probe]) -> dict[str, Folge]:
    """Je Anbieter die fehlerfreien Proben seit dem letzten Tag mit Fehler."""
    tage: dict[tuple[str, str], dict[str, str]] = {}
    for p in proben:
        je_buendel = tage.setdefault((p.anbieter, p.tag), {})
        if je_buendel.get(p.buendel) != FEHLER:
            je_buendel[p.buendel] = p.ergebnis
    folge: dict[str, Folge] = {}
    for (anbieter, _tag), ergebnisse in sorted(tage.items()):
        bisher = folge.get(anbieter, Folge())
        fehler = sum(e == FEHLER for e in ergebnisse.values())
        folge[anbieter] = (
            Folge(0, bisher.fehler + fehler)
            if fehler
            else Folge(bisher.fehlerfrei + len(ergebnisse), bisher.fehler)
        )
    return folge


def nicht_zuordenbar(
    proben: Iterable[Probe], anbieter_je_buendel: Mapping[str, str]
) -> list[Probe]:
    """Die Proben, deren Bündel nicht im Bestand steht oder einem anderen Anbieter
    gehört; ``anbieter_je_buendel`` ordnet jeder Bündel-ID ihren Anbieter zu."""
    return [p for p in proben if anbieter_je_buendel.get(p.buendel) != p.anbieter]
