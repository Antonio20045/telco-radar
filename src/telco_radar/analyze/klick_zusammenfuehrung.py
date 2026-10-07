"""Klick-Bündel im Gerätelauf: ersetzen, gegenprüfen, nichts verschweigen.

Datenkonzept Geräteradar §7: Hauptquelle ist allein die Anbieterseite, gelesen vom
Klick-Crawler; alles andere ist Gegenprobe. ``zusammenfuehren`` liest die
Ergebnisdateien des Klick-Tageslaufs (``collect.geraete.klickergebnis``), ohne Angabe
aus ``data/state/klick`` (``ORDNER``, wenn es ihn gibt; ``--klick`` bzw. ``UMGEBUNG``
nennen einen anderen), macht daraus Rohsätze (``klickrohsatz``) und mischt sie unter
die Rohsätze der Adapter, bevor ``tco_buendel.aus_rohsaetzen`` sie zu Bündeln macht.
Ohne Ordner bleibt alles wie ohne Klick-Crawler. Den Lesestand schreibt nur die Ablage
(``klick_ablage``); der Gerätelauf liest ihn.

Schlüssel ist (Anbieter, Gerät, Speicher, Tarif, Ratenzahl); der Tarif gilt als gleich,
wenn der gelesene Tarif in Vergleichsform (``klickrohsatz.tarifschluessel``) dem Namen
oder dem Slug des Adaptersatzes entspricht. Ein Klick-Satz ersetzt jeden Adaptersatz
mit seinem Schlüssel (nur Zustand neu) und übernimmt dessen SKU, Tarifnamen und Slug:
die Bündel-ID bleibt, der Tarif löst auf wie bisher. Ohne Gegenstück behält er seine
SKU ohne Farbe und seinen gelesenen Tarifnamen. Jeder ersetzte Adaptersatz ist
Gegenprobe: gleich oder abweichend, je Feld gezählt, mit Beispielen.

„Nicht gelesen ist nicht leer“: nur eine Datei mit Laufstatus ``gelesen``, jünger als
``FRISCHEGRENZE_TAGE``, ersetzt etwas. Eine Datei von heute ist die Messung des Tages.
Eine Datei von gestern oder vorgestern (der Klick-Lauf kam nach dem Gerätelauf oder
fiel aus) liefert keine Werte mit heutigem Datum: ihre Varianten halten nur die
Ersetzung, und der Bestand behält seinen Stand mit dessen Datum und altert ihn wie jeden
anderen. Ebenso hält eine Variante des Lesestands, die innerhalb der Frischegrenze
erfasst wurde, die Ersetzung über die Rotation. Ein gestörter, leerer, veralteter oder
fehlender Anbieter ersetzt nichts.
"""

from __future__ import annotations

import logging
import os
from collections import Counter
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from ..collect.geraete.klickergebnis import (
    FRISCHEGRENZE_TAGE,
    ORDNER,
    STAND_DATEI,
    lies_ergebnisse,
    lies_stand,
)
from ..collect.geraete.klicklauf import LAUF_GELESEN
from ..collect.geraete.klickrohsatz import ZUSTAND_NEU, ausbeute, tarifschluessel
from ..geraete_model import Katalog
from ..tco_model import laufzeit_in_monaten

log = logging.getLogger(__name__)

UMGEBUNG = "TELCO_KLICK_ERGEBNISSE"
VERGLEICHSFELDER = (
    "geraet_zuzahlung",
    "geraet_monatsrate",
    "tarif_monatlich",
    "buendel_monatlich",
    "anschlusspreis",
    "tarif_bindung_monate",
)
CENT = 0.005
BEISPIELE = 8
GRUND_VERALTET = "Datei vom {datum}, älter als {tage} Tage"
GRUND_ZUKUNFT = "Datei vom {datum}, nach heute"
GRUND_DATUM = "Datum der Datei unlesbar: {datum!r}"
UEBERNOMMEN = ("sku_id", "tarif_name", "tarif_slug")

Geraet = Callable[[str], tuple[str, int | None]]
Schluessel = tuple[str, str, int | None, str, int | None]


@dataclass
class Gegenprobe:
    """Adaptersätze, die ein Klick-Satz ersetzt hat: gleich oder abweichend."""

    gleich: int = 0
    abweichend: int = 0
    ohne_vergleich: int = 0
    felder: Counter[str] = field(default_factory=Counter)
    beispiele: list[str] = field(default_factory=list)

    def vergleiche(self, klick: dict, adapter: dict) -> None:
        """Zählt einen ersetzten Adaptersatz; Felder nur, wo beide einen Wert haben."""
        beide = [
            f
            for f in VERGLEICHSFELDER
            if klick.get(f) is not None and adapter.get(f) is not None
        ]
        anders = [f for f in beide if abs(klick[f] - adapter[f]) > CENT]
        if not beide:
            self.ohne_vergleich += 1
        elif anders:
            self.abweichend += 1
            self.felder.update(anders)
            if len(self.beispiele) < BEISPIELE:
                teile = ", ".join(f"{f} {klick[f]} statt {adapter[f]}" for f in anders)
                self.beispiele.append(
                    f"{adapter.get('sku_id')} {_zeige(klick)}: {teile}"
                )
        else:
            self.gleich += 1

    def als_daten(self) -> dict:
        """Zahlen und Beispiele für Bilanz und Protokoll."""
        return {
            "gleich": self.gleich,
            "abweichend": self.abweichend,
            "ohne_vergleich": self.ohne_vergleich,
            "felder": dict(self.felder),
            "beispiele": list(self.beispiele),
        }


