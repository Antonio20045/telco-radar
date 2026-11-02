"""Belegbilder neben dem Preis: aus dem Manifest zur Vorlagenfunktion ``belege_fuer``.

Gelesen wird allein ``data/state/belege_manifest.json`` (``beleg_manifest``),
geschrieben von ``scripts/belege_manifest.py`` aus den Release-Anhängen. Kein Netz, kein
LLM; ein Bild wird erst vom Browser geladen, wenn der Leser „Belege“ aufklappt. Fehlt
die Datei oder ein Bild, erscheint nichts. Eine kaputte Datei ist ein benannter Ausfall
(Regel 6).

Der Schlüssel eines Bilds ist ``(geraet_id, anbieter_id)`` = ``(m.schluessel,
anbieter_slug(Anbietername))`` der Preiszeile; beide Teile des Bilds kommen aus dem
Dateinamen, nie aus Titeltexten. Neueste Bilder zuerst, höchstens eins je Tag
(``beleg_manifest`` führt Tag und Monat zusammen).
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

from ..beleg_manifest import MANIFEST_NAME, Beleg, BelegManifestFehler, lies
from .ausfall import Ausfall
from .geraete_tco_grafik import anbieter_slug

TEIL = "Belegbilder"


def _heute(text: str) -> date | None:
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


def sortiert_je_preis(
    belege: list[Beleg], heute: date | None
) -> dict[tuple[str, str], list[dict]]:
    """Sichtbare Belege je ``(geraet_id, anbieter_id)``, neueste zuerst.

    Ohne ``heute`` (kein Bericht) bleibt es bei dem, was das Manifest schon gefiltert
    hat.
    """
    je_preis: dict[tuple[str, str], list[dict]] = {}
    for beleg in sorted(belege, key=lambda b: b.datum, reverse=True):
        if heute is not None and not beleg.sichtbar(heute):
            continue
        je_preis.setdefault((beleg.geraet_id, beleg.anbieter_id), []).append(
            {"datum": beleg.datum.isoformat(), "gross": beleg.gross, "url": beleg.url}
        )
    return je_preis


def installiere(env: Any, state_dir: Path, berichte: list[dict]) -> list[Ausfall]:
    """Macht ``belege_fuer(geraet_id, anbietername)`` für die Vorlagen verfügbar.

    ``berichte``: neuester zuerst; sein ``date`` ist das Berichtsdatum.
    """
    heute = berichte[0].get("date", "") if berichte else ""
    ausfaelle: list[Ausfall] = []
    try:
        je_preis = sortiert_je_preis(lies(state_dir / MANIFEST_NAME), _heute(heute))
    except BelegManifestFehler as fehler:
        ausfaelle.append(Ausfall.aus_ausnahme(TEIL, fehler))
        je_preis = {}
    env.globals["belege_fuer"] = lambda geraet_id, anbieter: je_preis.get(
        (geraet_id, anbieter_slug(anbieter or "")), []
    )
    return ausfaelle
