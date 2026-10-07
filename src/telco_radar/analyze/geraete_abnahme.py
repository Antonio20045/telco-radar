"""Abnahme der Geräteseite ohne Netz (Datenkonzept Geräte, Abschnitt 11, Schritt 9).

Ohne Netz und ohne Uhr; den Tag gibt der Aufrufer. ``stichprobe`` zieht je Anbieter und
Tag 10 bis 20 zählende Bündel über SHA-256 aus Tag, Anbieter und Bündel-ID: derselbe
Tag zieht dieselben Bündel, ein anderer Tag andere. ``stand`` rechnet die Prüfpunkte
aus Abschnitt 11, je Status ``gruen``, ``rot`` oder ``offen``, Zahl (oder None) und
Grund. Die Goldliste lädt und löst ``geraete_goldliste`` auf.

Zählend heißt, was die Notbremse der Seite zählen lässt (``satz_zaehlt``). Was nur mit
Netz, Ablage, Zugang oder einem Menschen prüfbar ist, bleibt ``offen`` mit Grund, nie
grün. Das Probenprotokoll der Stichprobe Mensch ist JSONL, eine Probe je Zeile::

    {"tag": "2026-10-07", "anbieter": "o2", "buendel": "<Bündel-ID>",
     "ergebnis": "ok", "beleg": "<Screenshot>", "notiz": "…"}

``ergebnis`` ist ``ok`` oder ``fehler``, ``beleg`` Pfad oder Adresse des Screenshots;
eine Zeile ohne Beleg zählt nicht. Je Anbieter und Tag zählt jedes Bündel einmal, ein
Fehler an ihm gewinnt; ein Tag mit Fehler setzt die Folge auf 0.
"""

from __future__ import annotations

import hashlib
import json
import logging
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date

from ..collect.geraete.klicklauf import BELEGT
from ..tco_model import laufzeit_segment
from .geraete_pruefstatus import (
    ERLAUBTE_RATENLAUFZEITEN,
    FELD_BELEG_VARIANTE,
    FELD_ECHO,
    FELD_PRUEFUNG,
    GUELTIG,
    lies_vermerk,
    satz_zaehlt,
)
from .tco_store import id_aus_satz

log = logging.getLogger(__name__)

GRUEN = "gruen"
ROT = "rot"
OFFEN = "offen"
STICHPROBE_MIN = 10
STICHPROBE_MAX = 20
PROBEN_IN_FOLGE = 30
BEISPIEL_PROTOKOLLE = "docs/abnahme/beispielseite-*.md"
OK = "ok"
FEHLER = "fehler"
FELD_BELEG_ID = "beleg_id"
FELD_BELEG_STATUS = "beleg_status"
PUNKT_BELEG = "Jede Zahl hat einen Beleg"
PUNKT_WOERTLICH = "Wörtlich im Beleg"
PUNKT_VARIANTE = "Variante stimmt"
PUNKT_LAUFZEIT = "Laufzeit getrennt"
PUNKT_STICHPROBE = "Stichprobe Mensch"
PUNKT_GEGENPROBE = "Gegenprobe"
PUNKT_BEISPIEL = "Beispielseite"
PUNKT_OPTIK = "Optik"
_PROBE_FELDER = ("tag", "anbieter", "buendel", "ergebnis", "beleg")


@dataclass(frozen=True)
class Probe:
    """Eine Zeile des Probenprotokolls."""

    tag: str
    anbieter: str
    buendel: str
    ergebnis: str
    beleg: str


@dataclass(frozen=True)
class Probenprotokoll:
    """Die lesbaren Proben und die Zahl der Zeilen, die nicht zählen."""

    proben: tuple[Probe, ...]
    unlesbar: int = 0


@dataclass(frozen=True)
class Folge:
    """Fehlerfreie Proben seit dem letzten Tag mit Fehler, Fehler insgesamt."""

    fehlerfrei: int = 0
    fehler: int = 0


@dataclass(frozen=True)
class Pruefpunkt:
    """Ein Prüfpunkt aus Abschnitt 11: Status, Zahl (oder None) und Grund."""

    name: str
    status: str
    zahl: int | None
    grund: str
    einheit: str = ""


