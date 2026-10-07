"""Klick-Bündel im Gerätelauf: ersetzen, gegenprüfen, nichts verschweigen.

Datenkonzept Geräteradar §7: Hauptquelle ist allein die Anbieterseite, gelesen vom
Klick-Crawler; alles andere ist Gegenprobe. ``zusammenfuehren`` liest die
Ergebnisdateien des Klick-Tageslaufs (``collect.geraete.klickergebnis``) aus einem
Ordner, macht daraus Rohsätze (``klickrohsatz``) und mischt sie unter die Rohsätze der
Adapter, bevor ``tco_buendel.aus_rohsaetzen`` sie zu Bündeln macht. Ohne Ordner bleibt
alles wie ohne Klick-Crawler.

Schlüssel ist (Anbieter, Gerät, Speicher, Tarif, Ratenzahl); der Tarif gilt als gleich,
wenn der gelesene Tarif in Vergleichsform (``klickrohsatz.tarifschluessel``) dem Namen
oder dem Slug des Adaptersatzes entspricht. Ein Klick-Satz ersetzt jeden Adaptersatz
mit seinem Schlüssel (nur Zustand neu) und übernimmt dessen SKU, Tarifnamen und Slug:
die Bündel-ID bleibt, der Tarif löst auf wie bisher. Ohne Gegenstück behält er seine
SKU ohne Farbe und seinen gelesenen Tarifnamen. Jeder ersetzte Adaptersatz ist
Gegenprobe: gleich oder abweichend, je Feld gezählt, mit Beispielen.

„Nicht gelesen ist nicht leer“: nur eine Datei von heute mit Laufstatus ``gelesen``
ersetzt etwas. Ein gestörter, leerer oder fehlender Anbieter ersetzt nichts und
schreibt nichts in den Lesestand. Liest ein Lauf nach Rotation nicht jede Variante,
bleibt ein Adaptersatz ersetzt, solange dieselbe Variante innerhalb von
``FRISCHEGRENZE_TAGE`` erfasst wurde (Lesestand); der Bestand behält dann die
Klick-Messung mit ihrem Datum und altert sie wie jede andere.
"""

from __future__ import annotations

import logging
from collections import Counter
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from ..collect.geraete.klickergebnis import (
    FRISCHEGRENZE_TAGE,
    GELESENE_SEITEN,
    STAND_FORMAT,
    lies_ergebnisse,
    lies_stand,
    schreibe,
)
from ..collect.geraete.klicklauf import LAUF_GELESEN
from ..collect.geraete.klickrohsatz import ZUSTAND_NEU, ausbeute, tarifschluessel
from ..geraete_model import Katalog
from ..tco_model import laufzeit_in_monaten

log = logging.getLogger(__name__)

UMGEBUNG = "TELCO_KLICK_ERGEBNISSE"
STAND = "klick_stand.json"
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
GRUND_ANDERER_TAG = "Datei vom {datum}, nicht von heute"
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
    """Die Rohsätze für ``aus_rohsaetzen``, die Bilanz und der neue Lesestand."""

    rohsaetze: list[dict]
    bilanz: dict | None = None
    stand: dict | None = None
    pfad: Path | None = None

    def speichere(self) -> None:
        """Schreibt den Lesestand, wenn es einen gibt; ohne Klick-Ordner nichts."""
        if self.stand is not None and self.pfad is not None:
            schreibe(self.pfad, self.stand)


