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
WIDERLEGT = (
    "Belegte Lücke widerlegt: %s führt %s %s mit Preis nach der Prüfung (%s) - "
    "Lücke in config/geraete_abdeckung.yaml prüfen, Preis bleibt stehen"
)
GLEICHSTAND = (
    "Belegte Lücke überholt einen Preis vom Prüftag: %s %s %s (Prüfung %s) - "
    "Abruf und Prüfung am selben Tag, Preis gilt als veraltet"
)
BELEG_AUSSAGEN = (
    "nicht im Sortiment",
    "Seite entfernt",
    "nicht in der Geräteliste",
    "nicht mehr in der Geräteliste",
)


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
    belege: dict,
    anbieter: str,
    device_id: str,
    heute: str,
    speicher: str | None = None,
) -> tuple[dict | None, str]:
    """(gültiger Beleg, Grund). Ohne gültigen Beleg ist der Grund `GRUND_OHNE` oder
    `GRUND_ABGELAUFEN`; ohne bekannten Stichtag gilt kein Beleg als gültig.
    Mit `speicher` ("512gb") geht eine Lücke genau dieser Stufe vor; ohne ihn
    zählt nie eine Stufenlücke, denn ein fehlender Speicher ist kein fehlendes Gerät."""
    b = (
        (belege.get((anbieter, device_id, speicher)) if speicher else None)
        or belege.get((anbieter, device_id))
        or belege.get((anbieter, "*"))
    )
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


def stufe(speicher_gb) -> str | None:
    """Speicherstufe im Format der Config ("512gb"), `None` ohne Angabe."""
    return f"{int(speicher_gb)}gb" if speicher_gb else None


def gueltiger_beleg(
    belege: dict, anbieter, device_id: str, heute: str, speicher: str | None
) -> dict | None:
    """Der gültige Beleg (`beleg_fuer`) - und nur, wenn die Prüfung am Stichtag
    schon stattgefunden hat: ein Stand vor der Prüfung kennt die Lücke nicht."""
    beleg, _ = beleg_fuer(belege, str(anbieter or ""), device_id, heute, speicher)
    return beleg if beleg and beleg["geprueft"].isoformat() <= heute else None


def _beleg(belege: dict, satz: dict, heute: str) -> dict | None:
    """Die Lücke, die dieses Bündel treffen kann: nur Neugeräte (eine Aufarbeitung
    ist ein anderes Sortiment), Stufenlücke vor Gerätelücke vor Anbieterlücke."""
    if (satz.get("zustand") or "neu") != "neu":
        return None
    modell, speicher = buendel_abdeckung.modell_und_speicher(satz.get("sku_id") or "")
    if modell is None:
        return None
    return gueltiger_beleg(belege, satz.get("anbieter"), modell, heute, speicher)


def _nach_pruefung(abgerufen, geprueft: date) -> bool:
    """Das Bündel ist NACH der Prüfung abgerufen; unlesbar heißt nein (fail-closed)."""
    try:
        return date.fromisoformat(str(abgerufen)) > geprueft
    except ValueError:
        return False


def ist_nicht_im_sortiment(belege: dict, satz: dict, heute: str) -> bool:
    """Trifft eine gültige belegte Lücke dieses Bündel? Der Beleg gilt ab dem
    Prüfdatum (ein Stand davor ist nicht widerlegt) und nur für ein Bündel, das nicht
    NACH der Prüfung abgerufen wurde (sonst ist das Gerät zurück: Lücke falsch, der
    Preis bleibt, `markiere_mit` warnt). Gleichstand (Abruf == Prüfdatum) gilt als
    überholt - Uhrzeiten sind unbekannt, `<=` ist die sichere Richtung - und warnt."""
    beleg = _beleg(belege, satz, heute)
    if beleg is None:
        return False
    return not _nach_pruefung(satz.get("abgerufen_am"), beleg["geprueft"])


def markiere_mit(saetze: list[dict], belege: dict, heute: str) -> list[dict]:
    """Die Bündelsätze, bei Treffern als Kopie mit Vermerk `veraltet 17`.

    Warnt (je Anbieter/Gerät/Stufe einmal) bei einem Bündel, das eine belegte Lücke
    widerlegt (jünger als die Prüfung: Lücke falsch, Preis bleibt) und bei
    Gleichstand (Abruf am Prüftag: der Preis wird überholt, könnte aber nach der
    Prüfung entstanden sein)."""
    if not belege:
        return list(saetze)
    aus, warnungen = [], {}
    for s in saetze:
        beleg = _beleg(belege, s, heute) if isinstance(s, dict) else None
        if beleg is None:
            aus.append(s)
            continue
        modell, speicher = buendel_abdeckung.modell_und_speicher(s.get("sku_id") or "")
        geprueft = beleg["geprueft"]
        art: str | None
        if _nach_pruefung(s.get("abgerufen_am"), geprueft):
            art = WIDERLEGT
            aus.append(s)
        else:
            art = (
                GLEICHSTAND
                if str(s.get("abgerufen_am")) == geprueft.isoformat()
                else None
            )
            aus.append({**s, "pruefung": VERMERK})
        if art:
            warnungen[(art, s.get("anbieter"), modell, speicher)] = geprueft
    for (art, anbieter, modell, speicher), geprueft in sorted(
        warnungen.items(), key=str
    ):
        log.warning(art, anbieter, modell, speicher, datum_de(geprueft.isoformat()))
    return aus


def markiere(saetze: list[dict] | None, state_dir, heute: str) -> list[dict]:
    """`markiere_mit` mit den belegten Lücken neben `data/state`; ohne Sätze leer."""
    return markiere_mit(saetze or [], belege_aus(state_dir), heute)


def lies(saetze: list[dict], state_dir, heute: str) -> list[dict]:
    """Die Bündel der Seite: ohne überholte Klick-Bündel, nicht geführte Geräte als
    Lücke markiert. Eine Stelle für Karten, Export, Katalog und Grafik."""
    return markiere(klick_ueberholt.ohne_ueberholte(saetze), state_dir, heute)
