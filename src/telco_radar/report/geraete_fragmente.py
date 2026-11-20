"""Die Ladegut-Fragmente der Geräteseite, je Modell eine Datei.

Bis 10.10.2026 holte app.js bei jedem Wechsel von Modell, Band oder
Laufzeit die Gesamtfragmente `geraete-zeitreihe.html` (47 MB) und
`geraete-buendel.html` (24 MB) und zerlegte sie im Browser: 7 s am
Rechner, 35 s mit Handy-CPU. Jetzt lädt der Client nur die Datei des
gewählten Modells aus `data/zr/` bzw. `data/bnd/`. `geraete-buendel.html`
bleibt für Prüfungen stehen. Die Gesamt-Zeitreihe entfällt seit 26.10.2026:
sie wuchs über 100 MB, und GitHub lehnte jeden Push der Seite ab.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from . import geraete_preisaenderungen

ZR_ORDNER = "zr"
BND_ORDNER = "bnd"


def _neu(ordner: Path) -> Path:
    if ordner.exists():
        shutil.rmtree(ordner)
    ordner.mkdir(parents=True)
    return ordner


def vorbereiten(
    site_dir: Path, env, geraete: dict, radar: dict | None = None
) -> dict[Path, str]:
    """Leert `data/zr/` und `data/bnd/`, gibt jede Fragmentdatei mit Inhalt zurück.

    Die Zeitfenster-Fragmente enthalten nur Grafiken (keine Rechenweg-Vorlagen, keine
    Bündel-Informationen); je ausgewähltem Modell genügt ein Abruf.

    UI-1717 Aufgabe 5: der Radar-Reiter (`#tafel-radar`, heute ohne Navi-
    Knopf, nur per Deep-Link erreichbar) stand bisher komplett im First
    Paint von `geraete.html` (1,57 MB, nie gesehen ohne JS-Tab-Wechsel).
    `data/geraete-radar.html` traegt denselben Inhalt, app.js laedt ihn
    nur beim Wechsel auf diesen Reiter nach.
    """
    daten = site_dir / "data"
    daten.mkdir(exist_ok=True)
    dateien = geraete_preisaenderungen.seiten(env, geraete, site_dir)
    if radar:
        radar_vorlage = env.get_template("geraete_radar_fragment.html.j2")
        dateien[daten / "geraete-radar.html"] = radar_vorlage.render(
            prefix="", geraete=geraete, wr=radar
        )
    tco = geraete.get("tco") or {}
    if not tco.get("modelle"):
        return dateien
    zr = geraete.get("zeitreihe") or {}
    vorgabe = (zr.get("start") or {}).get("modell") or tco["modell_vorgabe"]
    bnd_vorlage = env.get_template("geraete_buendel_fragment.html.j2")
    dateien[daten / "geraete-buendel.html"] = bnd_vorlage.render(
        modelle=tco["modelle"], vorgabe=vorgabe
    )
    bnd = _neu(daten / BND_ORDNER)
    for m in tco["modelle"]:
        dateien[bnd / f"{m['id']}.html"] = bnd_vorlage.render(
            modelle=[m], vorgabe=vorgabe
        )
    paare = zr.get("paare")
    if not paare:
        return dateien
    zr_vorlage = env.get_template("geraete_zeitreihe_fragment.html.j2")
    (daten / "geraete-zeitreihe.html").unlink(missing_ok=True)
    je_modell: dict[str, list] = {}
    for p in paare:
        je_modell.setdefault(p["modell"], []).append(p)
    ziel = _neu(daten / ZR_ORDNER)
    fenster_vorlage = env.get_template("geraete_zeitfenster_fragment.html.j2")
    fenster_root = _neu(daten / "zf")
    for modell, eigene in je_modell.items():
        dateien[ziel / f"{modell}.html"] = zr_vorlage.render(paare=eigene)
        dateien[fenster_root / f"{modell}.html"] = fenster_vorlage.render(paare=eigene)
    return dateien