def zusammenfuehren(
    adapter: list[dict],
    ordner: Path | None,
    zustand: Path,
    katalog: Katalog,
    heute: str,
    geraet: Geraet,
) -> Zusammenfuehrung:
    """Liest Ergebnisse und Lesestand und führt zusammen; ohne ``ordner`` wie bisher."""
    if ordner is None:
        return Zusammenfuehrung(list(adapter))
    ergebnisse, unlesbar = lies_ergebnisse(ordner)
    pfad = zustand / STAND
    ergebnis = fuehre_zusammen(
        adapter, ergebnisse, katalog, heute, geraet, lies_stand(pfad), unlesbar
    )
    ergebnis.pfad = pfad
    return ergebnis


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
    dateien: list[dict] = []
    klick: list[dict] = []
    gelesen: set[str] = set()
    for daten in ergebnisse:
        eintrag, saetze = _datei(daten, katalog, heute)
        dateien.append(eintrag)
        if eintrag["verwendet"]:
            gelesen.add(eintrag["anbieter"])
            klick.extend(saetze)
            _merke_seiten(stand, daten, heute)
    index: dict[Schluessel, list[int]] = {}
    for stelle, satz in enumerate(adapter):
        for schluessel in _adapterschluessel(satz, geraet):
            index.setdefault(schluessel, []).append(stelle)
    probe = Gegenprobe()
    ersetzt: set[int] = set()
    neu: list[dict] = []
    ohne_gegenstueck = 0
    for satz in klick:
        schluessel = _klickschluessel(satz)
        _merke_variante(stand, schluessel, heute)
        treffer = sorted(set(index.get(schluessel, [])))
        if not treffer:
            ohne_gegenstueck += 1
            neu.append(satz)
        for stelle in treffer:
            alt = adapter[stelle]
            probe.vergleiche(satz, alt)
            ersetzt.add(stelle)
            neu.append({**satz, **{f: alt.get(f) for f in UEBERNOMMEN}})
    frueher = _frisch_gelesen(stand, gelesen, heute)
    frueher_ersetzt = 0
    bleiben: list[dict] = []
    for stelle, satz in enumerate(adapter):
        if stelle in ersetzt:
            continue
        if any(k in frueher for k in _adapterschluessel(satz, geraet)):
            frueher_ersetzt += 1
            continue
        bleiben.append(satz)
    _kuerze(stand, heute)
    bilanz = {
        "dateien": dateien,
        "unlesbar": list(unlesbar),
        "klick_rohsaetze": len(neu),
        "ersetzt": len(ersetzt),
        "frueher_gelesen_ersetzt": frueher_ersetzt,
        "ohne_gegenstueck": ohne_gegenstueck,
        "gegenprobe": probe.als_daten(),
    }
    _protokolliere(bilanz)
    return Zusammenfuehrung(bleiben + neu, bilanz, stand)


def _datei(daten: dict, katalog: Katalog, heute: str) -> tuple[dict, list[dict]]:
    """Kopf einer Ergebnisdatei für die Bilanz und, wenn verwendet, ihre Rohsätze."""
    status = daten.get("laufstatus")
    eintrag = {
        "anbieter": daten.get("name"),
        "datum": daten.get("datum"),
        "laufstatus": status,
        "grund": daten.get("grund"),
        "verwendet": False,
        "warum_nicht": None,
    }
    if daten.get("datum") != heute:
        eintrag["warum_nicht"] = GRUND_ANDERER_TAG.format(datum=daten.get("datum"))
        return eintrag, []
    if status != LAUF_GELESEN:
        eintrag["warum_nicht"] = f"Lauf {status}: {daten.get('grund')}"
        return eintrag, []
    aus = ausbeute(daten, katalog)
    eintrag.update(aus.als_daten(), verwendet=True)
    return eintrag, aus.rohsaetze


def _klickschluessel(satz: dict) -> Schluessel:
    return (
        str(satz.get("anbieter")),
        str(satz.get("device_id")),
        satz.get("speicher_gb"),
        tarifschluessel(satz.get("tarif_name")),
        laufzeit_in_monaten(satz.get("laufzeit_monate")),
    )


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


def _text(schluessel: Schluessel) -> str:
    return "|".join("" if teil is None else str(teil) for teil in schluessel)


def _merke_seiten(stand: dict, daten: dict, heute: str) -> None:
    seiten = stand["seiten"].setdefault(str(daten.get("name")), {})
    for seite in daten.get("seiten") or []:
        if seite.get("status") in GELESENE_SEITEN:
            seiten[str(seite.get("adresse"))] = heute


def _merke_variante(stand: dict, schluessel: Schluessel, heute: str) -> None:
    stand["varianten"].setdefault(schluessel[0], {})[_text(schluessel)] = heute


def _frisch_gelesen(stand: dict, gelesen: set[str], heute: str) -> set[Schluessel]:
    """Schlüssel der heute gelesenen Anbieter, deren Variante noch frisch ist."""
    frisch: set[Schluessel] = set()
    for anbieter in gelesen:
        for text, datum in (stand["varianten"].get(anbieter) or {}).items():
            if _alter(datum, heute) < FRISCHEGRENZE_TAGE:
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


def _kuerze(stand: dict, heute: str) -> None:
    """Varianten jenseits der Frischegrenze wirken nicht mehr und fallen weg."""
    stand["format"] = STAND_FORMAT
    for anbieter, varianten in stand["varianten"].items():
        stand["varianten"][anbieter] = {
            k: d for k, d in varianten.items() if _alter(d, heute) < FRISCHEGRENZE_TAGE
        }


def _alter(datum: str, heute: str) -> int:
    return (date.fromisoformat(heute) - date.fromisoformat(datum)).days


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
