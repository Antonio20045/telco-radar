"""Vorschaubilder der KI-Videos zum Selbstausliefern (Pitch 9, Schnitt 14).

Im Tageslauf holt ``hole`` je Video im Store das beste Vorschaubild aus
``snippet.thumbnails`` (``youtube_api.vorschau``) mit ehrlicher Kennung über
``http.fetch``, nur wenn die robots.txt von i.ytimg.com es erlaubt. Ein Bild in
4:3 mit schwarzen Balken wird auf 16:9 beschnitten, dann auf ``BREITE`` Pixel
verkleinert und als JPEG ``<video-id>.jpg`` abgelegt. Ein vorhandenes Bild wird
nicht neu geholt. Scheitert eins, heißt sein Feld ``None`` (protokolliert), die
Seite zeigt dann das gezeichnete Standbild. Der Browser lädt nie von YouTube.
"""

from __future__ import annotations

import io
import logging
import re
import time
from pathlib import Path

from . import http
from .geraete.robots import RobotsWaechter

log = logging.getLogger(__name__)

BREITE = 960
QUALITAET = 80
SEITENVERHAELTNIS = 16 / 9
_ID = re.compile(r"[A-Za-z0-9_-]{6,20}")


class VorschauFehler(ValueError):
    """Das Vorschaubild ist nicht abrufbar oder kein lesbares Bild."""


def dateiname(video_id: str) -> str | None:
    """``<id>.jpg``; eine ID mit fremden Zeichen bekommt keinen Namen."""
    return f"{video_id}.jpg" if _ID.fullmatch(video_id or "") else None


def verkleinere(daten: bytes) -> bytes:
    """Auf 16:9 beschneiden (Balken bei 4:3), auf ``BREITE`` verkleinern, JPEG."""
    from PIL import Image, UnidentifiedImageError

    try:
        with Image.open(io.BytesIO(daten)) as roh:
            bild = roh.convert("RGB")
    except (UnidentifiedImageError, OSError) as exc:
        raise VorschauFehler(f"kein lesbares Bild: {exc}") from exc
    breite, hoehe = bild.size
    soll = round(breite / SEITENVERHAELTNIS)
    if hoehe > soll:
        oben = (hoehe - soll) // 2
        bild = bild.crop((0, oben, breite, oben + soll))
    if bild.width > BREITE:
        bild = bild.resize(
            (BREITE, max(1, round(bild.height * BREITE / bild.width))),
            Image.LANCZOS,
        )
    aus = io.BytesIO()
    bild.save(aus, "JPEG", quality=QUALITAET, optimize=True, progressive=True)
    return aus.getvalue()


def hole(
    videos: list[dict], adressen: dict[str, str], ordner: Path, http_cfg: dict
) -> dict[str, str | None]:
    """Je Video-ID der Dateiname im ``ordner`` oder ``None``; wirft nicht."""
    cfg = {**http_cfg, "user_agent": http.BOT_UA}

    def _robots(url: str) -> tuple[int, str]:
        try:
            antwort = http.fetch(url, cfg, schnell=True)
        except http.StatusFehler as exc:
            return exc.response.status_code, ""
        return antwort.status_code, antwort.text

    waechter = RobotsWaechter(_robots)
    ergebnis: dict[str, str | None] = {}
    for video in videos:
        vid = video["id"]
        name = dateiname(vid)
        if name is None:
            log.warning("Vorschaubild %r: ungültige Video-ID", vid)
            ergebnis[vid] = None
            continue
        if (ordner / name).is_file():
            ergebnis[vid] = name
            continue
        url = adressen.get(vid)
        if not url:
            ergebnis[vid] = None
            continue
        try:
            daten = _lade(url, cfg, waechter)
            ordner.mkdir(parents=True, exist_ok=True)
            (ordner / name).write_bytes(verkleinere(daten))
            ergebnis[vid] = name
        except (VorschauFehler, http.HttpFehler, OSError) as exc:
            log.warning("Vorschaubild %s nicht geladen: %s", vid, exc)
            ergebnis[vid] = None
    return ergebnis


def _lade(url: str, cfg: dict, waechter: RobotsWaechter) -> bytes:
    regeln = waechter.regeln(url)
    if not regeln.abrufbar or not regeln.erlaubt(url) or regeln.fenster_text:
        grund = regeln.fehler or f"robots.txt sperrt {url} {regeln.fenster_text}"
        raise VorschauFehler(grund.strip())
    time.sleep(waechter.abstand(url))
    antwort = http.fetch(
        url, cfg, schnell=True, extra_headers={"Accept": "image/jpeg,image/*"}
    )
    return antwort.content


def raeume_auf(ordner: Path, behalten: set[str]) -> int:
    """Löscht im ``ordner`` jedes JPEG, das kein Video im Store mehr nennt."""
    if not ordner.is_dir():
        return 0
    weg = [b for b in ordner.glob("*.jpg") if b.name not in behalten]
    for bild in weg:
        bild.unlink()
    if weg:
        log.info("KI-Vorschaubilder aufgeräumt: %d entfernt", len(weg))
    return len(weg)
