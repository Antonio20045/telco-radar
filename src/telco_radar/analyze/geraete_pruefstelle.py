"""Die Prüfstelle im Gerätelauf: Kontext aus den Stores, Vermerk in jeden Bündelsatz.

``vermerke`` läuft im nächtlichen Gerätelauf nach dem Upsert der Bündel und vor
``TcoDB.save``, immer über den ganzen Bestand (Regel 5 und 12 brauchen ihn). In das Feld
``pruefung`` jedes Bündelsatzes schreibt sie den kurzen ``Vermerk`` (Status und Nummern
der verletzten Regeln), in ``TcoDB.pruefung`` die Kennzahlen des Laufs
(``geraete_pruefkennzahlen``) mit Lücken und „nicht prüfbar“ je Regel. ``TcoDB.buendel``
gibt die gespeicherten Sätze selbst zurück; ``save`` schreibt beides.

Kein Messtag scheitert an der Prüfstelle: sie läuft unter der ``Absicherung`` des
Gerätelaufs (``analyze.takt``). Scheitert sie, auch unerwartet, steht in jedem Satz
``unbekannt`` mit dem Fehler, die Kennzahlen nennen ihn, und der Lauf speichert weiter.

Den Vortag (Regel 11) liest ``vortageswerte`` aus der Preishistorie: je Bündel die
letzte Messung vor seinem Abruf, damit ein Sprung erst nach dem zweiten Abruf zählt.
"""

from __future__ import annotations

import json
import logging
from collections import Counter
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path

from ..collect.geraete.klicktext import volumen_aus_zeile
from ..geraete_model import Katalog
from ..tarif_bezug import Tarifbestand
from .geraete_pruefkennzahlen import kennzahlen
from .geraete_pruefstatus import (
    FELD_PRUEFUNG,
    UNBEKANNT,
    VERLETZT,
    Kontext,
    Pruefergebnis,
    fehlerfeld,
    vermerk,
)
from .geraete_regeln import pruefe_bestand, sim_only_tabelle
from .geraete_store import GeraeteDB
from .takt import Absicherung
from .tco_store import TcoDB, id_aus_satz

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Seite:
    """Die Definitionen der Geräteseite (``report/geraete_tco_karten``), die die Regeln
    teilen: ``frisch`` (Regel 16) und Gerät mit Speicher je SKU (Regeln 5 und 13)."""

    frisch: Callable[[str, str], bool]
    geraet_aus_sku: Callable[[str, Katalog], tuple[str, int | None]]
    katalog: Katalog


def vortageswerte(historie: Path, stand: Mapping[str, str]) -> dict[str, dict]:
    """Je Bündel-ID (``stand``: ID → Abrufdatum) die letzte Historienzeile davor.

    Eine fehlende Historie heißt: kein Vortag. Unlesbare Zeilen werden gezählt und
    protokolliert, die übrigen gelten.
    """
    if not historie.exists():
        return {}
    vortag: dict[str, dict] = {}
    unlesbar = 0
    for zeile in historie.read_text(encoding="utf-8").splitlines():
        if not zeile.strip():
            continue
        try:
            satz = json.loads(zeile)
        except json.JSONDecodeError:
            unlesbar += 1
            continue
        bid = id_aus_satz(satz) if isinstance(satz, dict) else None
        tag = str(satz.get("datum") or "") if bid else ""
        grenze = stand.get(bid or "")
        if not tag or not grenze or tag >= grenze:
            continue
        if bid and (bid not in vortag or tag > str(vortag[bid].get("datum"))):
            vortag[bid] = satz
    if unlesbar:
        log.warning("Prüfstelle: %d Zeilen der Historie unlesbar", unlesbar)
    return vortag


