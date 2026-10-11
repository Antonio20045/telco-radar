"""Schleusen des Klick-Crawlers: Abstand je Host und Zeitgrenze je Seite.

``Hostschleuse`` hält je Host eine ``Abrufschleuse``: Crawl-delay aus robots.txt und
eigenes Rate-Limit, über einen ganzen Anbieterlauf. ``passiere_unterressource`` wartet
nur den Crawl-delay ab, nicht das eigene Rate-Limit: Skripte, Stylesheets und XHR einer
Seite lädt der Crawler wie ein Browser (Entscheidung Antonio 11.10.2026); das Tor
(``klicktor``) wählt den Weg nach der Art der Anfrage. ``Fristschleuse`` legt eine
Zeitgrenze darüber: nach ``ende`` geht keine Anfrage hinaus (``GRUND_FRIST``).
"""

from __future__ import annotations

import time
from collections.abc import Callable
from datetime import datetime
from typing import Protocol

from . import Abrufschleuse
from .basis import GeraeteAbrufFehler
from .robots import RobotsWaechter, host_von

GRUND_FRIST = "Zeitgrenze erreicht"


class Schleuse(Protocol):
    """Das robots-Tor vor einem Abruf; hält den Abstand je Host über Läufe hinweg."""

    def passiere(self, url: str) -> None:
        """Wartet den Abstand ab oder wirft ``GeraeteAbrufFehler``."""

    def passiere_ohne_regeln(self, url: str) -> None:
        """Wie ``passiere``, ohne robots.txt zu fragen: nur für eine Hilfsdatei."""

    def passiere_unterressource(self, url: str) -> None:
        """Wie ``passiere``, mit dem Crawl-delay, aber ohne eigenen Abstand."""

    def erledigt(self, url: str) -> None:
        """Merkt das Ende der Antwort; ab hier zählt der Abstand."""

    def abstand(self, url: str) -> float:
        """Der Abstand in Sekunden, den ``passiere`` für ``url`` höchstens wartet."""


class _Hostabruf(Abrufschleuse):
    """Eine ``Abrufschleuse``, deren Abstand ab dem Ende der letzten Antwort zählt."""

    def passiere_ohne_regeln(self, url: str) -> None:
        """Wartet den Abstand ab (``RobotsWaechter.abstand``), ohne ``darf``."""
        abstand = self._waechter.abstand(url, self._rate_limit)
        if self._letzter_abruf:
            time.sleep(max(0.0, abstand + self._letzter_abruf - time.monotonic()))
        self._letzter_abruf = time.monotonic()

    def erledigt(self) -> None:
        """Setzt den letzten Abruf auf jetzt, nach dem Ende der Antwort."""
        self._letzter_abruf = time.monotonic()


class Hostschleuse:
    """Je Host eine Abrufschleuse: Crawl-delay und Besuchszeit des Zielhosts.

    Eine Hostschleuse gilt für einen ganzen Anbieterlauf, damit der Abstand auch
    zwischen zwei Produktseiten desselben Hosts gilt; Hosts warten nicht aufeinander.
    """

    def __init__(
        self,
        waechter: RobotsWaechter,
        uhr: Callable[[], datetime],
        rate_limit_sekunden: float = 0.0,
    ) -> None:
        self._waechter, self._uhr = waechter, uhr
        self._rate_limit = rate_limit_sekunden
        self._je_host: dict[str, _Hostabruf] = {}

    def passiere(self, url: str) -> None:
        """Wartet den Abstand des Hosts von ``url`` ab; eine Sperre wirft."""
        self._fuer(url).passiere(url)

    def passiere_ohne_regeln(self, url: str) -> None:
        """Wartet den Abstand des Hosts von ``url`` ab, ohne robots.txt zu fragen."""
        self._fuer(url).passiere_ohne_regeln(url)

    def passiere_unterressource(self, url: str) -> None:
        """Wartet nur den Crawl-delay des Hosts ab, nicht das eigene Rate-Limit."""
        self._fuer(url).passiere(url, eigener_abstand=False)

    def erledigt(self, url: str) -> None:
        """Die Antwort von ``url`` ist da; der nächste Abruf wartet ab jetzt."""
        self._fuer(url).erledigt()

    def abstand(self, url: str) -> float:
        """Crawl-delay des Hosts oder eigenes Rate-Limit, der größere Wert."""
        return self._waechter.abstand(url, self._rate_limit)

    def _fuer(self, url: str) -> _Hostabruf:
        host = host_von(url)
        if host not in self._je_host:
            schleuse = _Hostabruf(self._waechter, self._uhr, self._rate_limit)
            self._je_host[host] = schleuse
        return self._je_host[host]


class Fristschleuse:
    """Eine Hostschleuse mit Zeitgrenze: nach ``ende`` geht keine Anfrage hinaus."""

    def __init__(self, innen: Hostschleuse, ende: float) -> None:
        self.innen, self.ende = innen, ende
        self.abgelaufen = False

    def setze(self, ende: float) -> None:
        """Neue Grenze für die nächste Seite."""
        self.ende, self.abgelaufen = ende, False

    def offen(self, url: str) -> bool:
        """Wahr, solange ein Abruf von ``url`` samt Abstand vor der Grenze hinausgeht.

        Dieselbe Grenze gilt für ``passiere`` und für den Klick-Crawler (``frist``).
        """
        return time.monotonic() + self.innen.abstand(url) < self.ende

    def passiere(self, url: str) -> None:
        """Wirft ``GeraeteAbrufFehler``, wenn der Abstand über die Grenze reicht."""
        self._pruefe_frist(url)
        self.innen.passiere(url)

    def passiere_ohne_regeln(self, url: str) -> None:
        """Wie ``passiere``, ohne robots.txt zu fragen: nur für eine Hilfsdatei."""
        self._pruefe_frist(url)
        self.innen.passiere_ohne_regeln(url)

    def passiere_unterressource(self, url: str) -> None:
        """Wie ``passiere``, ohne eigenen Abstand (``Hostschleuse``)."""
        self._pruefe_frist(url)
        self.innen.passiere_unterressource(url)

    def erledigt(self, url: str) -> None:
        """Die Antwort ist da; der Abstand zählt ab jetzt."""
        self.innen.erledigt(url)

    def abstand(self, url: str) -> float:
        """Crawl-delay oder eigener Abstand des Hosts."""
        return self.innen.abstand(url)

    def _pruefe_frist(self, url: str) -> None:
        if not self.offen(url):
            self.abgelaufen = True
            raise GeraeteAbrufFehler(f"{GRUND_FRIST}, nicht abgerufen")
