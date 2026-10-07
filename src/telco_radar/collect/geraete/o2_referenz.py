"""o2: die Referenz der Vertiefung - erster Durchlauf und Proben je Lauf.

DER BEFUND VOM 07.10.2026
-------------------------
`o2.vertiefe_buendel` misst die Referenz (Tarifanzeige -> Slug und
Anschlusspreis) einmal je Lauf am Tarifdurchlauf des ersten Geraets. Die
Tarifliste haengt aber am Geraet: am 29.09.2026 bot das iPhone 18 Pro sieben
Tarife ohne "Plus", das iPhone 17 Pro zwoelf. Eine Option, die die Referenz
nicht kannte, zaehlte `saetze_aus_konfiguration` als `ohne_referenz` und
verwarf sie - bei jedem weiteren Geraet. In `geraete_tco.json` vom
07.10.2026 fehlten so "O2 Mobile Unlimited L Plus mit 300 MBit/s" und
"O2 Mobile Special" bei allen 94 o2-Geraeten.

DIE PROBE
---------
Eine solche Option wird einmal je Lauf geprobt: ihr Link aus der Antwort,
ueber denselben gebremsten Abruf und nur, solange `weiter()` Zeit gibt.
Antwort und Probe sind ein Durchlauf desselben Geraets. Haelt er die Befunde
von `o2.referenz_aus` (gleiche Rate, gleiche Anzahlung, Slug da, Anzeigen
eindeutig) und nennt die Probe genau die Anzeige der Option, kommen seine
Anzeigen in die Referenz, fuer alle weiteren Geraete. Ein Eintrag, den die
Referenz schon traegt, wird nie ueberschrieben. Haelt die Probe nicht,
bleibt die Option `ohne_referenz`.
"""

from __future__ import annotations

import logging
from collections.abc import Callable

from .o2 import _gemessen, _hole_seite, _link, _ohne_markup, _zaehle, referenz_aus

log = logging.getLogger(__name__)

REFERENZ_TARIFE = "referenz_tarife"
PROBE_ABRUF = "referenz_probe"
PROBE_ERGAENZT = "referenz_ergaenzt"
PROBE_VERWORFEN = "probe_verworfen"
PROBE_FRIST = "probe_frist"


def erster_durchlauf(
    hole: Callable[[str], str],
    start: dict,
    weiter: Callable[[], bool],
    z: dict,
) -> dict | None:
    """Die Referenz aus dem Tarifdurchlauf des ersten Geraets - oder nichts.

    Je verlinktem Tarif der Startantwort ein Abruf; ohne Zeit ist der
    Durchlauf unvollstaendig, und `referenz_aus` liefert nichts.
    """
    durchlauf: list = [start]
    for option in (start.get("tariff") or {}).get("tariffOptions") or []:
        if option.get("selected") or not _link(option):
            continue
        if not weiter():
            durchlauf.append(None)
            break
        durchlauf.append(_hole_seite(hole, _link(option), z))
    referenz = referenz_aus(durchlauf)
    z[REFERENZ_TARIFE] = len(referenz or {})
    if referenz is None:
        log.warning(
            "o2-Vertiefung: der Referenzdurchlauf haelt die Befunde nicht "
            "(Rate/Anzahlung tarifabhaengig oder eine Probe faellt) - nur "
            "gemessene Saetze"
        )
    return referenz


def _probefaehig(option: dict, anzeige: str, anzeigen: list) -> bool:
    return bool(
        anzeige
        and not option.get("selected")
        and _link(option)
        and anzeigen.count(anzeige) == 1
    )


def ergaenze_referenz(
    hole: Callable[[str], str],
    referenz: dict | None,
    pv: dict,
    weiter: Callable[[], bool],
    geprobt: set,
    z: dict,
) -> None:
    """Probt die Optionen dieser Antwort, die die Referenz nicht kennt.

    Aendert `referenz` an Ort und Stelle; `geprobt` haelt die Anzeigen,
    die in diesem Lauf schon geprobt wurden, ob mit Erfolg oder nicht.
    Ohne Referenz (der erste Durchlauf hielt die Befunde nicht) wird nichts
    geprobt: dann gelten fuer den ganzen Lauf nur gemessene Saetze.
    """
    if referenz is None or _gemessen(pv) is None:
        return
    optionen = [
        o
        for o in (pv.get("tariff") or {}).get("tariffOptions") or []
        if isinstance(o, dict)
    ]
    anzeigen = [_ohne_markup(o.get("displayValue") or "") for o in optionen]
    for option, anzeige in zip(optionen, anzeigen, strict=True):
        if anzeige in referenz or anzeige in geprobt:
            continue
        if not _probefaehig(option, anzeige, anzeigen):
            continue
        if not weiter():
            _zaehle(z, PROBE_FRIST)
            return
        geprobt.add(anzeige)
        _zaehle(z, PROBE_ABRUF)
        neu = referenz_aus([pv, _hole_seite(hole, _link(option), z)])
        if neu is None or anzeige not in neu:
            _zaehle(z, PROBE_VERWORFEN)
            continue
        for name, eintrag in neu.items():
            if name not in referenz:
                referenz[name] = eintrag
                _zaehle(z, PROBE_ERGAENZT)
