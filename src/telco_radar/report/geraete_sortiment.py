"""Bündel eines Geräts, das der Anbieter nachweislich nicht mehr verkauft.

Die belegten Lücken (`config/geraete_abdeckung.yaml`, `art: nicht_im_portfolio`)
sagen, was der Wächter und die Portfolio-Ansicht wissen: dieser Anbieter führt
dieses Gerät (oder diese Speicherstufe) nicht. Der Bestand löscht nie ein
Bündel (`analyze/tco_store`), also stünde die alte Preiszeile weiter als gültiger
Preis da - 1&1 iPhone 16e 128 GB (abgerufen 05.11.2026) und iPhone 15 128 GB
(08.10.2026), 08.11.2026 am Original widerlegt.

`markiere` nimmt solchen Bündeln beim Lesen die Zahl: der Vermerk der Prüfstelle
(`pruefung`) wird `veraltet 17`, derselbe Weg wie Regel 16 (`geraete_preisstand`).
Die Notbremse liest daraus `nicht_im_sortiment`, Karte, Export, Verlauf und
Grafik nennen den Grund statt einer Zahl. Die Gültigkeit definiert `beleg_fuer`,
die auch die Portfolio-Ansicht nutzt: Sortiments-Aussage im `grund`, heute <= `bis`.

Kommt das Gerät zurück - ein Bündel, das NACH der Prüfung abgerufen wurde -,
bleibt es unberührt und der Wächter warnt (`luecke_ueberholt`): "nicht gelesen"
ist nicht "nicht mehr da". Der Bestand selbst bleibt unverändert (Kopien).
"""

from __future__ import annotations

import logging
from datetime import date
from pathlib import Path

from ..analyze import buendel_abdeckung
from ..analyze.geraete_pruefstatus import REGEL_SORTIMENT, VERALTET
from . import klick_ueberholt

log = logging.getLogger(__name__)

VERMERK = f"{VERALTET} {REGEL_SORTIMENT}"
ABDECKUNG = ("config", "geraete_abdeckung.yaml")
GRUND_OHNE = "ohne Beleg"
GRUND_ABGELAUFEN = "Beleg abgelaufen"
GRUND_UNZUREICHEND = "Beleg zeigt kein fehlendes Sortiment"
BELEG_AUSSAGEN = ("nicht im Sortiment", "Seite entfernt", "nicht in der Geräteliste")


def datum_de(text) -> str:
    """„2026-11-08“ → „08.11.2026“; anderes bleibt, wie es ist."""
    try:
        d = date.fromisoformat(str(text))
    except ValueError:
        return str(text)
    return f"{d.day:02d}.{d.month:02d}.{d.year}"


def abdeckung_pfad(state_dir) -> Path:
    """`config/geraete_abdeckung.yaml` neben `data/state` (Aufbau des Repos)."""
    return Path(state_dir).parents[1].joinpath(*ABDECKUNG)


def beleg_fuer(
    belege: dict, anbieter: str, device_id: str, heute: str
) -> tuple[dict | None, str]:
    """(gültiger Beleg, Grund). Ohne gültigen Beleg ist der Grund `GRUND_OHNE` oder
    `GRUND_ABGELAUFEN`; ohne bekannten Stichtag gilt kein Beleg als gültig."""
    b = belege.get((anbieter, device_id)) or belege.get((anbieter, "*"))
    if not b:
        return None, GRUND_OHNE
    if not any(a.lower() in str(b.get("grund", "")).lower() for a in BELEG_AUSSAGEN):
        return None, GRUND_UNZUREICHEND
    if not heute or heute > b["bis"].isoformat():
        return None, f"{GRUND_ABGELAUFEN} (bis {datum_de(b['bis'].isoformat())})"
    return b, ""


def belege_aus(state_dir) -> dict:
    """Die belegten Lücken neben `data/state`; unlesbar heißt keine Lücke belegt
    (die sichere Richtung für die Portfolio-Aussage, hier aber ohne Wirkung auf
    Preise) und wird protokolliert."""
    try:
        pfad = abdeckung_pfad(state_dir)
        return buendel_abdeckung.lade_pflicht(Path(pfad))["belege"]
    except (OSError, ValueError, KeyError, AttributeError):
        log.exception("Belegliste für nicht geführte Geräte nicht lesbar")
        return {}


def _beleg(belege: dict, satz: dict, heute: str) -> dict | None:
    modell, speicher = buendel_abdeckung.modell_und_speicher(satz.get("sku_id") or "")
    anbieter = satz.get("anbieter") or ""
    if modell is None:
        return None
    for schluessel in (
        (anbieter, modell, speicher),
        (anbieter, modell),
        (anbieter, "*"),
    ):
        if schluessel in belege:
            beleg, _ = beleg_fuer(
                {(anbieter, modell): belege[schluessel]}, anbieter, modell, heute
            )
            return beleg
    return None


def ist_nicht_im_sortiment(belege: dict, satz: dict, heute: str) -> bool:
    """Trifft eine gültige belegte Lücke dieses Bündel? Der Beleg gilt ab dem
    Prüfdatum (ein Stand davor ist nicht widerlegt) und nur für ein Bündel, das nicht
    NACH der Prüfung abgerufen wurde (sonst ist das Gerät zurück)."""
    beleg = _beleg(belege, satz, heute)
    if beleg is None:
        return False
    geprueft = beleg["geprueft"].isoformat()
    return heute >= geprueft and str(satz.get("abgerufen_am") or "") <= geprueft


def markiere_mit(saetze: list[dict], belege: dict, heute: str) -> list[dict]:
    """Die Bündelsätze, bei Treffern als Kopie mit Vermerk `veraltet 17`."""
    if not belege:
        return list(saetze)
    return [
        {**s, "pruefung": VERMERK}
        if isinstance(s, dict) and ist_nicht_im_sortiment(belege, s, heute)
        else s
        for s in saetze
    ]


def markiere(saetze: list[dict] | None, state_dir, heute: str) -> list[dict]:
    """`markiere_mit` mit den belegten Lücken neben `data/state`; ohne Sätze leer."""
    return markiere_mit(saetze or [], belege_aus(state_dir), heute)


def lies(saetze: list[dict], state_dir, heute: str) -> list[dict]:
    """Die Bündel der Seite: ohne überholte Klick-Bündel, nicht geführte Geräte als
    Lücke markiert. Eine Stelle für Karten, Export, Katalog und Grafik."""
    return markiere(klick_ueberholt.ohne_ueberholte(saetze), state_dir, heute)