def kontext(
    tco: TcoDB,
    listungen: Iterable[Mapping],
    bestand: Tarifbestand,
    heute: str,
    *,
    frisch: Callable[[str, str], bool],
    geraet_von: Callable[[str], tuple[str, int | None]],
) -> Kontext:
    """Was die Regeln aus Store, Listungen und Tarifbestand brauchen."""
    uvp = {
        str(e["sku_id"]): float(e["uvp"])
        for e in listungen
        if e.get("sku_id") and e.get("uvp")
    }
    volumen = {
        tid: float(satz["datenvolumen_gb"])
        for tid, satz in bestand.je_id_aktuell.items()
        if satz.get("datenvolumen_gb") is not None
    }
    stand = {str(s.get("id")): str(s.get("abgerufen_am") or "") for s in tco.buendel()}
    return Kontext(
        heute=heute,
        frisch=frisch,
        geraet_von=geraet_von,
        volumen_im_namen=volumen_aus_zeile,
        sim_only=sim_only_tabelle(tco.referenzen()),
        uvp=uvp,
        volumen=volumen,
        vortag=vortageswerte(tco.historie_path, stand),
    )


def vermerke(
    tco: TcoDB,
    db: GeraeteDB,
    bestand: Tarifbestand,
    heute: str,
    seite: Seite,
    abgesichert: Absicherung,
) -> Counter[str]:
    """Prüft den ganzen Bündelbestand, vermerkt den Status und die Kennzahlen.

    ``seite`` trägt die Definitionen der Geräteseite, ``abgesichert`` die Absicherung
    des Gerätelaufs. Gibt die Zahl der Bündel je Status zurück.
    """
    saetze = tco.buendel()

    def _pruefen() -> dict[str, dict]:
        k = kontext(
            tco,
            db.eintraege(),
            bestand,
            heute,
            frisch=seite.frisch,
            geraet_von=lambda sku: seite.geraet_aus_sku(sku, seite.katalog),
        )
        ergebnisse = pruefe_bestand(saetze, k)
        _protokolliere(ergebnisse)
        return {bid: e.als_feld() for bid, e in ergebnisse.items()}

    def _gescheitert(exc: Exception) -> dict[str, dict]:
        log.error("Prüfstelle gescheitert: %s: %s", type(exc).__name__, exc)
        return {_id(s): fehlerfeld(exc) for s in saetze}

    felder = abgesichert(_pruefen, _gescheitert)
    abgesichert(
        lambda: _schreibe(saetze, felder),
        lambda exc: _schreibe(saetze, _gescheitert(exc)),
    )

    def _ohne_kennzahlen(exc: Exception) -> dict:
        log.error("Prüfstelle gescheitert an den Kennzahlen: %s", fehlerfeld(exc))
        return {"lauf": heute, "fehler": fehlerfeld(exc)["fehler"]}

    tco.pruefung = abgesichert(
        lambda: {"lauf": heute, **kennzahlen(saetze, felder)}, _ohne_kennzahlen
    )
    zahlen = Counter(str(f["status"]) for f in felder.values())
    log.info("Prüfstelle: %s", ", ".join(f"{n} {s}" for s, n in sorted(zahlen.items())))
    return zahlen


def _id(satz: Mapping) -> str:
    return str(satz.get("id") or "")


def _schreibe(saetze: list[dict], felder: Mapping[str, dict]) -> None:
    """Der Vermerk in jeden Satz; ein Satz ohne Feld ist an der Prüfung gescheitert."""
    ohne = {"status": UNBEKANNT, "fehler": "kein Prüfergebnis"}
    for satz in saetze:
        satz[FELD_PRUEFUNG] = vermerk(felder.get(_id(satz)) or ohne).als_text()


def _protokolliere(ergebnisse: Mapping[str, Pruefergebnis]) -> None:
    """Je verletzter Regel die Zahl der Bündel und ein Beispiel mit Satz."""
    beispiel: dict[int, tuple[str, str]] = {}
    zahl: Counter[int] = Counter()
    for bid, ergebnis in ergebnisse.items():
        for b in ergebnis.je(VERLETZT):
            zahl[b.regel] += 1
            beispiel.setdefault(b.regel, (bid, b.satz))
    for regel, n in sorted(zahl.items()):
        bid, satz = beispiel[regel]
        log.info(
            "Prüfstelle: Regel %d bei %d Bündeln, z. B. %s: %s", regel, n, bid, satz
        )
