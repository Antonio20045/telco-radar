"""Was ein Lauf seinen Phasen leiht: Stoppuhr, Phasenprotokoll, Absicherung."""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

log = logging.getLogger(__name__)

Absicherung = Callable[[Callable[[], Any], Callable[[Exception], Any]], Any]


@dataclass(frozen=True)
class Takt:
    """Stoppuhr, Phasenprotokoll und Absicherung, die der Lauf den Phasen leiht."""

    stoppuhr: Callable[[], float]
    phase: Callable[[str, float, str], None]
    abgesichert: Absicherung


def protokoll(meldung: str, ersatz: Any) -> Callable[[Exception], Any]:
    """Ein Ausfall, der ``meldung`` protokolliert und ``ersatz`` liefert."""

    def _ausfall(exc: Exception) -> Any:
        log.error(meldung, exc)
        return ersatz

    return _ausfall
