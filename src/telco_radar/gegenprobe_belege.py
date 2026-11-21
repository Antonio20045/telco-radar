"""Welche Gegenprobe einen angezeigten Preis belegt, welche eine Preisänderung, und
welche Bilder darum verlinkt bleiben: EINE Stelle für Seite, Bilanz und Aufräumen.

Abnahmekriterium 3 (Antonio, 21.11.2026), ehrlich ausgelegt: ein angezeigter Preis ist
belegt durch das Bild seiner letzten guten Gegenprobe (``des_preises``: ``letzte_gute``,
sonst der letzte Versuch mit Grund). Eine Preisänderung ist am Tag ihres Auftretens
geprüft (``neuer_preis``: die Gegenprobe dieses Tages, die genau die neue Messung
prüfte); ihr „Vortag“ ist die letzte gute Prüfung des alten Preises (``alter_preis``:
vor dem Tag der Änderung, gespeicherte Posten gleich der alten Messung). Beide suchen
erst das Bündel, dann dasselbe Angebot in anderer Farbe.

Aufbewahrung (``verlinkte``): ein Bild bleibt, solange die Seite es zeigt, als Beleg
eines angezeigten Preises oder einer Preisänderung, höchstens ``AUFBEWAHRUNG_TAGE``
nach seiner Prüfung (``aufbewahrt``; älter zeigt die Seite „kein Bild“ mit Grund). So
ist jedes Release nach dieser Frist ganz frei und geht mit einem Aufruf (die Löschzeit
reicht nicht für einzelne Bilder, ``scripts/belege_manifest.py``). Jünger als
``MINDEST_TAGE`` (Fenster plus Vorlauf) wird nie gelöscht. Die Liste schreibt jeder
Lauf der Gegenprobe nach ``verlinkt.json``; ``scripts/belege_manifest.py`` löscht nur,
was nicht darin steht (``gegenprobe_ablage.plane``).
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterable, Iterator, Mapping
from datetime import date
from pathlib import Path

from . import gegenprobe as gp
from .gegenprobe_fenster import GEGENPROBE_FENSTER_TAGE, VORLAUF_TAGE, Gegenproben

AUFBEWAHRUNG_TAGE = 90
"""So lange nach ihrer Prüfung zeigt die Seite ein Gegenprobe-Bild, am Preis und an
beiden Tagen einer Preisänderung, und so lange bleibt es im Release (wie die großen
Änderungen der Klick-Belege). EINE Frist für beides: eine ältere Änderung zeigt
benannt „Bild nach 90 Tagen nicht aufbewahrt“."""
MINDEST_TAGE = GEGENPROBE_FENSTER_TAGE + VORLAUF_TAGE
"""Jünger wird kein Bild gelöscht: es kann noch ``letzte_gute`` eines Preises werden,
den der Lauf gerade erst prüft."""
VERLINKT = gp.ORDNER / "verlinkt.json"
FORMAT = 1
GRUND_KEINE = "noch nicht gegengeprüft"
GRUND_OHNE_BILD = "Gegenprobe ohne Bild"
GRUND_ALT = f"Bild nach {AUFBEWAHRUNG_TAGE} Tagen nicht aufbewahrt"
GRUND_GELOESCHT = "nicht mehr im Release"
GRUND_KEIN_ALTER = "keine gute Gegenprobe des alten Preises"
GRUND_KEIN_NEUER = "an diesem Tag nicht gegengeprüft"


def des_preises(
    proben: Gegenproben, buendel_id: str, gesamt: float | None, posten=None
) -> gp.Ergebnis | None:
    """Die Gegenprobe, die an der Preiszeile steht: die letzte gute, sonst der letzte
    geöffnete Versuch (gescheitert, mit Grund)."""
    gute = proben.letzte_gute(buendel_id, gesamt, posten)
    return gute or proben.letzter_versuch(buendel_id, gesamt, posten)


def _passt(e: gp.Ergebnis, messung: Mapping) -> bool:
    """Prüfte ``e`` genau diese Messung (gespeicherte Posten gleich)?"""
    return bool(e.gespeichert) and not gp.geaendert(e.gespeichert, messung)


def neuer_preis(proben: Gegenproben, messung: Mapping, tag: str) -> gp.Ergebnis | None:
    """Die Gegenprobe am Tag ``tag``, die die Messung des Tages prüfte (eine geöffnete
    vor „nicht gegengeprüft“ mit Grund); eine Zeile ohne gespeicherte Posten (vor dem
    20.11.2026) zählt nur für dasselbe Bündel."""
    bid = str(messung["id"])
    offen = None
    for e in proben.des_angebots(bid):
        if e.datum != tag:
            continue
        if not (_passt(e, messung) or (not e.gespeichert and e.buendel_id == bid)):
            continue
        if e.status != gp.NICHT_GEGENGEPRUEFT:
            return e
        offen = offen or e
    return offen


def alter_preis(proben: Gegenproben, vorher: Mapping, tag: str) -> gp.Ergebnis | None:
    """Die letzte gute Gegenprobe des alten Preises vor dem Tag der Änderung."""
    for e in proben.des_angebots(str(vorher["id"])):
        if e.datum < tag and e.status in gp.GEPRUEFT and _passt(e, vorher):
            return e
    return None


def aufbewahrt(datum: str, pruefdatum: str) -> bool:
    """Zeigt die Seite an ``datum`` noch das Bild einer Prüfung vom ``pruefdatum``?"""
    if not datum or not pruefdatum:
        return True
    alter = (date.fromisoformat(datum) - date.fromisoformat(pruefdatum[:10])).days
    return alter <= AUFBEWAHRUNG_TAGE


def aenderungen_je_tag(
    tage: Iterable[tuple[str, list[dict]]],
) -> Iterator[tuple[str, list[tuple[Mapping, Mapping]]]]:
    """(Tag, [(Messung, Messung davor)]) je Messtag, wie die Seite „Preisänderungen“
    (``gegenprobe.aenderungen`` gegen ``letzte_messungen``)."""
    zuletzt: dict[str, Mapping] = {}
    for tag, saetze in tage:
        gemessen = gp.gemessen(saetze, tag)
        yield tag, gp.aenderungen(gemessen, zuletzt)
        zuletzt.update(gemessen)


def verlinkte(
    datum: str,
    angezeigt: Iterable[Mapping],
    gesamt: Callable[[Mapping], float | None],
    proben: Gegenproben,
    tage: Iterable[tuple[str, list[dict]]] = (),
) -> set[str]:
    """Jede Bildadresse, die die Seite an ``datum`` zeigt (Modulkopf)."""
    gezeigt: list[gp.Ergebnis | None] = [
        des_preises(proben, str(satz["id"]), gesamt(satz), satz) for satz in angezeigt
    ]
    for tag, paare in aenderungen_je_tag(tage):
        for messung, vorher in paare:
            gezeigt.append(neuer_preis(proben, messung, tag))
            gezeigt.append(alter_preis(proben, vorher, tag))
    return {
        e.bild
        for e in gezeigt
        if e is not None and e.bild and aufbewahrt(datum, e.datum)
    }


def schreibe_verlinkt(wurzel: Path, datum: str, urls: Iterable[str]) -> Path:
    """``data/state/gegenprobe/verlinkt.json``: Tag und Adressen, sortiert."""
    pfad = wurzel / VERLINKT
    pfad.parent.mkdir(parents=True, exist_ok=True)
    daten = {"format": FORMAT, "datum": datum, "bilder": sorted(set(urls))}
    pfad.write_text(json.dumps(daten, ensure_ascii=False, indent=0) + "\n", "utf-8")
    return pfad


def lies_verlinkt(wurzel: Path) -> tuple[date, set[str]] | None:
    """(Tag, Adressen) aus ``verlinkt.json``; None ohne Datei, ``ValueError`` bei
    einer unlesbaren (dann löscht niemand)."""
    pfad = wurzel / VERLINKT
    if not pfad.is_file():
        return None
    try:
        daten = json.loads(pfad.read_text(encoding="utf-8"))
        if daten["format"] != FORMAT:
            raise ValueError(f"Format {daten['format']!r}")
        return date.fromisoformat(daten["datum"]), {str(u) for u in daten["bilder"]}
    except (KeyError, TypeError) as fehler:
        raise ValueError(f"{pfad.name}: {fehler}") from fehler


def bild_ganz(e: gp.Ergebnis | None) -> bool:
    """Zeigt das Bild dieser Gegenprobe die ganze Konfiguration (Gerät, Speicher,
    Tarif, Raten, Preis, soweit das Bündel sie hat)? Ein Bild vor dem 22.11.2026
    (nur Preisbereich, ``bild_zeigt`` None) zählt nicht."""
    return bool(e is not None and e.bild and e.bild_zeigt and not e.bild_ohne)
