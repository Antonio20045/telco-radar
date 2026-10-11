"""Die Videos für ki.html (Pitch 9, Schnitt 14).

Der Store ``data/state/ki_videos.json`` hält ``stand``, höchstens ``HOECHSTENS``
Videos der letzten ``TAGE`` Tage (neueste zuerst), je Kanal ``error`` und
``error`` für den ganzen Abruf. Fällt der Abruf aus, bleibt der alte Stand;
fällt ein Kanal aus, bleiben seine Videos. Titel verlieren nur Werbe-Emoji.
Lesen ohne Netz, damit ``report/`` den Store laden darf.
"""

from __future__ import annotations

import json
import logging
import re
import unicodedata
from datetime import date, timedelta
from pathlib import Path

import yaml

log = logging.getLogger(__name__)

STORE_NAME = "ki_videos.json"
KATALOG = Path("config") / "ki_videos.yaml"
HOECHSTENS = 30
TAGE = 60
_UNSICHTBAR = {"️", "‍", "⃣"}


def kanaele(root: Path) -> list[dict]:
    """Die Kanäle von Hand; ohne Datei keiner."""
    pfad = Path(root) / KATALOG
    if not pfad.exists():
        return []
    return yaml.safe_load(pfad.read_text(encoding="utf-8")).get("kanaele") or []


def saeubere(titel: str) -> str:
    """Emoji und Bildzeichen raus, Leerraum zusammenziehen; Wortlaut bleibt."""
    zeichen = (
        z
        for z in titel
        if z not in _UNSICHTBAR
        and not (ord(z) >= 0x2190 and unicodedata.category(z) in ("So", "Sk"))
    )
    return re.sub(r"\s+", " ", "".join(zeichen)).strip()


def lade(state_dir: Path) -> dict:
    """Der Store; fehlt er, ist nichts abgerufen. Einziger Einstieg für report/."""
    pfad = Path(state_dir) / STORE_NAME
    leer: dict = {"stand": None, "videos": [], "kanaele": {}, "error": None}
    if not pfad.exists():
        return leer
    try:
        return json.loads(pfad.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        log.error("%s unlesbar: %s", pfad, exc)
        return dict(leer, error=f"{STORE_NAME} unlesbar")


def aktualisiere(
    state_dir: Path, katalog: list[dict], abruf: dict, heute: date
) -> dict:
    """Neue Videos zu den alten; ein Ausfall lässt den alten Stand stehen."""
    alt = lade(state_dir)
    tag = heute.isoformat()
    store = dict(alt, error=abruf.get("error"))
    if "kanaele" in abruf:
        je_name = {k["name"]: k for k in katalog}
        videos = {v["id"]: v for v in alt.get("videos") or []}
        kanal_stand = {}
        for name, ergebnis in abruf["kanaele"].items():
            vorher = (alt.get("kanaele") or {}).get(name) or {}
            gelesen = "error" not in ergebnis
            kanal_stand[name] = {
                "error": ergebnis.get("error"),
                "versucht": tag,
                "abgerufen": tag if gelesen else vorher.get("abgerufen"),
            }
            kanal = je_name.get(name, {})
            for v in ergebnis.get("videos") or []:
                videos[v["id"]] = {
                    "id": v["id"],
                    "titel": saeubere(v["titel"]),
                    "kanal": name,
                    "datum": v["datum"],
                    "dauer_sekunden": v["dauer_sekunden"],
                    "stufe": kanal.get("stufe"),
                    "sprache": kanal.get("sprache"),
                }
        grenze = (heute - timedelta(days=TAGE)).isoformat()
        frisch = [v for v in videos.values() if v["datum"] >= grenze]
        frisch.sort(key=lambda v: (v["datum"], v["id"]), reverse=True)
        store.update(stand=tag, videos=frisch[:HOECHSTENS], kanaele=kanal_stand)
    pfad = Path(state_dir) / STORE_NAME
    pfad.parent.mkdir(parents=True, exist_ok=True)
    pfad.write_text(json.dumps(store, ensure_ascii=False, indent=1), encoding="utf-8")
    return store
