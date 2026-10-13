"""Vorschaubilder der KI-Videos in die Site (Pitch 9, Schnitt 14).

Der Tageslauf legt die Bilder unter ``data/state/ki_videos/`` ab und nennt sie
im Store als ``bild``. Hier wird nur kopiert: nach ``ZIEL`` in der Site, was
fehlt, verliert sein ``bild`` (die Vorlage zeichnet dann ihr Standbild), was
kein Video mehr nennt, wird aus ``ZIEL`` entfernt. Nichts kommt aus dem Netz.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from ..analyze import ki_videos

ZIEL = Path("images") / "ki-videos"


def liefere_aus(state_dir: Path, site_dir: Path) -> dict:
    """Der Store mit ``bild`` nur für kopierte Bilder und ``bild_src`` dazu."""
    store = ki_videos.lade(state_dir)
    quelle = ki_videos.bildordner(state_dir)
    ziel = site_dir / ZIEL
    videos = []
    kopiert: set[str] = set()
    for video in store.get("videos") or []:
        name = video.get("bild")
        datei = quelle / name if name else None
        if datei is None or not datei.is_file():
            videos.append(dict(video, bild=None, bild_src=None))
            continue
        ziel.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(datei, ziel / name)
        kopiert.add(name)
        videos.append(dict(video, bild_src=(ZIEL / name).as_posix()))
    if ziel.is_dir():
        for alt in ziel.iterdir():
            if alt.is_file() and alt.name not in kopiert:
                alt.unlink()
    return dict(store, videos=videos)
