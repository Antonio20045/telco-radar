"""Abnahme der Geräteseite ohne Netz (Datenkonzept Geräte, Abschnitt 11, Schritt 9).

Ohne Netz und ohne Uhr; den Tag gibt der Aufrufer. ``stichprobe`` zieht je Anbieter und
Tag 10 bis 20 zählende Bündel über SHA-256 aus Tag, Anbieter und Bündel-ID: derselbe
Tag zieht dieselben Bündel, ein anderer Tag andere. ``stand`` rechnet die Prüfpunkte
aus Abschnitt 11, je Status ``gruen``, ``rot`` oder ``offen``, Zahl (oder None) und
Grund. Die Goldliste lädt und löst ``geraete_goldliste`` auf, das Probenprotokoll der
Stichprobe Mensch liest ``geraete_proben``.

Zählend heißt, was die Notbremse der Seite zählen lässt (``satz_zaehlt``). Beleg und
Variante gelten für jede Bündelzeile, zählend oder nicht: auch eine Schätzung steht mit
Beträgen auf der Seite. Eine Zeile ist jeder Satz, aus dem ein ``Buendel`` wird; einen
anderen übergeht die Seite. Die Variante stimmt nur positiv geprüft: Echo ohne Befund
mit Werten gleich dem Datensatz (``ECHO_ZU_SATZ``) und ein Beleglink, der Ratenlaufzeit,
Tarif und Speicher nennt und Regel 13 besteht. Was nur mit Netz, Ablage, Zugang oder
einem Menschen prüfbar ist, bleibt ``offen`` mit Grund, nie grün.
"""

from __future__ import annotations

import hashlib
import logging
from collections import Counter
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date

from ..collect.geraete.klicklauf import BELEGT
from ..tco_model import Buendel, laufzeit_segment
from .geraete_proben import FEHLER as FEHLER
from .geraete_proben import OK as OK
from .geraete_proben import PROBEN_IN_FOLGE as PROBEN_IN_FOLGE
from .geraete_proben import Folge as Folge
from .geraete_proben import Probenprotokoll as Probenprotokoll
from .geraete_proben import folgen as folgen
from .geraete_proben import lies_proben as lies_proben
from .geraete_proben import nicht_zuordenbar
from .geraete_pruefstatus import (
    CENT,
    ERLAUBTE_RATENLAUFZEITEN,
    FELD_BELEG_VARIANTE,
    FELD_ECHO,
    Kontext,
    buendel_aus_satz,
    satz_zaehlt,
)
from .geraete_regeln import regel_9_echo, regel_13_beleglink
from .tco_store import id_aus_satz

log = logging.getLogger(__name__)

GRUEN = "gruen"
ROT = "rot"
OFFEN = "offen"
STICHPROBE_MIN = 10
STICHPROBE_MAX = 20
BEISPIEL_PROTOKOLLE = "docs/abnahme/beispielseite-*.md"
FELD_BELEG_ID = "beleg_id"
FELD_BELEG_STATUS = "beleg_status"
ECHO_ZU_SATZ = {
    "anzahlung": "geraet_zuzahlung",
    "rate": "geraet_monatsrate",
    "ratenzahl": "laufzeit_monate",
    "anschluss": "anschlusspreis",
}
"""Echo-Wert (``klicktext.Preiswerte``) und das Feld des Bündelsatzes, das ihn trägt."""
BELEGLINK_TEILE = ("laufzeit", "tarif", "speicher")
ZEILEN = ("Bündelzeilen", "keine Bündelzeile im Bestand")
ZAEHLENDE = ("zählenden Bündeln", "kein zählendes Bündel im Bestand")
PUNKT_BELEG = "Jede Zahl hat einen Beleg"
PUNKT_WOERTLICH = "Wörtlich im Beleg"
PUNKT_VARIANTE = "Variante stimmt"
PUNKT_LAUFZEIT = "Laufzeit getrennt"
PUNKT_STICHPROBE = "Stichprobe Mensch"
PUNKT_GEGENPROBE = "Gegenprobe"
PUNKT_BEISPIEL = "Beispielseite"
PUNKT_OPTIK = "Optik"

GeraetVon = Callable[[str], tuple[str, int | None]]
Zeile = tuple[Mapping, Buendel]


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


