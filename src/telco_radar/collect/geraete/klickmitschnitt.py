"""Mitschnitt des Klick-Crawlers: welche Anfragen die Seite stellt, welche offen sind.

``Mitschnitt`` hängt an den Ereignissen der Seite. Er merkt die Anfragen, die zum
Antwortmuster der Karte passen, und ihre Antworten; so gehört eine Antwort nur zu dem
Klick, nach dem ihre Anfrage hinausging, und eine Anfrage, die über die Frist offen
bleibt, ist als offen erkennbar. Daneben zählt er jede Anfrage der Seite und hält die
laufenden: Ruhe heißt keine laufende Anfrage und keine neue seit der letzten Lesung.
Dieses Modul ruft kein Netz.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from playwright.sync_api import Page, Request, Response


class Mitschnitt:
    """Anfragen der Seite: alle laufenden und die zum Antwortmuster mit Antworten."""

    def __init__(self, passt: Callable[[str], bool]) -> None:
        self._passt = passt
        self.anfragen: list[Request] = []
        self.offen: list[Request] = []
        self.antworten: list[Response] = []
        self.gestartet = 0
        self.laufend: list[Request] = []

    def binde(self, seite: Page) -> None:
        """Hängt den Mitschnitt an die Anfrage-Ereignisse der Seite."""
        seite.on("request", self.anfrage)
        seite.on("response", self.antwort)
        seite.on("requestfinished", self.fertig)
        seite.on("requestfailed", self.fertig)

    def anfrage(self, anfrage: Request) -> None:
        """Zählt jede Anfrage als laufend; eine passende ist offen."""
        self.gestartet += 1
        self.laufend.append(anfrage)
        if self._passt(anfrage.url):
            self.anfragen.append(anfrage)
            self.offen.append(anfrage)

    def antwort(self, antwort: Response) -> None:
        """Merkt eine passende Antwort; ihre Anfrage ist nicht mehr offen."""
        if self._passt(antwort.url):
            self.antworten.append(antwort)
            self._schliesse(antwort.request)

    def fertig(self, anfrage: Request) -> None:
        """Eine beendete oder abgebrochene Anfrage läuft nicht mehr, ist nicht offen."""
        self.laufend = [a for a in self.laufend if a is not anfrage]
        self._schliesse(anfrage)

    def stand(self) -> int:
        """Zahl der bisher gemerkten passenden Anfragen, die Marke vor einem Klick."""
        return len(self.anfragen)

    def ruhe(self) -> int | None:
        """Zahl aller gestellten Anfragen, wenn keine läuft; sonst ``None``."""
        return None if self.laufend else self.gestartet

    def fertig_seit(self, seit: int) -> bool:
        """Wahr, wenn seit der Marke eine Anfrage hinausging und keine offen ist."""
        neue = self.anfragen[seit:]
        return bool(neue) and not self.offen_seit(seit)

    def offen_seit(self, seit: int) -> bool:
        """Wahr, wenn eine passende Anfrage seit der Marke noch offen ist."""
        return any(_unter(a, self.offen) for a in self.anfragen[seit:])

    def letzte_seit(self, seit: int) -> Response | None:
        """Die letzte Antwort auf eine Anfrage seit der Marke, sonst ``None``."""
        eigene = self.antworten_seit(seit)
        return eigene[-1] if eigene else None

    def antworten_seit(self, seit: int) -> list[Response]:
        """Die Antworten auf Anfragen seit der Marke, in Reihenfolge."""
        neue = self.anfragen[seit:]
        return [a for a in self.antworten if _unter(a.request, neue)]

    def _schliesse(self, anfrage: Request) -> None:
        self.offen = [a for a in self.offen if a is not anfrage]


def _unter(anfrage: Request, anfragen: list[Request]) -> bool:
    return any(anfrage is a for a in anfragen)
