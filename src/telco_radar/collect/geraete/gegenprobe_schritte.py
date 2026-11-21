"""Bausteine der Kundenwege, die mehrere Bündel auf einer Seite lesen.

Ein Weg (``gegenprobe_wege.Weg``) bekommt die Bündel eines Seitenbesuchs und gibt
nach jeder Wahl ein Bündel mit dem Text vorab zurück (``Schritte``); Adressen lädt er
nur über ``Oeffnen``, damit der Aufrufer robots.txt und den Abstand zum Host einhält.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Iterator
from datetime import datetime
from typing import TYPE_CHECKING

from ...gegenprobe import GRUND_ROBOTS
from .gegenprobe_browser import NichtPruefbar
from .robots import RobotsWaechter, host_von

if TYPE_CHECKING:
    from playwright.sync_api import Page

HOECHSTE_TARIFKACHELN = 8
WARTEN_MS = 8_000
"""So lange wartet ein Weg, bis die Seite eine Wahl sichtbar übernommen hat."""
TAKT_MS = 250

Oeffnen = Callable[["Page", str], None]
"""Lädt eine Adresse; der Aufrufer hält dabei robots.txt und den Abstand ein."""
Schritte = Iterator[tuple[dict, "str | NichtPruefbar"]]
"""Je gewähltes Bündel: der Text vorab (oft leer) oder warum es nicht wählbar war."""


def norm(text: str) -> str:
    """Nur Buchstaben und Ziffern, klein (Tarifnamen vergleichen)."""
    return "".join(z for z in text.lower() if z.isalnum())


def warte_bis(seite: Page, bedingung: Callable[[], bool]) -> bool:
    """Prüft ``bedingung`` alle ``TAKT_MS`` bis ``WARTEN_MS``; ob sie eintrat."""
    for _ in range(WARTEN_MS // TAKT_MS):
        if bedingung():
            return True
        seite.wait_for_timeout(TAKT_MS)
    return bedingung()


def nach_tarif(
    gruppe: list[dict], schluessel: Callable[[str], str]
) -> dict[str, list[dict]]:
    """Die Bündel einer Gruppe je Tarifname (``schluessel``); Farben desselben
    Speichers teilen eine Tarifauswahl und damit eine Lesung."""
    out: dict[str, list[dict]] = {}
    for b in gruppe:
        out.setdefault(schluessel(b.get("tarif_name") or ""), []).append(b)
    return out


def nicht_zur_wahl(offen: dict[str, list[dict]]) -> Schritte:
    """Die Bündel, deren Tarif der Besuch auf der Tarifauswahl nicht fand."""
    for liste in offen.values():
        for b in liste:
            grund = (
                f"Tarif {b.get('tarif_name')} steht auf der Tarifauswahl nicht zur Wahl"
            )
            yield b, NichtPruefbar(grund)


def tor(
    kennung: str, mindestabstand_s: float, jetzt: Callable[[], datetime]
) -> Callable[[str], None]:
    """Was vor jedem Laden einer Adresse gilt (``Oeffnen``): robots.txt, abgerufen mit
    ehrlicher ``kennung``, erlaubt die Adresse zur Zeit ``jetzt()`` (sonst
    ``NichtPruefbar``), und seit dem letzten Laden beim selben Host liegt der
    Crawl-delay oder ``mindestabstand_s``."""
    from .. import http

    def hole(url: str) -> tuple[int, str]:
        antwort = http.get(
            url, headers={"User-Agent": kennung}, timeout=20, follow_redirects=True
        )
        return antwort.status_code, antwort.text

    robots = RobotsWaechter(hole)
    zuletzt: dict[str, float] = {}

    def vor_laden(url: str) -> None:
        darf, grund = robots.darf(url, jetzt())
        if not darf:
            raise NichtPruefbar(f"{GRUND_ROBOTS}: {grund}")
        host = host_von(url)
        warte = zuletzt.get(host, 0.0) + robots.abstand(url, mindestabstand_s)
        time.sleep(max(0.0, warte - time.monotonic()))
        zuletzt[host] = time.monotonic()

    return vor_laden
