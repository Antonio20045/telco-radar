"""Die zwei Ranglisten der KI-Modelle (Pitch 9, Schnitt 6).

Artificial Analysis zeigt den Intelligence Index als HTML-Tabelle, eine Zeile je
Modell und Einstellung. Arena trägt die Text-Rangliste als ld+json
``ItemList`` mit Platz und Name. Beide robots.txt erlauben den Abruf; geprüft
wird bei jedem Lauf über ``RobotsWaechter``. Eine Besuchszeit in der robots.txt
gilt als gesperrt, weil der Lauf seine Uhrzeit hier nicht kennt.
"""

from __future__ import annotations

import json
import logging
import re
import time
from collections.abc import Callable
from html.parser import HTMLParser

from . import http
from .geraete.robots import RobotsWaechter

log = logging.getLogger(__name__)

AA_URL = "https://artificialanalysis.ai/leaderboards/models"
ARENA_URL = "https://arena.ai/leaderboard/text"
AA_SPALTE = "Artificial Analysis Intelligence Index"
_LDJSON = re.compile(
    r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>', re.S
)


class RanglisteUnlesbar(ValueError):
    """Die Seite kam an, trägt aber die erwartete Liste nicht."""


class _Tabelle(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.zeilen: list[list[str]] = []
        self._zeile: list[str] | None = None
        self._zelle: str | None = None

    def handle_starttag(self, tag, attrs) -> None:
        if tag == "tr":
            self._zeile = []
        elif tag in ("td", "th") and self._zeile is not None:
            self._zelle = ""

    def handle_endtag(self, tag) -> None:
        if tag in ("td", "th") and self._zelle is not None and self._zeile is not None:
            self._zeile.append(self._zelle.strip())
            self._zelle = None
        elif tag == "tr" and self._zeile is not None:
            self.zeilen.append(self._zeile)
            self._zeile = None

    def handle_data(self, data) -> None:
        if self._zelle is not None:
            self._zelle += data


def aa_index(html: str) -> list[dict]:
    """Je Tabellenzeile Name und Intelligence Index; Zeilen ohne Zahl fallen weg."""
    leser = _Tabelle()
    leser.feed(html)
    kopf = next((z for z in leser.zeilen if AA_SPALTE in z), None)
    if kopf is None:
        raise RanglisteUnlesbar(f"Spalte {AA_SPALTE!r} fehlt")
    spalte = kopf.index(AA_SPALTE)
    out = []
    for zeile in leser.zeilen[leser.zeilen.index(kopf) + 1 :]:
        wert = zeile[spalte] if len(zeile) > spalte else ""
        if zeile and re.fullmatch(r"\d+(\.\d+)?", wert):
            out.append({"name": zeile[0], "index": float(wert)})
    if not out:
        raise RanglisteUnlesbar("Tabelle ohne Modellzeile")
    return out


def arena_plaetze(html: str) -> list[dict]:
    """Platz und Name aus der ld+json-``ItemList`` der Seite."""
    for roh in _LDJSON.findall(html):
        daten = json.loads(roh)
        if isinstance(daten, dict) and daten.get("@type") == "ItemList":
            return [
                {"platz": int(e["position"]), "name": str(e["name"])}
                for e in daten.get("itemListElement") or []
            ]
    raise RanglisteUnlesbar("ld+json ItemList fehlt")


QUELLEN: dict[str, tuple[str, Callable[[str], list[dict]]]] = {
    "aa": (AA_URL, aa_index),
    "arena": (ARENA_URL, arena_plaetze),
}


def abrufen(http_cfg: dict) -> dict[str, dict]:
    """Beide Listen; je Quelle ``eintraege`` oder ``error``, nie beides."""
    cfg = {**http_cfg, "user_agent": http.BOT_UA}

    def _robots(url: str) -> tuple[int, str]:
        try:
            antwort = http.fetch(url, cfg, schnell=True)
        except http.StatusFehler as exc:
            return exc.response.status_code, ""
        return antwort.status_code, antwort.text

    waechter = RobotsWaechter(_robots)
    return {
        name: _eine(url, lesen, cfg, waechter) for name, (url, lesen) in QUELLEN.items()
    }


def _eine(url: str, lesen, cfg: dict, waechter: RobotsWaechter) -> dict:
    regeln = waechter.regeln(url)
    if not regeln.abrufbar or not regeln.erlaubt(url) or regeln.fenster_text:
        grund = regeln.fehler or f"robots.txt sperrt {url} {regeln.fenster_text}"
        return {"url": url, "error": grund.strip()}
    time.sleep(waechter.abstand(url))
    try:
        return {"url": url, "eintraege": lesen(http.fetch(url, cfg, schnell=True).text)}
    except (http.HttpFehler, ValueError) as exc:
        log.warning("KI-Rangliste %s nicht gelesen: %s", url, exc)
        return {"url": url, "error": f"{type(exc).__name__}: {str(exc)[:160]}"}