def stand(
    buendel: Iterable[Mapping],
    tag: str,
    proben: Probenprotokoll | None = None,
    beispielprotokolle: Sequence[str] = (),
    geraet_von: GeraetVon | None = None,
) -> list[Pruefpunkt]:
    """Die Prüfpunkte aus Abschnitt 11 in dessen Reihenfolge.

    ``tag`` ist der Tag des Bestands, ``proben`` das gelesene Probenprotokoll oder
    None, wenn es fehlt, ``beispielprotokolle`` die Namen der Protokolle der
    Beispielseite (``BEISPIEL_PROTOKOLLE``), ``geraet_von`` Gerät und Speicher einer
    SKU wie auf der Seite; ohne sie ist der Speicher im Beleglink nicht prüfbar.
    """
    saetze = list(buendel)
    zeilen, unlesbar = _zeilen(saetze)
    zaehlende = [s for s in saetze if satz_zaehlt(s, tag)]
    anbieter = {str(s.get("anbieter") or "") for s in saetze} - {""}
    gegenprobe = "kein Zugang zu TARIFFUXX, communicationAds oder Diffbot"
    optik = "pruefe_portal.py und Screenshots 1440 px und 390 px sieht ein Mensch an"
    belegt = sum(_belegt(s) for s, _ in zeilen)
    was = "mit beleg_id und Belegstatus belegt"
    beleg = _anteil(PUNKT_BELEG, belegt, len(zeilen), was, ZEILEN)
    if unlesbar:
        grund = f"{beleg.grund}; {unlesbar} Sätze unlesbar, nicht auf der Seite"
        beleg = Pruefpunkt(beleg.name, beleg.status, beleg.zahl, grund, beleg.einheit)
    return [
        beleg,
        _woertlich(zeilen),
        _variante(zeilen, Kontext(heute=tag, geraet_von=geraet_von)),
        _laufzeit(zaehlende),
        _stichprobe_mensch(anbieter, proben, _anbieter_je_buendel(saetze)),
        Pruefpunkt(PUNKT_GEGENPROBE, OFFEN, None, gegenprobe),
        _beispielseite(beispielprotokolle),
        Pruefpunkt(PUNKT_OPTIK, OFFEN, None, optik),
    ]


def _zeilen(saetze: list[Mapping]) -> tuple[list[Zeile], int]:
    """Jeder Satz, aus dem ein ``Buendel`` wird, und die Zahl der übrigen."""
    zeilen: list[Zeile] = []
    unlesbar = 0
    for satz in saetze:
        try:
            zeilen.append((satz, buendel_aus_satz(satz)))
        except (TypeError, ValueError) as exc:
            log.warning("Abnahme: Satz %s unlesbar: %s", satz.get("id", "?"), exc)
            unlesbar += 1
    return zeilen, unlesbar


def _anbieter_je_buendel(saetze: list[Mapping]) -> dict[str, str]:
    """Gespeicherte und heutige ID (``id_aus_satz``) jedes Satzes zu seinem Anbieter."""
    return {
        schluessel: str(s.get("anbieter") or "")
        for s in saetze
        for schluessel in (str(s.get("id") or ""), id_aus_satz(dict(s)))
        if schluessel
    }


