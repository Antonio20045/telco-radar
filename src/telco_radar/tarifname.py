"""Ein Tarifname ist kein Fehlertext.

08.11.2026: die o2-Schnittstelle lieferte im Namensfeld eine Java-Ausnahme samt URL
(`...&scheme=https: javax.net.ssl.SSLHandshakeException: ...`, später
`java.net.BindException`), der Sammler übernahm sie als Tarifnamen. Die Regel steht
hier, wo jedes Bündel und jede Referenz entsteht, nicht je Anbieter: ein Name, der wie
eine URL oder eine Ausnahme aussieht, macht den Satz ungültig (lieber ein Preis weniger
als ein falscher).
"""

from __future__ import annotations

import logging
import re

log = logging.getLogger(__name__)

_MUSTER = (
    ("URL", re.compile(r"https?://|\bwww\.", re.I)),
    ("Ausnahme", re.compile(r"exception|\bjavax?\.|traceback|stack ?trace", re.I)),
)


def tarifname_fehlergrund(name: object) -> str | None:
    """Warum ein Tarifname eine Fehlermeldung statt eines Namens ist; sonst `None`."""
    text = str(name or "")
    return next((grund for grund, muster in _MUSTER if muster.search(text)), None)


def pruefe_tarifname(name: str, leer_meldung: str) -> None:
    """`ValueError`, wenn der Name leer oder ein Fehlertext ist."""
    if not (name or "").strip():
        raise ValueError(leer_meldung)
    grund = tarifname_fehlergrund(name)
    if grund:
        raise ValueError(f"Tarifname ist ein Fehlertext ({grund}): {name[:80]!r}")


def ohne_fehlertext(saetze: dict) -> dict[str, int]:
    """Entfernt Bestandssätze mit Fehlertext als Namen aus `buendel` und `sim_only`.

    Gibt die Zahl je Anbieter zurück; jeder Satz steht mit Grund im Protokoll.
    """
    verworfen: dict[str, int] = {}
    for art in ("buendel", "sim_only"):
        behalten = []
        for satz in saetze.get(art) or []:
            grund = tarifname_fehlergrund(satz.get("tarif_name"))
            if grund is None:
                behalten.append(satz)
                continue
            anbieter = str(satz.get("anbieter") or "?")
            verworfen[anbieter] = verworfen.get(anbieter, 0) + 1
            log.info("Bestandssatz %s verworfen: Tarifname %s", satz.get("id"), grund)
        saetze[art] = behalten
    if verworfen:
        log.warning(
            "geraete_tco.json: %d Saetze mit Fehlertext als Tarifname beim Lesen "
            "verworfen (je Anbieter: %s)",
            sum(verworfen.values()),
            verworfen,
        )
    return verworfen
