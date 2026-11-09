"""Ein Bündelpreis, der zwischen Messtagen hin- und herspringt, ist widersprüchlich.

1&1 zeigt dieselbe Geräteseite verschiedenen Besuchern mit verschiedenen Preisen: ein
A/B-Test (``AB-Test_DOTASK-52022``, Varianten VTA und VTB, zugeteilt je Besuch) lässt
das iPhone 18 Pro mit All-Net-Flat S 49,99 € und 420 € Ablöse (VTA) oder 52,99 € und
460 € (VTB) kosten, mit Unlimited XL 74,99 €/420 € oder 77,99 €/460 €. Wer ohne Cookie
abruft, bekommt eine Variante nach Zufall; der Bestand wechselt deshalb von Tag zu Tag.

Beide Preise sind echt, keiner ist der Preis. Ein solcher Bündelpreis trägt keine
Aussage, die an eine Stufe gebunden wäre (``band_regel.unbegrenzt_ohne_beleg``). Erkannt
wird er am Verlauf: in den letzten ``FENSTER_MESSTAGE`` Messtagen der Historie kehrt der
Wert der Zeile mindestens ``MIN_RUECKSPRUENGE``-mal zu einem früheren, zwischenzeitlich
verlassenen Stand zurück (A, B, A). Ein Preiswechsel (A, dann B) oder zwei Preisanstiege
nacheinander (A, B, C) sind es nicht. Das Fenster zählt Messtage der Historie, nie das
heutige Datum.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from .. import tco_historie
from ..tco_model import buendel_id_aktuell

log = logging.getLogger(__name__)

FENSTER_MESSTAGE = 7
MIN_RUECKSPRUENGE = 1
MESSFELDER = (
    "buendel_monatlich",
    "tarif_monatlich",
    "geraet_monatsrate",
    "geraet_zuzahlung",
)


def rueckspruenge(staende: list) -> int:
    """Wie oft der Wert zu einem früheren Stand zurückkehrt, den er verlassen hatte."""
    gesehen: list = []
    zahl = 0
    for wert in staende:
        if gesehen and wert != gesehen[-1]:
            zahl += wert in gesehen
        if not gesehen or wert != gesehen[-1]:
            gesehen.append(wert)
    return zahl


def _wert(satz: dict) -> tuple:
    return tuple(
        None if satz.get(f) is None else round(float(satz[f]), 2) for f in MESSFELDER
    )


def _lies(pfad: Path, je_id: dict[str, dict[str, tuple]]) -> None:
    for zeile in pfad.read_text(encoding="utf-8").splitlines():
        if not zeile.strip():
            continue
        try:
            satz = json.loads(zeile)
        except json.JSONDecodeError:
            continue
        if not isinstance(satz, dict) or not satz.get("datum") or not satz.get("id"):
            continue
        if bid := buendel_id_aktuell(satz["id"], satz.get("laufzeit_monate")):
            je_id.setdefault(bid, {})[str(satz["datum"])] = _wert(satz)


def schwankende_buendel(
    altdatei: Path,
    fenster: int = FENSTER_MESSTAGE,
    min_rueckspruenge: int = MIN_RUECKSPRUENGE,
) -> frozenset[str] | None:
    """Die IDs der Bündel, deren Werte in den letzten ``fenster`` Messtagen springen.

    ``None`` heißt: die Historie fehlt oder ist unlesbar. Das ist keine leere Menge
    ("nichts schwankt"), sondern "nicht gelesen", und der Aufrufer behandelt es so."""
    dateien = tco_historie.dateien(altdatei)
    if not dateien:
        return None
    je_id: dict[str, dict[str, tuple]] = {}
    try:
        for pfad in reversed(dateien):
            _lies(pfad, je_id)
            if len({d for tage in je_id.values() for d in tage}) >= fenster:
                break
    except OSError as exc:
        log.warning("Historie unlesbar fuer die Schwankungspruefung: %s", exc)
        return None
    tage = sorted({d for t in je_id.values() for d in t})[-fenster:]
    return frozenset(
        bid
        for bid, werte in je_id.items()
        if rueckspruenge([werte[d] for d in tage if d in werte]) >= min_rueckspruenge
    )


def lage_mit_schwankung(tco_db) -> dict:
    """``TcoDB.historie_lage()`` plus ``schwankend`` (Liste der IDs, ``None`` wenn
    die Historie nicht gelesen wurde): die eine Auskunft für die Geräteseite."""
    schwankend = schwankende_buendel(tco_db.historie_path)
    return {
        **tco_db.historie_lage(),
        "schwankend": None if schwankend is None else sorted(schwankend),
    }