def _anteil(
    name: str, treffer: int, von: int, was: str, menge: tuple[str, str]
) -> Pruefpunkt:
    """Grün nur, wenn alle ``von`` treffen; ohne einen offen.

    Die Zahl ist der Anteil in ganzen Prozent, abgerundet: 100 heißt alle.
    """
    if not von:
        return Pruefpunkt(name, OFFEN, None, menge[1])
    status = GRUEN if treffer == von else ROT
    grund = f"{treffer} von {von} {menge[0]} {was}"
    return Pruefpunkt(name, status, 100 * treffer // von, grund, "%")


def _beleg_id(satz: Mapping) -> str:
    return str(satz.get(FELD_BELEG_ID) or "").strip()


def _belegt(satz: Mapping) -> bool:
    return bool(_beleg_id(satz)) and satz.get(FELD_BELEG_STATUS) == BELEGT


def _woertlich(zeilen: list[Zeile]) -> Pruefpunkt:
    mit_id = sum(1 for s, _ in zeilen if _beleg_id(s))
    if not mit_id:
        grund = f"kein archivierter Beleg: 0 von {len(zeilen)} {ZEILEN[0]}"
    else:
        grund = f"{mit_id} Bündel mit beleg_id; Neulesen braucht die Ablage"
    return Pruefpunkt(PUNKT_WOERTLICH, OFFEN, None, grund)


def _variante(zeilen: list[Zeile], k: Kontext) -> Pruefpunkt:
    angaben = sum(
        1 for s, _ in zeilen if s.get(FELD_ECHO) or s.get(FELD_BELEG_VARIANTE)
    )
    if not angaben:
        grund = f"kein Echo und kein Beleglink: 0 von {len(zeilen)} {ZEILEN[0]}"
        return Pruefpunkt(PUNKT_VARIANTE, OFFEN, None, grund)
    if k.geraet_von is None:
        grund = "ohne Gerätekatalog ist der Speicher im Beleglink nicht prüfbar"
        return Pruefpunkt(PUNKT_VARIANTE, OFFEN, None, grund)
    stimmt = sum(_variante_geprueft(s, b, k) for s, b in zeilen)
    was = "mit Echo gleich Datensatz und Beleglink der Variante"
    return _anteil(PUNKT_VARIANTE, stimmt, len(zeilen), was, ZEILEN)


def _variante_geprueft(satz: Mapping, b: Buendel, k: Kontext) -> bool:
    """Positiv geprüft, nicht nur nicht verletzt: Regeln 9 und 13 bestanden, der
    Beleglink nennt alle ``BELEGLINK_TEILE``, der Katalog kennt den Speicher, und das
    Echo nennt Werte, die dem Datensatz gleichen."""
    beleg = satz.get(FELD_BELEG_VARIANTE)
    if not isinstance(beleg, Mapping) or k.geraet_von is None:
        return False
    return (
        all(beleg.get(teil) not in (None, "") for teil in BELEGLINK_TEILE)
        and k.geraet_von(b.sku_id)[1] is not None
        and _echo_gleich(satz)
        and regel_9_echo(satz, b, k) is None
        and regel_13_beleglink(satz, b, k) is None
    )


def _echo_gleich(satz: Mapping) -> bool:
    """Das Echo nennt mindestens einen Wert, und jeder gleicht dem Datensatz."""
    echo = satz.get(FELD_ECHO)
    werte = echo.get("werte") if isinstance(echo, Mapping) else None
    if not isinstance(werte, Mapping):
        return False
    paare = [(werte.get(e), satz.get(s)) for e, s in ECHO_ZU_SATZ.items()]
    genannt = any(e is not None for e, _ in paare)
    return genannt and all(_gleich(e, s) for e, s in paare)


def _gleich(echo: object, satz: object) -> bool:
    if echo is None or satz is None:
        return echo is satz
    if isinstance(echo, int | float) and isinstance(satz, int | float):
        return abs(echo - satz) <= CENT
    return echo == satz


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
    punkt = _anteil(PUNKT_LAUFZEIT, getrennt, len(zaehlende), was, ZAEHLENDE)
    if punkt.status != GRUEN:
        return punkt
    grund = f"{punkt.grund}; die Vergleiche der Seite prüfen nur die Tests aus 5.5"
    return Pruefpunkt(PUNKT_LAUFZEIT, OFFEN, punkt.zahl, grund, "%")


def _stichprobe_mensch(
    anbieter: set[str],
    protokoll: Probenprotokoll | None,
    anbieter_je_buendel: Mapping[str, str],
) -> Pruefpunkt:
    """Rot nach einem Fehler, bis wieder ``PROBEN_IN_FOLGE`` fehlerfrei folgen; grün
    erst, wenn jeder Anbieter sie hat und keine Zeile unlesbar oder nicht zuordenbar
    ist."""
    if protokoll is None:
        grund = f"kein Probenprotokoll: 0 von {PROBEN_IN_FOLGE} je Anbieter"
        return Pruefpunkt(PUNKT_STICHPROBE, OFFEN, 0, grund, "Proben")
    je = folgen(protokoll.proben)
    fremd = nicht_zuordenbar(protokoll.proben, anbieter_je_buendel)
    werte = {a: je.get(a, Folge()) for a in sorted(anbieter | set(je))}
    zahl = min((f.fehlerfrei for f in werte.values()), default=0)
    teile = ", ".join(f"{a} {f.fehlerfrei}" for a, f in werte.items())
    grund = f"in Folge fehlerfrei, Grenze {PROBEN_IN_FOLGE}: {teile or 'kein Anbieter'}"
    if protokoll.unlesbar:
        grund += f"; {protokoll.unlesbar} Zeilen unlesbar"
    if fremd:
        grund += f"; {len(fremd)} Proben ohne Bündel dieses Anbieters im Bestand"
        grund += f", etwa {fremd[0].anbieter} {fremd[0].buendel}"
    if any(f.fehler and f.fehlerfrei < PROBEN_IN_FOLGE for f in werte.values()):
        status = ROT
    elif werte and zahl >= PROBEN_IN_FOLGE and not protokoll.unlesbar and not fremd:
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