@dataclass
class Zusammenfuehrung:
    """Die Rohsätze für ``aus_rohsaetzen`` und die Bilanz (``None`` ohne Ordner)."""

    rohsaetze: list[dict]
    bilanz: dict | None = None


@dataclass
class Dateien:
    """Was die Ergebnisdateien beitragen: Messungen von heute, frühere Schlüssel."""

    eintraege: list[dict] = field(default_factory=list)
    heute: list[dict] = field(default_factory=list)
    frueher: set[Schluessel] = field(default_factory=set)
    anbieter: set[str] = field(default_factory=set)


def klickordner(umgebung: Mapping[str, str] | None = None) -> Path | None:
    """Der Ordner aus ``UMGEBUNG``; leer oder nicht gesetzt heißt kein Klick-Ordner."""
    wert = (os.environ if umgebung is None else umgebung).get(UMGEBUNG, "")
    return Path(wert) if wert else None


def zusammenfuehren(
    adapter: list[dict],
    ordner: Path | None,
    root: Path,
    katalog: Katalog,
    heute: str,
    geraet: Geraet,
) -> Zusammenfuehrung:
    """Liest Ergebnisse und Lesestand und führt zusammen.

    Ohne ``ordner`` gilt ``root / ORDNER``, wenn es ihn gibt; sonst bleibt alles wie
    bisher. Der Lesestand kommt immer aus ``root / ORDNER``.
    """
    standard = root / ORDNER
    if ordner is None and standard.is_dir():
        ordner = standard
    if ordner is None:
        return Zusammenfuehrung(list(adapter))
    ergebnisse, unlesbar = lies_ergebnisse(ordner)
    stand = lies_stand(standard / STAND_DATEI)
    return fuehre_zusammen(adapter, ergebnisse, katalog, heute, geraet, stand, unlesbar)


def fuehre_zusammen(
    adapter: list[dict],
    ergebnisse: list[dict],
    katalog: Katalog,
    heute: str,
    geraet: Geraet,
    stand: dict,
    unlesbar: Iterable[str] = (),
) -> Zusammenfuehrung:
    """Klick-Sätze ersetzen Adaptersätze mit gleichem Schlüssel (siehe Modulkopf)."""
    dateien = _lies(ergebnisse, katalog, heute)
    index: dict[Schluessel, list[int]] = {}
    for stelle, satz in enumerate(adapter):
        for schluessel in _adapterschluessel(satz, geraet):
            index.setdefault(schluessel, []).append(stelle)
    probe = Gegenprobe()
    ersetzt: set[int] = set()
    neu: list[dict] = []
    ohne_gegenstueck = 0
    for satz in dateien.heute:
        treffer = sorted(set(index.get(klickschluessel(satz), [])))
        if not treffer:
            ohne_gegenstueck += 1
            neu.append(satz)
        for stelle in treffer:
            alt = adapter[stelle]
            probe.vergleiche(satz, alt)
            ersetzt.add(stelle)
            neu.append({**satz, **{f: alt.get(f) for f in UEBERNOMMEN}})
    frueher = dateien.frueher | _frisch_gelesen(stand, dateien.anbieter, heute)
    bleiben = [
        satz
        for stelle, satz in enumerate(adapter)
        if stelle not in ersetzt
        and not any(k in frueher for k in _adapterschluessel(satz, geraet))
    ]
    bilanz = {
        "dateien": dateien.eintraege,
        "unlesbar": list(unlesbar),
        "klick_rohsaetze": len(neu),
        "ersetzt": len(ersetzt),
        "frueher_gelesen_ersetzt": len(adapter) - len(ersetzt) - len(bleiben),
        "ohne_gegenstueck": ohne_gegenstueck,
        "gegenprobe": probe.als_daten(),
    }
    _protokolliere(bilanz)
    return Zusammenfuehrung(bleiben + neu, bilanz)


def klickschluessel(satz: dict) -> Schluessel:
    """Der Schlüssel eines Klick-Rohsatzes (siehe Modulkopf)."""
    return (
        str(satz.get("anbieter")),
        str(satz.get("device_id")),
        satz.get("speicher_gb"),
        tarifschluessel(satz.get("tarif_name")),
        laufzeit_in_monaten(satz.get("laufzeit_monate")),
    )


def schluesseltext(schluessel: Schluessel) -> str:
    """Der Schlüssel als Text für den Lesestand."""
    return "|".join("" if teil is None else str(teil) for teil in schluessel)