def stichprobe(
    buendel: Iterable[Mapping], anbieter: str, tag: str, anzahl: int
) -> list[Mapping]:
    """Die ``anzahl`` zählenden Bündel des Anbieters, die das Los des Tages zieht.

    Das Los ist SHA-256 über Tag, Anbieter und Bündel-ID (``id_aus_satz``); gezählt
    wird am ``tag`` (abgelaufene Aktionen). Gibt es weniger, kommen alle.
    """
    if not STICHPROBE_MIN <= anzahl <= STICHPROBE_MAX:
        raise ValueError(
            f"Stichprobe von {anzahl}: erlaubt {STICHPROBE_MIN} bis {STICHPROBE_MAX}"
        )
    tag = date.fromisoformat(tag).isoformat()
    lose = []
    for satz in buendel:
        if satz.get("anbieter") != anbieter or not satz_zaehlt(satz, tag):
            continue
        schluessel = id_aus_satz(dict(satz))
        if schluessel is not None:
            los = hashlib.sha256(f"{tag}|{anbieter}|{schluessel}".encode()).hexdigest()
            lose.append((los, schluessel, satz))
    lose.sort(key=lambda t: (t[0], t[1]))
    return [satz for _, _, satz in lose[:anzahl]]


def lies_proben(text: str) -> Probenprotokoll:
    """Das Probenprotokoll aus JSONL; jede Zeile, die nicht zählt, steht im Log."""
    proben: list[Probe] = []
    unlesbar = 0
    for nummer, zeile in enumerate(text.splitlines(), start=1):
        if not zeile.strip():
            continue
        try:
            proben.append(_probe(json.loads(zeile)))
        except ValueError as exc:
            log.warning("Probenprotokoll Zeile %d zählt nicht: %s", nummer, exc)
            unlesbar += 1
    return Probenprotokoll(tuple(proben), unlesbar)


def _probe(roh: object) -> Probe:
    if not isinstance(roh, Mapping):
        raise ValueError("Zeile ist keine Zuordnung")
    werte = {f: str(roh.get(f) or "").strip() for f in _PROBE_FELDER}
    fehlt = [f for f, wert in werte.items() if not wert]
    if fehlt:
        raise ValueError(f"es fehlt {', '.join(fehlt)}")
    if werte["ergebnis"] not in (OK, FEHLER):
        raise ValueError(f"Ergebnis {werte['ergebnis']!r} ist weder ok noch fehler")
    werte["tag"] = date.fromisoformat(werte["tag"]).isoformat()
    return Probe(**werte)


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


def stand(
    buendel: Iterable[Mapping],
    tag: str,
    proben: Probenprotokoll | None = None,
    beispielprotokolle: Sequence[str] = (),
) -> list[Pruefpunkt]:
    """Die Prüfpunkte aus Abschnitt 11 in dessen Reihenfolge.

    ``tag`` ist der Tag des Bestands, ``proben`` das gelesene Probenprotokoll oder
    None, wenn es fehlt, ``beispielprotokolle`` die Namen der Protokolle der
    Beispielseite (``BEISPIEL_PROTOKOLLE``).
    """
    saetze = list(buendel)
    zaehlende = [s for s in saetze if satz_zaehlt(s, tag)]
    anbieter = {str(s.get("anbieter") or "") for s in saetze} - {""}
    gegenprobe = "kein Zugang zu TARIFFUXX, communicationAds oder Diffbot"
    optik = "pruefe_portal.py und Screenshots 1440 px und 390 px sieht ein Mensch an"
    return [
        _anteil(
            PUNKT_BELEG,
            sum(map(_belegt, zaehlende)),
            len(zaehlende),
            "mit beleg_id und Belegstatus belegt",
        ),
        _woertlich(zaehlende),
        _variante(zaehlende),
        _laufzeit(zaehlende),
        _stichprobe_mensch(anbieter, proben),
        Pruefpunkt(PUNKT_GEGENPROBE, OFFEN, None, gegenprobe),
        _beispielseite(beispielprotokolle),
        Pruefpunkt(PUNKT_OPTIK, OFFEN, None, optik),
    ]


