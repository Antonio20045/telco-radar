"""Produktfotos der Geräte: die Zuordnung Gerät → Bilddatei steht in einer Datei.

`config/geraete_bilder.yaml` ordnet einer `device_id` eine Bilddatei zu. Die
Dateien liegen im Repo bei den Vorlagen (`report/templates/static/geraete/`)
und werden bei jedem Rendern mit allen anderen statischen Dateien nach
`site/static/` gespiegelt; welcher Ordner das ist, sagt der Aufrufer. Es gibt
KEINEN Abruf und kein Hotlinking fremder Händlerbilder: ein Foto kommt nur auf
die Seite, wenn die Datei im Repo liegt und ihre Herkunft in der YAML-Datei
steht (`quelle`, `lizenz`).

Fehlt die Zuordnungsdatei oder fehlt ein Gerät darin, ist das kein Fehler: die
Kachel zeigt die Geräte-Silhouette als Platzhalter. Steht ein Gerät in der
Zuordnung, die genannte Bilddatei fehlt aber im Ordner, wird das protokolliert
und ebenfalls der Platzhalter gezeigt - nie ein kaputtes Bild.
"""

from __future__ import annotations

import logging
from pathlib import Path

import yaml

log = logging.getLogger(__name__)

DATEI = ("config", "geraete_bilder.yaml")
ORDNER = "geraete"
PFAD_VORLAGE = f"static/{ORDNER}/{{datei}}"


def bilder_pfad(state_dir) -> Path:
    """`config/geraete_bilder.yaml` neben `data/state` (Aufbau des Repos)."""
    return Path(state_dir).parents[1].joinpath(*DATEI)


def lade_bilder(pfad: Path, ordner: Path) -> dict[str, str]:
    """{device_id: "static/geraete/<datei>"} aus der Zuordnungsdatei.

    Ohne Datei ein leeres Verzeichnis (der Normalfall, solange keine Fotos mit
    geklärter Herkunft vorliegen). Eine unlesbare Datei wird protokolliert und
    zählt wie keine Datei; eine genannte, aber nicht vorhandene Bilddatei fällt
    einzeln heraus.
    """
    if not pfad.is_file():
        return {}
    try:
        daten = yaml.safe_load(pfad.read_text(encoding="utf-8")) or {}
        eintraege = daten.get("bilder") or {}
    except (OSError, ValueError, yaml.YAMLError, AttributeError):
        log.exception("Bildzuordnung der Geräte nicht lesbar: %s", pfad)
        return {}
    aus: dict[str, str] = {}
    for device_id, eintrag in eintraege.items():
        datei = (eintrag or {}).get("datei") if isinstance(eintrag, dict) else eintrag
        if not datei:
            log.warning("Bildzuordnung ohne Datei: %s", device_id)
            continue
        if not (ordner / str(datei)).is_file():
            log.warning("Bilddatei fehlt im Bildordner: %s (%s)", datei, device_id)
            continue
        aus[str(device_id)] = PFAD_VORLAGE.format(datei=datei)
    return aus