def alter_tage(datum: object, heute: str) -> int | None:
    """Tage von ``datum`` bis ``heute``; ``None``, wenn ``datum`` kein ISO-Datum ist."""
    try:
        return (date.fromisoformat(heute) - date.fromisoformat(str(datum))).days
    except ValueError:
        return None


def _lies(ergebnisse: list[dict], katalog: Katalog, heute: str) -> Dateien:
    dateien = Dateien()
    for daten in ergebnisse:
        eintrag, saetze = _datei(daten, katalog, heute)
        dateien.eintraege.append(eintrag)
        if not eintrag["verwendet"]:
            continue
        dateien.anbieter.add(eintrag["anbieter"])
        if eintrag["alter_tage"] == 0:
            dateien.heute.extend(saetze)
        else:
            dateien.frueher.update(klickschluessel(s) for s in saetze)
    return dateien


def _datei(daten: dict, katalog: Katalog, heute: str) -> tuple[dict, list[dict]]:
    """Kopf einer Ergebnisdatei für die Bilanz und, wenn verwendet, ihre Rohsätze."""
    status = daten.get("laufstatus")
    datum = daten.get("datum")
    alter = alter_tage(datum, heute)
    eintrag = {
        "anbieter": daten.get("name"),
        "datum": datum,
        "alter_tage": alter,
        "laufstatus": status,
        "grund": daten.get("grund"),
        "verwendet": False,
        "warum_nicht": None,
    }
    if alter is None:
        eintrag["warum_nicht"] = GRUND_DATUM.format(datum=datum)
    elif alter < 0:
        eintrag["warum_nicht"] = GRUND_ZUKUNFT.format(datum=datum)
    elif alter >= FRISCHEGRENZE_TAGE:
        grund = GRUND_VERALTET.format(datum=datum, tage=FRISCHEGRENZE_TAGE)
        eintrag["warum_nicht"] = grund
    elif status != LAUF_GELESEN:
        eintrag["warum_nicht"] = f"Lauf {status}: {daten.get('grund')}"
    if eintrag["warum_nicht"] is not None:
        return eintrag, []
    aus = ausbeute(daten, katalog)
    eintrag.update(aus.als_daten(), verwendet=True)
    return eintrag, aus.rohsaetze


def _adapterschluessel(satz: dict, geraet: Geraet) -> list[Schluessel]:
    """Je Tarifschreibweise (Name, Slug) ein Schlüssel; nur Geräte im Zustand neu."""
    if str(satz.get("zustand") or ZUSTAND_NEU) != ZUSTAND_NEU:
        return []
    device, speicher = geraet(str(satz.get("sku_id") or ""))
    if not device:
        return []
    speicher = satz.get("speicher_gb") if speicher is None else speicher
    laufzeit = laufzeit_in_monaten(satz.get("laufzeit_monate"))
    tarife = {tarifschluessel(satz.get(f)) for f in ("tarif_name", "tarif_slug")}
    anbieter = str(satz.get("anbieter"))
    return [(anbieter, device, speicher, t, laufzeit) for t in sorted(tarife) if t]


def _frisch_gelesen(stand: dict, gelesen: set[str], heute: str) -> set[Schluessel]:
    """Schlüssel der verwendeten Anbieter, deren Variante im Lesestand frisch ist."""
    frisch: set[Schluessel] = set()
    for anbieter in gelesen:
        for text, datum in (stand["varianten"].get(anbieter) or {}).items():
            alter = alter_tage(datum, heute)
            if alter is not None and 0 <= alter < FRISCHEGRENZE_TAGE:
                frisch.add(_aus_text(text))
    return frisch


def _aus_text(text: str) -> Schluessel:
    anbieter, device, speicher, tarif, laufzeit = text.split("|")
    return (
        anbieter,
        device,
        int(speicher) if speicher else None,
        tarif,
        int(laufzeit) if laufzeit else None,
    )


def _zeige(satz: dict) -> str:
    return (
        f"{satz.get('anbieter')} {satz.get('tarif_name')}"
        f" {satz.get('laufzeit_monate')} Raten"
    )


def _protokolliere(bilanz: dict) -> None:
    for datei in bilanz["dateien"]:
        if not datei["verwendet"]:
            log.warning(
                "Klick-Ergebnis %s ersetzt nichts: %s",
                datei["anbieter"],
                datei["warum_nicht"],
            )
    probe = bilanz["gegenprobe"]
    log.info(
        "Klick-Bündel: %d Sätze, %d Adaptersätze ersetzt (%d gleich, %d abweichend,"
        " %d ohne Vergleich), %d nach früherer Lesung ersetzt, %d ohne Gegenstück",
        bilanz["klick_rohsaetze"],
        bilanz["ersetzt"],
        probe["gleich"],
        probe["abweichend"],
        probe["ohne_vergleich"],
        bilanz["frueher_gelesen_ersetzt"],
        bilanz["ohne_gegenstueck"],
    )
    for beispiel in probe["beispiele"]:
        log.warning("Klick-Gegenprobe weicht ab: %s", beispiel)
