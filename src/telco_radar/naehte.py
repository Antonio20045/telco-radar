"""Nähte von ``pipeline.run``: Netz, LLM-Client und Uhr von außen setzbar.

Im Betrieb gilt ``PRODUKTION``: echtes Netz, der Client aus ``analyze.llm`` und die
Wanduhr, die ``pipeline.run`` selbst liest. Der goldene Lauf setzt aufgezeichnete
Antworten und eine feste Uhr. ``setzen()`` schreibt alle Nähte bei jedem Lauf neu,
damit nichts aus einem vorigen Lauf hängen bleibt.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from .analyze import llm
from .collect import http
from .report import bilder

LlmClient = Callable[[str, str, str, int, int], str]
"""``(system, user, modell, max_tokens, versuche) -> Antworttext``."""


@dataclass(frozen=True)
class Naehte:
    """``transport`` trägt Quellen und LLM-Endpunkt, ``bilder`` den Bildabruf;
    ``uhr`` ersetzt die Wanduhr, ``stoppuhr`` ``time.monotonic`` für Laufzeiten."""

    transport: http.Transport | None = None
    bilder: http.Transport | None = None
    llm_client: LlmClient | None = None
    uhr: Callable[[], datetime] | None = None
    stoppuhr: Callable[[], float] | None = None

    def setzen(self) -> Callable[[], datetime] | None:
        """Setzt Netz und LLM-Client und gibt die Uhr zurück, ``None`` heißt Wanduhr."""
        http.TRANSPORT = self.transport
        llm.TRANSPORT = self.transport
        llm.CLIENT = self.llm_client
        bilder.TRANSPORT = self.bilder
        return self.uhr


PRODUKTION = Naehte()
