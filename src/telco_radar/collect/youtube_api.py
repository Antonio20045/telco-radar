"""Neue Videos der KI-Kanäle über die YouTube Data API v3 (Pitch 9, Schnitt 14).

Je Kanal ein ``playlistItems.list`` auf die Uploads-Playlist, danach ein
``videos.list`` für die Dauer aller gefundenen Videos: zusammen etwa eine
Einheit je Kanal vom Tageskontingent (10.000). Der Schlüssel kommt nur aus der
Umgebung und geht nur im Kopf ``X-Goog-Api-Key`` mit, nie in Adresse,
Protokoll oder Fehlertext. Vorschaubilder werden nicht gelesen.
"""

from __future__ import annotations

import logging
import os
import re

from . import http

log = logging.getLogger(__name__)

API = "https://www.googleapis.com/youtube/v3"
UMGEBUNG = "YOUTUBE_API_KEY"
JE_KANAL = 5
OHNE_SCHLUESSEL = "YouTube-Schlüssel fehlt"
_GESAMT = {"quotaExceeded", "dailyLimitExceeded", "keyInvalid", "accessNotConfigured"}
_DAUER = re.compile(r"P(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?)?")


class YoutubeFehler(RuntimeError):
    """Die API hat abgelehnt; ``gesamt`` heißt: kein weiterer Kanal lohnt."""

    def __init__(self, grund: str, gesamt: bool) -> None:
        super().__init__(grund)
        self.gesamt = gesamt


def schluessel() -> str | None:
    """Der Schlüssel aus der Umgebung; fehlt er, ``None``."""
    return os.environ.get(UMGEBUNG) or None


def dauer_sekunden(iso: str) -> int | None:
    """ISO-8601 wie ``PT14M7S`` in Sekunden; ``P0D`` (live) und Unlesbares: ``None``."""
    treffer = _DAUER.fullmatch(iso or "")
    if not treffer:
        return None
    tage, stunden, minuten, sekunden = (int(t or 0) for t in treffer.groups())
    summe = ((tage * 24 + stunden) * 60 + minuten) * 60 + sekunden
    return summe if summe > 0 else None


def uploads(antwort: dict) -> list[dict]:
    """ID, Titel und Tag je Video; private und gelöschte (ohne Datum) fallen weg."""
    out = []
    for eintrag in antwort.get("items") or []:
        details = eintrag.get("contentDetails") or {}
        datum = details.get("videoPublishedAt")
        if details.get("videoId") and datum:
            titel = (eintrag.get("snippet") or {}).get("title") or ""
            out.append({"id": details["videoId"], "titel": titel, "datum": datum[:10]})
    return out


def dauern(antwort: dict) -> dict[str, int | None]:
    """Dauer je Video-ID; Live und Vorschau (``liveBroadcastContent``) fallen weg."""
    return {
        v["id"]: dauer_sekunden((v.get("contentDetails") or {}).get("duration", ""))
        for v in antwort.get("items") or []
        if (v.get("snippet") or {}).get("liveBroadcastContent", "none") == "none"
    }


def _grund(antwort: http.Antwort) -> tuple[str, bool]:
    try:
        fehler = antwort.json().get("error") or {}
    except ValueError:
        fehler = {}
    gruende = [e.get("reason") for e in fehler.get("errors") or []]
    gruende += [
        "keyInvalid"
        for d in fehler.get("details") or []
        if d.get("reason") in ("API_KEY_INVALID", "API_KEY_SERVICE_BLOCKED")
    ]
    gesamt = [g for g in gruende if g in _GESAMT]
    grund = (gesamt or gruende or ["ohne Grund"])[-1]
    return f"HTTP {antwort.status_code} {grund}", bool(gesamt)


def _hole(pfad: str, parameter: dict, kopf: dict, http_cfg: dict) -> dict:
    url = f"{API}/{pfad}"
    antwort = http.get(
        url,
        params=parameter,
        headers=kopf,
        timeout=float(http_cfg.get("timeout_seconds", 20)),
    )
    if antwort.status_code != 200:
        grund, gesamt = _grund(antwort)
        raise YoutubeFehler(f"YouTube {pfad}: {grund}", gesamt)
    return antwort.json()


def abrufen(kanaele: list[dict], http_cfg: dict, schluessel: str | None) -> dict:
    """``{"kanaele": {name: {"videos"|"error"}}}`` oder ``{"error"}`` für alle."""
    if not schluessel:
        return {"error": OHNE_SCHLUESSEL}
    kopf = {"User-Agent": http.BOT_UA, "X-Goog-Api-Key": schluessel}
    ergebnis: dict[str, dict] = {}
    try:
        for kanal in kanaele:
            teil = {"part": "snippet,contentDetails", "maxResults": JE_KANAL}
            teil["playlistId"] = kanal["uploads"]
            try:
                videos = uploads(_hole("playlistItems", teil, kopf, http_cfg))
                ergebnis[kanal["name"]] = {"videos": videos}
            except (YoutubeFehler, http.HttpFehler, ValueError) as exc:
                if getattr(exc, "gesamt", False):
                    raise
                log.warning("YouTube-Kanal %s nicht gelesen: %s", kanal["name"], exc)
                ergebnis[kanal["name"]] = {"error": _kurz(exc)}
        ids = [v["id"] for e in ergebnis.values() for v in e.get("videos", [])]
        dauer: dict[str, int | None] = {}
        for start in range(0, len(ids), 50):
            stapel = ",".join(ids[start : start + 50])
            teil = {"part": "contentDetails,snippet", "id": stapel}
            dauer.update(dauern(_hole("videos", teil, kopf, http_cfg)))
    except (YoutubeFehler, http.HttpFehler, ValueError) as exc:
        log.error("YouTube-Abruf abgebrochen: %s", exc)
        return {"error": _kurz(exc)}
    for eintrag in ergebnis.values():
        if "videos" in eintrag:
            eintrag["videos"] = [
                dict(v, dauer_sekunden=dauer[v["id"]])
                for v in eintrag["videos"]
                if v["id"] in dauer
            ]
    return {"kanaele": ergebnis}


def _kurz(exc: Exception) -> str:
    if isinstance(exc, YoutubeFehler):
        return str(exc).split(": ", 1)[-1]
    return f"{type(exc).__name__}: {str(exc)[:160]}"
