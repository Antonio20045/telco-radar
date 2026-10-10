"""Die Ladegut-Fragmente der Geräteseite, je Modell eine Datei.

Bis 10.10.2026 holte app.js bei jedem Wechsel von Modell, Band oder
Laufzeit die Gesamtfragmente `geraete-zeitreihe.html` (47 MB) und
`geraete-buendel.html` (24 MB) und zerlegte sie im Browser: 7 s am
Rechner, 35 s mit Handy-CPU. Jetzt lädt der Client nur die Datei des
gewählten Modells aus `data/zr/` bzw. `data/bnd/`. Die Gesamtfragmente
bleiben für Wachstumsmessung und Prüfungen stehen.
"""

from __future__ import annotations

import shutil
from pathlib import Path

ZR_ORDNER = "zr"
BND_ORDNER = "bnd"


def _neu(ordner: Path) -> Path:
    if ordner.exists():
        shutil.rmtree(ordner)
    ordner.mkdir(parents=True)
    return ordner


def vorbereiten(site_dir: Path, env, geraete: dict) -> dict[Path, str]:
    """Leert `data/zr/` und `data/bnd/`, gibt jede Fragmentdatei mit Inhalt zurück."""
    tco = geraete.get("tco") or {}
    if not tco.get("modelle"):
        return {}
    daten = site_dir / "data"
    daten.mkdir(exist_ok=True)
    zr = geraete.get("zeitreihe") or {}
    vorgabe = (zr.get("start") or {}).get("modell") or tco["modell_vorgabe"]
    bnd_vorlage = env.get_template("geraete_buendel_fragment.html.j2")
    dateien = {
        daten / "geraete-buendel.html": bnd_vorlage.render(
            modelle=tco["modelle"], vorgabe=vorgabe
        )
    }
    bnd = _neu(daten / BND_ORDNER)
    for m in tco["modelle"]:
        dateien[bnd / f"{m['id']}.html"] = bnd_vorlage.render(
            modelle=[m], vorgabe=vorgabe
        )
    paare = zr.get("paare")
    if not paare:
        return dateien
    zr_vorlage = env.get_template("geraete_zeitreihe_fragment.html.j2")
    dateien[daten / "geraete-zeitreihe.html"] = zr_vorlage.render(paare=paare)
    je_modell: dict[str, list] = {}
    for p in paare:
        je_modell.setdefault(p["modell"], []).append(p)
    ziel = _neu(daten / ZR_ORDNER)
    for modell, eigene in je_modell.items():
        dateien[ziel / f"{modell}.html"] = zr_vorlage.render(paare=eigene)
    return dateien
