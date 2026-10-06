"""Die Prüfstelle im Gerätelauf: Kontext aus den Stores, Status in jeden Bündelsatz.

``vermerke`` läuft im nächtlichen Gerätelauf nach dem Upsert der Bündel und vor
``TcoDB.save``, immer über den ganzen Bestand (Regel 5 und 12 brauchen ihn), und
schreibt ``Pruefergebnis.als_feld`` in das Feld ``pruefung`` jedes Bündelsatzes.
``TcoDB.buendel`` gibt die gespeicherten Sätze selbst zurück; ``save`` schreibt sie mit
diesem Feld.

Scheitert die Prüfung, steht in jedem Satz der Status ``unbekannt`` mit dem Fehler: das
Bündel fällt aus Sieger und Δ, die Quellen-Seite nennt den Ausfall, und der Messtag
bleibt gesichert.

Den Vortag (Regel 11) liest ``vortageswerte`` aus der Preishistorie: je Bündel die
letzte Messung vor seinem Abruf, damit ein Sprung erst nach dem zweiten Abruf zählt.
"""

from __future__ import annotations

import json
import logging
from collections import Counter
from collections.abc import Callable, Iterable, Mapping
from pathlib import Path

from ..collect.geraete.klicktext import volumen_aus_zeile
from ..geraete_model import Katalog
from ..tarif_bezug import Tarifbestand
from .geraete_pruefstatus import FELD_PRUEFUNG, UNBEKANNT, Kontext
from .geraete_regeln import pruefe_bestand, sim_only_tabelle
from .geraete_store import GeraeteDB
from .tco_store import TcoDB, id_aus_satz

log = logging.getLogger(__name__)

PRUEFFEHLER = (
    ArithmeticError,
    AttributeError,
    LookupError,
    OSError,
    TypeError,
    ValueError,
)
"""Was beim Lesen von Store, Listungen, Historie und Katalog scheitern kann."""


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
    frisch: Callable[[str, str], bool],
    geraet_aus_sku: Callable[[str, Katalog], tuple[str, int | None]],
    katalog: Katalog,
) -> Counter[str]:
    """Prüft den ganzen Bündelbestand und schreibt den Status in jeden Satz.

    ``frisch`` und ``geraet_aus_sku`` sind die Definitionen der Geräteseite
    (``report/geraete_tco_karten``); der Gerätelauf reicht sie herein. Gibt die Zahl
    der Bündel je Status zurück. Ein Fehler aus ``PRUEFFEHLER`` wird protokolliert und
    als Status ``unbekannt`` mit ``fehler`` in jeden Satz geschrieben.
    """
    saetze = tco.buendel()
    try:
        k = kontext(
            tco,
            db.eintraege(),
            bestand,
            heute,
            frisch=frisch,
            geraet_von=lambda sku: geraet_aus_sku(sku, katalog),
        )
        felder = {bid: e.als_feld() for bid, e in pruefe_bestand(saetze, k).items()}
    except PRUEFFEHLER as exc:
        log.error("Prüfstelle gescheitert: %s: %s", type(exc).__name__, exc)
        fehler = {"status": UNBEKANNT, "fehler": f"{type(exc).__name__}: {exc}"}
        felder = {str(s.get("id") or ""): dict(fehler) for s in saetze}
    for satz in saetze:
        satz[FELD_PRUEFUNG] = felder[str(satz.get("id") or "")]
    zahlen = Counter(str(f["status"]) for f in felder.values())
    log.info("Prüfstelle: %s", ", ".join(f"{n} {s}" for s, n in sorted(zahlen.items())))
    return zahlen
