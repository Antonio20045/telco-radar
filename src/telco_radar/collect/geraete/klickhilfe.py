"""Ausnahmeweg des Klick-Tors: Hilfsdateien eines Hosts ohne lesbare robots.txt.

Antwortet robots.txt eines Hosts mit 401 oder 403 (``ROBOTS_VERWEIGERT``), gilt das
nach RFC 9309 als „keine Regeln“ (Entscheidung Antonio 07.10.2026). Von dort lässt das
Tor nur Skripte und Stylesheets hinaus (``HILFSDATEI_ARTEN``), und in den Browser kommt
nur eine Antwort, deren Content-Type JavaScript oder CSS nennt (``HILFSDATEI_TYPEN``),
auch nach einer Umleitung. Jede andere verwirft das Tor mit ``KEINE_HILFSDATEI``; sie
erreicht weder Lesung noch Mitschnitt noch Beleg. Dieses Modul ruft keinen Browser und
kein Netz.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from .klicklauf import Hilfsdatei, Klicklauf
from .robots import RobotsWaechter

if TYPE_CHECKING:
    from playwright.sync_api import APIResponse, Request

HILFSDATEI_ARTEN = frozenset({"script", "stylesheet"})
ROBOTS_VERWEIGERT = frozenset({401, 403})
HILFSDATEI_TYPEN = re.compile(
    r"(?:text|application)/(?:x-)?(?:java|ecma)script|text/css"
)
KEINE_HILFSDATEI = "Antwort ist keine Hilfsdatei"


class Ausnahmeweg:
    """Wer ohne Regeln hinaus darf (``darf``) und welche Antwort in den Browser darf.

    ``pruefe`` merkt jede Hilfsdatei, die in den Browser geht, in ``lauf.hilfsdateien``.
    """

    def __init__(self, waechter: RobotsWaechter, lauf: Klicklauf) -> None:
        self.waechter, self.lauf = waechter, lauf

    def darf(self, art: str, ziel: str) -> bool:
        """Skript oder Stylesheet eines Hosts, dessen robots.txt 401 oder 403 sagt."""
        verweigert = self.waechter.regeln(ziel).status in ROBOTS_VERWEIGERT
        return art in HILFSDATEI_ARTEN and verweigert

    def pruefe(self, ziel: str, anfrage: Request, antwort: APIResponse) -> str | None:
        """Grund, wenn ``ziel`` ohne Regeln kam und die Antwort keine Hilfsdatei ist.

        ``None`` für jede Antwort auf dem gewöhnlichen Weg und für eine Hilfsdatei; die
        Hilfsdatei steht danach mit dem Grund aus robots.txt in ``lauf.hilfsdateien``.
        """
        art = anfrage.resource_type
        if not self.darf(art, ziel):
            return None
        grund = keine_hilfsdatei(antwort.headers.get("content-type", ""))
        if grund is None:
            robots = self.waechter.regeln(ziel).fehler
            self.lauf.hilfsdateien.append(Hilfsdatei(ziel, art, robots, anfrage.url))
        return grund


def keine_hilfsdatei(typ: str) -> str | None:
    """Grund, wenn ``typ`` weder JavaScript noch CSS nennt, sonst ``None``."""
    medientyp = typ.split(";", 1)[0].strip().lower()
    if HILFSDATEI_TYPEN.fullmatch(medientyp):
        return None
    return f"{KEINE_HILFSDATEI} (Content-Type {medientyp or 'fehlt'})"