def _anteil(name: str, treffer: int, von: int, was: str) -> Pruefpunkt:
    """Grün nur, wenn alle ``von`` treffen; ohne zählendes Bündel offen.

    Die Zahl ist der Anteil in ganzen Prozent, abgerundet: 100 heißt alle.
    """
    if not von:
        return Pruefpunkt(name, OFFEN, None, "kein zählendes Bündel im Bestand")
    status = GRUEN if treffer == von else ROT
    grund = f"{treffer} von {von} zählenden Bündeln {was}"
    return Pruefpunkt(name, status, 100 * treffer // von, grund, "%")


def _beleg_id(satz: Mapping) -> str:
    return str(satz.get(FELD_BELEG_ID) or "").strip()


def _belegt(satz: Mapping) -> bool:
    return bool(_beleg_id(satz)) and satz.get(FELD_BELEG_STATUS) == BELEGT


def _woertlich(zaehlende: list[Mapping]) -> Pruefpunkt:
    mit_id = sum(1 for s in zaehlende if _beleg_id(s))
    if not mit_id:
        grund = f"kein archivierter Beleg: 0 von {len(zaehlende)} zählenden Bündeln"
    else:
        grund = f"{mit_id} Bündel mit beleg_id; Neulesen braucht die Ablage"
    return Pruefpunkt(PUNKT_WOERTLICH, OFFEN, None, grund)


def _variante(zaehlende: list[Mapping]) -> Pruefpunkt:
    mit_echo = [s for s in zaehlende if isinstance(s.get(FELD_ECHO), Mapping)]
    if not mit_echo:
        grund = f"kein Echo im Bestand: 0 von {len(zaehlende)} zählenden Bündeln"
        return Pruefpunkt(PUNKT_VARIANTE, OFFEN, None, grund)
    stimmt = sum(
        1
        for s in mit_echo
        if isinstance(s.get(FELD_BELEG_VARIANTE), Mapping)
        and lies_vermerk(s.get(FELD_PRUEFUNG)).status == GUELTIG
    )
    was = "mit Echo, Beleglink der Variante und Prüfstatus gültig"
    return _anteil(PUNKT_VARIANTE, stimmt, len(zaehlende), was)


def _laufzeit(zaehlende: list[Mapping]) -> Pruefpunkt:
    """Aus den Daten: jedes zählende Bündel hat eine erlaubte Ratenlaufzeit, trägt sie
    in seiner ID, und keine ID steht zweimal. Rot, wenn eins fehlt; sonst offen, weil
    nur der Seitenbau zeigt, dass Sieger und Δ nie über Laufzeiten vergleichen."""
    ids = [id_aus_satz(dict(s)) for s in zaehlende]
    doppelt = {i for i, n in Counter(ids).items() if n > 1}
    getrennt = sum(
        1
        for s, i in zip(zaehlende, ids, strict=True)
        if i is not None
        and i not in doppelt
        and s.get("laufzeit_monate") in ERLAUBTE_RATENLAUFZEITEN
        and i.rsplit("--", 1)[-1] == laufzeit_segment(s.get("laufzeit_monate"))
    )
    was = "mit erlaubter Ratenlaufzeit in eindeutiger ID"
    punkt = _anteil(PUNKT_LAUFZEIT, getrennt, len(zaehlende), was)
    if punkt.status != GRUEN:
        return punkt
    grund = f"{punkt.grund}; die Vergleiche der Seite prüfen nur die Tests aus 5.5"
    return Pruefpunkt(PUNKT_LAUFZEIT, OFFEN, punkt.zahl, grund, "%")


def _stichprobe_mensch(
    anbieter: set[str], protokoll: Probenprotokoll | None
) -> Pruefpunkt:
    if protokoll is None:
        grund = f"kein Probenprotokoll: 0 von {PROBEN_IN_FOLGE} je Anbieter"
        return Pruefpunkt(PUNKT_STICHPROBE, OFFEN, 0, grund, "Proben")
    je = folgen(protokoll.proben)
    werte = {a: je.get(a, Folge()) for a in sorted(anbieter | set(je))}
    zahl = min((f.fehlerfrei for f in werte.values()), default=0)
    teile = ", ".join(f"{a} {f.fehlerfrei}" for a, f in werte.items())
    grund = f"in Folge fehlerfrei, Grenze {PROBEN_IN_FOLGE}: {teile or 'kein Anbieter'}"
    if protokoll.unlesbar:
        grund += f"; {protokoll.unlesbar} Zeilen zählen nicht"
    if any(f.fehler and f.fehlerfrei < PROBEN_IN_FOLGE for f in werte.values()):
        status = ROT
    elif werte and zahl >= PROBEN_IN_FOLGE and not protokoll.unlesbar:
        status = GRUEN
    else:
        status = OFFEN
    return Pruefpunkt(PUNKT_STICHPROBE, status, zahl, grund, "Proben")


def _beispielseite(protokolle: Sequence[str]) -> Pruefpunkt:
    if not protokolle:
        grund = f"kein Protokoll unter {BEISPIEL_PROTOKOLLE}"
    else:
        grund = f"Protokoll {max(protokolle)} liegt vor; ob jede Zeile stimmt, prüft"
        grund += " ein Mensch"
    return Pruefpunkt(PUNKT_BEISPIEL, OFFEN, None, grund)
