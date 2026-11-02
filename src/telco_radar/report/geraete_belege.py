"""Belegbilder neben dem Preis: aus dem Manifest zur Vorlagenfunktion ``belege_fuer``.

Gelesen wird allein ``data/state/belege_manifest.json`` (``beleg_manifest``),
geschrieben von ``scripts/belege_manifest.py`` aus den Release-Anhängen. Kein Netz, kein
LLM; ein Bild wird erst vom Browser geladen, wenn der Leser „Belege“ aufklappt. Fehlt
die Datei oder ein Bild, erscheint nichts. Eine kaputte Datei ist ein benannter Ausfall
(Regel 6).

Der Schlüssel eines Bilds ist ``(geraet_id, anbieter_id)`` = ``(m.schluessel,
anbieter_schluessel(Anbietername))`` der Preiszeile; beide Teile des Bilds kommen
aus dem Dateinamen, nie aus Titeltexten. Neueste Bilder zuerst, höchstens eins je Tag
(``beleg_manifest`` führt Tag und Monat zusammen).

Angezeigt werden die Belege der letzten ``ANZEIGE_TAGE`` Tage und dazu höchstens die
letzten ``ANZEIGE_GROSS_ANZAHL`` älteren großen Änderungen; die 90 Tage Aufbewahrung
sind keine Anzeige. Hat das Manifest einen Störungsvermerk (Geräte-Lauf konnte es nicht
erneuern), nennt die Seite ihn als Ausfall „Belegbilder“.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

from ..beleg_manifest import MANIFEST_NAME, Beleg, BelegManifestFehler, lies_manifest
from ..beleg_regeln import ANZEIGE_GROSS_ANZAHL, anbieter_schluessel, ist_anzeige_neu
from .ausfall import Ausfall

TEIL = "Belegbilder"


def _heute(text: str) -> date | None:
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


def sortiert_je_preis(
    belege: list[Beleg], heute: date | None
) -> dict[tuple[str, str], list[dict]]:
    """Angezeigte Belege je ``(geraet_id, anbieter_id)``, neueste zuerst.

    Alle der letzten ``ANZEIGE_TAGE`` Tage, dazu höchstens ``ANZEIGE_GROSS_ANZAHL``
    ältere große Änderungen. Was nicht mehr aufbewahrt wird (``Beleg.sichtbar``), fällt
    ganz heraus. Ohne ``heute`` (kein Bericht) bleibt es bei dem, was das Manifest schon
    gefiltert hat.
    """
    je_preis: dict[tuple[str, str], list[dict]] = {}
    aeltere_grosse: dict[tuple[str, str], int] = {}
    for beleg in sorted(belege, key=lambda b: b.datum, reverse=True):
        schluessel = (beleg.geraet_id, beleg.anbieter_id)
        if heute is not None:
            if not beleg.sichtbar(heute):
                continue
            if not ist_anzeige_neu(beleg.datum, heute):
                if not beleg.gross or aeltere_grosse.get(schluessel, 0) >= (
                    ANZEIGE_GROSS_ANZAHL
                ):
                    continue
                aeltere_grosse[schluessel] = aeltere_grosse.get(schluessel, 0) + 1
        je_preis.setdefault(schluessel, []).append(
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
        manifest = lies_manifest(state_dir / MANIFEST_NAME)
        je_preis = sortiert_je_preis(manifest.belege, _heute(heute))
        if manifest.ausfall:
            ausfaelle.append(
                Ausfall(
                    TEIL,
                    f"Manifest nicht erneuert, Stand von zuvor: {manifest.ausfall}",
                )
            )
    except BelegManifestFehler as fehler:
        ausfaelle.append(Ausfall.aus_ausnahme(TEIL, fehler))
        je_preis = {}
    env.globals["belege_fuer"] = lambda geraet_id, anbieter: je_preis.get(
        (geraet_id, anbieter_schluessel(anbieter or "")), []
    )
    return ausfaelle
